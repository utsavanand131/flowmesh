
import json
import signal
import threading
import time

import redis

from lib.events import DELIVERY_EVENTS_STREAM
from lib.event_reliability import handle_failed_message
from lib.logger import get_logger
from lib.redis import redis_client
from services.order_service.app.database import SessionLocal
from services.order_service.app.order_service import OrderManager


logger = get_logger(__name__)

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
    logger.info(
        "Shutdown signal received",
        extra={"signal": signum},
    )
    shutdown_event.set()


def install_signal_handlers():
    """Register handlers for normal termination signals."""
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def ensure_consumer_group():
    """Create the Redis consumer group if it does not already exist."""
    try:
        redis_client.xgroup_create(
            name=DELIVERY_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )

        logger.info(
            "Created consumer group",
            extra={"consumer_group": CONSUMER_GROUP},
        )

    except redis.exceptions.ResponseError as error:
        if "BUSYGROUP" in str(error):
            return
        raise


def process_event(message_id, fields):
    """Process a delivery event and update the corresponding order."""
    event_type = fields.get("event_type")
    order_id = fields.get("order_id")
    event_id = fields.get("event_id")

    event_context = {
        "message_id": message_id,
        "event_id": event_id,
        "event_type": event_type,
        "order_id": order_id,
    }

    try:
        data = json.loads(fields.get("data", "{}"))

        if not isinstance(data, dict):
            raise ValueError("Event data must be a JSON object")

    except (json.JSONDecodeError, TypeError, ValueError):
        logger.exception(
            "Invalid delivery event data",
            extra=event_context,
        )
        return False

    delivery_status = data.get("status")

    logger.info(
        "Received delivery event",
        extra={
            **event_context,
            "delivery_status": delivery_status,
        },
    )

    # Delivery assignment does not change order status.
    if event_type != "delivery.status_updated":
        logger.info(
            "Ignoring event type",
            extra=event_context,
        )
        return True

    status_mapping = {
        "PICKED_UP": "PROCESSING",
        "IN_TRANSIT": "PROCESSING",
        "DELIVERED": "DELIVERED",
    }

    new_order_status = status_mapping.get(delivery_status)

    if new_order_status is None:
        logger.warning(
            "Ignoring unsupported delivery status",
            extra={
                **event_context,
                "delivery_status": delivery_status,
            },
        )
        return True

    if not order_id:
        logger.warning(
            "Event has no order ID; skipping",
            extra=event_context,
        )
        return True

    db = SessionLocal()

    try:
        order, error = order_manager.update_order_status(
            db=db,
            order_id=order_id,
            new_status=new_order_status,
        )

        if error == "NOT_FOUND":
            logger.warning(
                "Order not found",
                extra=event_context,
            )
            return True

        if error == "INVALID_STATUS":
            logger.warning(
                "Invalid order status",
                extra={
                    **event_context,
                    "new_order_status": new_order_status,
                },
            )
            return True

        if error == "INVALID_TRANSITION":
            logger.warning(
                "Invalid order status transition",
                extra={
                    **event_context,
                    "new_order_status": new_order_status,
                },
            )
            return True

        logger.info(
            "Order status updated",
            extra={
                **event_context,
                "new_order_status": order.status,
            },
        )
        return True

    except Exception:
        db.rollback()

        logger.exception(
            "Failed to update order status",
            extra=event_context,
        )
        return False

    finally:
        db.close()


def acknowledge_event(message_id):
    """Acknowledge a successfully processed Redis message."""
    acknowledged = redis_client.xack(
        DELIVERY_EVENTS_STREAM,
        CONSUMER_GROUP,
        message_id,
    )

    if acknowledged:
        logger.info(
            "Order status event acknowledged",
            extra={"message_id": message_id},
        )
    else:
        logger.warning(
            "Order status event was not acknowledged",
            extra={"message_id": message_id},
        )


def handle_processing_failure(message_id, fields, error):
    """Apply the shared retry and dead-letter policy to a failed event."""
    event_context = {
        "message_id": message_id,
        "event_id": fields.get("event_id"),
        "order_id": fields.get("order_id"),
    }

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
            logger.warning(
                "Order status event scheduled for retry",
                extra=event_context,
            )

        elif result == "dead_lettered":
            logger.warning(
                "Order status event moved to dead-letter stream",
                extra=event_context,
            )

        return result

    except redis.exceptions.RedisError:
        logger.exception(
            "Failed to handle order status event failure",
            extra=event_context,
        )
        return "pending"


def process_message(message_id, fields):
    """Process one message and apply ACK, retry, or dead-letter behavior."""
    event_context = {
        "message_id": message_id,
        "event_id": fields.get("event_id"),
        "order_id": fields.get("order_id"),
    }

    try:
        processed = process_event(message_id, fields)

    except Exception as error:
        logger.exception(
            "Order status event processing failed",
            extra=event_context,
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

    except redis.exceptions.RedisError:
        logger.exception(
            "Failed to acknowledge order status event; "
            "message remains pending",
            extra=event_context,
        )


def recover_pending_messages():
    """Claim and retry eligible messages left pending by a consumer."""
    logger.info("Checking for stale pending delivery events")

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
                logger.warning(
                    "Pending entries whose stream data was deleted",
                    extra={"deleted_message_ids": deleted_ids},
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

        except redis.exceptions.RedisError:
            logger.exception("Pending-message recovery failed")
            raise

    logger.info("Pending-message recovery check complete")


def main():
    """Consume events and shut down gracefully when requested."""
    install_signal_handlers()

    # Respect a shutdown request received before startup.
    if shutdown_event.is_set():
        logger.info("Shutdown already requested. Worker will not start.")
        return

    ensure_consumer_group()

    if shutdown_event.is_set():
        logger.info(
            "Shutdown requested. Skipping pending-message recovery."
        )
        return

    recover_pending_messages()

    if shutdown_event.is_set():
        logger.info(
            "Shutdown requested. Skipping new message consumption."
        )
        logger.info("Order Status Worker shut down gracefully")
        return

    logger.info(
        "Order Status Worker running",
        extra={
            "stream": DELIVERY_EVENTS_STREAM,
            "consumer_group": CONSUMER_GROUP,
            "consumer_name": CONSUMER_NAME,
        },
    )
    logger.info("Press Ctrl+C to shut down gracefully")

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

            except redis.exceptions.RedisError:
                logger.exception("Redis worker error")

                if not shutdown_event.is_set():
                    time.sleep(2)

            except Exception:
                logger.exception("Unexpected worker error")

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

                except redis.exceptions.RedisError:
                    logger.exception("Periodic recovery failed")

                last_recovery_time = time.monotonic()

            if not shutdown_event.is_set():
                time.sleep(0.1)

    finally:
        logger.info("Order Status Worker shut down gracefully")


if __name__ == "__main__":
    main()
