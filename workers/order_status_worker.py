
import json
import signal
import threading
import time

import redis

from lib.events import DELIVERY_EVENTS_STREAM
from lib.event_reliability import handle_failed_message
from lib.redis import redis_client
from services.order_service.app.database import SessionLocal
from services.order_service.app.order_service import OrderManager


CONSUMER_GROUP = "flowmesh-order-status-workers"
CONSUMER_NAME = "order-status-worker-1"

# A message must be idle for at least 60 seconds before recovery.
PENDING_IDLE_THRESHOLD_MS = 60_000
CLAIM_BATCH_SIZE = 10
RECOVERY_INTERVAL_SECONDS = 30

# Shared shutdown signal for the worker.
shutdown_event = threading.Event()

order_manager = OrderManager()


def request_shutdown(signum, frame):
    """Request a graceful worker shutdown."""
    print(f"Shutdown signal received: {signum}")
    shutdown_event.set()


def install_signal_handlers():
    """Register handlers for normal termination signals."""
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def ensure_consumer_group():
    try:
        redis_client.xgroup_create(
            name=DELIVERY_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        print(f"Created consumer group: {CONSUMER_GROUP}")

    except redis.exceptions.ResponseError as error:
        if "BUSYGROUP" in str(error):
            return
        raise


def process_event(message_id, fields):
    event_type = fields.get("event_type")
    order_id = fields.get("order_id")

    try:
        data = json.loads(fields.get("data", "{}"))

        if not isinstance(data, dict):
            raise ValueError("Event data must be a JSON object")

    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print("Invalid event data:", message_id, error)
        return False

    delivery_status = data.get("status")

    print()
    print("Received delivery event")
    print("Message ID:", message_id)
    print("Event type:", event_type)
    print("Order ID:", order_id)
    print("Delivery status:", delivery_status)

    # Delivery assignment does not change order status.
    if event_type != "delivery.status_updated":
        print("Ignoring event type:", event_type)
        return True

    status_mapping = {
        "PICKED_UP": "PROCESSING",
        "IN_TRANSIT": "PROCESSING",
        "DELIVERED": "DELIVERED",
    }

    new_order_status = status_mapping.get(delivery_status)

    if new_order_status is None:
        print(
            "Ignoring unsupported delivery status:",
            delivery_status,
        )
        return True

    if not order_id:
        print("Event has no order ID; skipping.")
        return True

    db = SessionLocal()

    try:
        order, error = order_manager.update_order_status(
            db=db,
            order_id=order_id,
            new_status=new_order_status,
        )

        if error == "NOT_FOUND":
            print("Order not found:", order_id)
            return True

        if error == "INVALID_STATUS":
            print("Invalid order status:", new_order_status)
            return True

        if error == "INVALID_TRANSITION":
            print("Invalid order status transition for:", order_id)
            return True

        print(
            "Order status updated:",
            order.order_id,
            "->",
            order.status,
        )
        return True

    except Exception as error:
        db.rollback()
        print("Failed to update order status:", error)
        return False

    finally:
        db.close()


def acknowledge_event(message_id):
    acknowledged = redis_client.xack(
        DELIVERY_EVENTS_STREAM,
        CONSUMER_GROUP,
        message_id,
    )

    if acknowledged:
        print("Event acknowledged:", message_id)
    else:
        print("Event was not acknowledged:", message_id)


def handle_processing_failure(message_id, fields, error):
    try:
        result = handle_failed_message(
            redis_client=redis_client,
            stream=DELIVERY_EVENTS_STREAM,
            group=CONSUMER_GROUP,
            message_id=message_id,
            fields=fields,
            error=str(error),
        )

        if result == "retry":
            print("Order status event will be retried:", message_id)

        elif result == "dead_lettered":
            print(
                "Order status event moved to dead-letter stream:",
                message_id,
            )

        return result

    except redis.exceptions.RedisError as redis_error:
        print(
            "Failed to handle order status event failure:",
            message_id,
            redis_error,
        )
        return "pending"


def process_message(message_id, fields):
    try:
        processed = process_event(message_id, fields)

    except Exception as error:
        print(
            "Order status event processing failed:",
            message_id,
            error,
        )
        handle_processing_failure(message_id, fields, error)
        return

    if not processed:
        handle_processing_failure(
            message_id,
            fields,
            "Order status event processing returned False",
        )
        return

    try:
        acknowledge_event(message_id)

    except redis.exceptions.RedisError as error:
        print(
            "Failed to acknowledge order status event; "
            "message remains pending:",
            message_id,
            error,
        )


def recover_pending_messages():
    print(
        f"[{time.strftime('%H:%M:%S')}] "
        "Checking for stale pending delivery events..."
    )

    start_id = "0-0"

    while not shutdown_event.is_set():
        try:
            next_id, claimed_messages, deleted_ids = (
                redis_client.xautoclaim(
                    name=DELIVERY_EVENTS_STREAM,
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    min_idle_time=PENDING_IDLE_THRESHOLD_MS,
                    start_id=start_id,
                    count=CLAIM_BATCH_SIZE,
                )
            )

            if deleted_ids:
                print(
                    "Pending entries whose stream data was deleted:",
                    deleted_ids,
                )

            # Finish every message already claimed.
            for message_id, fields in claimed_messages:
                process_message(message_id, fields)

            # Stop scanning for additional batches after shutdown.
            if shutdown_event.is_set():
                break

            # Redis returns 0-0 when the scan is complete.
            if next_id == "0-0":
                break

            start_id = next_id

        except redis.exceptions.RedisError as error:
            print("Pending-message recovery failed:", error)
            raise

    print("Pending-message recovery check complete.")


def main():
    """Consume events and shut down gracefully when requested."""
    install_signal_handlers()

    # Respect a shutdown request received before startup.
    if shutdown_event.is_set():
        print("Shutdown already requested. Worker will not start.")
        return

    ensure_consumer_group()

    if shutdown_event.is_set():
        print("Shutdown requested. Skipping pending-message recovery.")
        return

    recover_pending_messages()

    if shutdown_event.is_set():
        print("Shutdown requested. Skipping new message consumption.")
        print("Order Status Worker shut down gracefully.")
        return

    print("FlowMesh Order Status Worker running...")
    print("Listening to:", DELIVERY_EVENTS_STREAM)
    print("Press Ctrl+C to shut down gracefully.")

    last_recovery_time = time.monotonic()

    try:
        while not shutdown_event.is_set():
            try:
                messages = redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={DELIVERY_EVENTS_STREAM: ">"},
                    count=10,
                    block=5000,
                )

                # Finish messages already fetched before exiting.
                for _, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        process_message(message_id, fields)

                if shutdown_event.is_set():
                    break

            except redis.exceptions.TimeoutError:
                pass

            except redis.exceptions.RedisError as error:
                print("Redis worker error:", error)

                if not shutdown_event.is_set():
                    time.sleep(2)

            except Exception as error:
                print("Unexpected worker error:", error)

                if not shutdown_event.is_set():
                    time.sleep(2)

            if shutdown_event.is_set():
                break

            if (
                time.monotonic() - last_recovery_time
                >= RECOVERY_INTERVAL_SECONDS
            ):
                try:
                    recover_pending_messages()
                except redis.exceptions.RedisError as error:
                    print("Periodic recovery failed:", error)

                last_recovery_time = time.monotonic()

            if not shutdown_event.is_set():
                time.sleep(0.1)

    finally:
        print("Order Status Worker shut down gracefully.")


if __name__ == "__main__":
    main()
