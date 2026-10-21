
import json
import time

import redis

from lib.events import DELIVERY_EVENTS_STREAM
from lib.redis import redis_client
from services.order_service.app.database import SessionLocal
from services.order_service.app.order_service import OrderManager


CONSUMER_GROUP = "flowmesh-order-status-workers"
CONSUMER_NAME = "order-status-worker-1"

# A message must be idle for at least 60 seconds before recovery.
PENDING_IDLE_THRESHOLD_MS = 60_000
CLAIM_BATCH_SIZE = 10
RECOVERY_INTERVAL_SECONDS = 30

order_manager = OrderManager()


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
    except (json.JSONDecodeError, TypeError) as error:
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


def recover_pending_messages():
    print(
    f"[{time.strftime('%H:%M:%S')}] "
    "Checking for stale pending delivery events..."
)

    start_id = "0-0"

    while True:
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

            for message_id, fields in claimed_messages:
                try:
                    processed = process_event(message_id, fields)

                    if processed:
                        acknowledge_event(message_id)
                    else:
                        print(
                            "Claimed event remains pending:",
                            message_id,
                        )

                except Exception as error:
                    print(
                        "Claimed event processing failed:",
                        message_id,
                        error,
                    )

            # Redis returns 0-0 when the scan is complete.
            if next_id == "0-0":
                break

            start_id = next_id

        except redis.exceptions.RedisError as error:
            print("Pending-message recovery failed:", error)
            raise

    print("Pending-message recovery check complete.")


def main():
    ensure_consumer_group()
    recover_pending_messages()

    print("FlowMesh Order Status Worker running...")
    print("Listening to:", DELIVERY_EVENTS_STREAM)

    last_recovery_time = time.monotonic()

    while True:
        try:
            messages = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={DELIVERY_EVENTS_STREAM: ">"},
                count=10,
                block=5000,
            )

            for _, stream_messages in messages:
                for message_id, fields in stream_messages:
                    try:
                        processed = process_event(message_id, fields)

                        if processed:
                            acknowledge_event(message_id)
                        else:
                            print(
                                "Event left pending for retry:",
                                message_id,
                            )

                    except Exception as error:
                        print(
                            "Event processing failed:",
                            message_id,
                            error,
                        )

        except redis.exceptions.TimeoutError:
            pass

        except redis.exceptions.RedisError as error:
            print("Redis worker error:", error)
            time.sleep(2)

        except Exception as error:
            print("Unexpected worker error:", error)
            time.sleep(2)

        if (
            time.monotonic() - last_recovery_time
            >= RECOVERY_INTERVAL_SECONDS
        ):
            try:
                recover_pending_messages()
            except redis.exceptions.RedisError as error:
                print("Periodic recovery failed:", error)

            last_recovery_time = time.monotonic()

        time.sleep(0.1)


if __name__ == "__main__":
    main()
