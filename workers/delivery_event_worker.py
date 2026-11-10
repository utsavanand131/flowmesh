
import json
import time

import redis
from sqlalchemy.exc import SQLAlchemyError

from lib.event_reliability import handle_failed_message
from lib.redis import redis_client
from services.order_service.app.database import SessionLocal
from services.order_service.app.models import Order


DELIVERY_EVENTS_STREAM = "flowmesh:delivery-events"

CONSUMER_GROUP = "flowmesh-order-workers"
CONSUMER_NAME = "delivery-event-worker-1"

PENDING_IDLE_THRESHOLD_MS = 60_000
CLAIM_BATCH_SIZE = 10
RECOVERY_INTERVAL_SECONDS = 30


def ensure_consumer_group():
    """Create the Redis consumer group if it does not already exist."""
    try:
        redis_client.xgroup_create(
            name=DELIVERY_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )

        print(f"Created consumer group: {CONSUMER_GROUP}")

    except Exception as error:
        if "BUSYGROUP" in str(error):
            return
        raise


def process_event(message_id, fields):
    """Process a delivery event and return whether it can be acknowledged."""
    event_type = fields.get("event_type")
    order_id = fields.get("order_id")

    try:
        data = json.loads(fields.get("data", "{}"))

        if not isinstance(data, dict):
            raise ValueError("Event data must be a JSON object")

    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print("Invalid event data:", message_id, error)
        return False

    print()
    print("Received delivery event")
    print("Message ID:", message_id)
    print("Event type:", event_type)
    print("Order ID:", order_id)
    print("Data:", data)

    if event_type not in {
        "delivery.assigned",
        "delivery.status_updated",
    }:
        print("Ignoring unsupported delivery event:", event_type)
        return True

    if not order_id:
        print("Delivery event is missing order_id:", message_id)
        return False

    db = SessionLocal()

    try:
        order = db.get(Order, order_id)

        if order is None:
            print(f"Order not found. Order ID: {order_id}")
            return False

        print("Current order status:", order.status)

        if event_type == "delivery.assigned":
            return handle_delivery_assigned(
                db=db,
                order=order,
                order_id=order_id,
            )

        if event_type == "delivery.status_updated":
            return handle_delivery_status_updated(
                db=db,
                order=order,
                order_id=order_id,
                data=data,
            )

        return True

    except SQLAlchemyError as error:
        db.rollback()

        print(
            "Database error while processing "
            f"delivery event for order {order_id}: {error}"
        )

        return False

    except Exception as error:
        db.rollback()

        print(
            f"Unexpected error processing delivery event "
            f"for order {order_id}: {error}"
        )

        return False

    finally:
        db.close()


def handle_delivery_assigned(db, order, order_id):
    """Confirm an order when its delivery has been assigned."""
    if order.status == "PENDING":
        order.status = "CONFIRMED"

        try:
            db.commit()
            print("Order status updated:", f"{order_id} -> CONFIRMED")
            return True

        except SQLAlchemyError as error:
            db.rollback()
            print("Failed to confirm order:", error)
            return False

    if order.status == "CONFIRMED":
        print(
            "Order already confirmed. "
            "Treating event as already processed."
        )
        return True

    print(
        "Order is not in PENDING state. "
        f"Current status: {order.status}"
    )

    # The event cannot currently be applied.
    return False


def handle_delivery_status_updated(db, order, order_id, data):
    """Validate delivery progress without changing the order status."""
    delivery_status = data.get("status")

    if delivery_status is None:
        print("Delivery status missing from event.")
        return False

    print("Delivery status:", delivery_status)

    if delivery_status in {"PICKED_UP", "IN_TRANSIT", "DELIVERED"}:
        print(
            "Delivery progress is handled by "
            "order_status_worker. Order status remains:",
            order.status,
        )
        return True

    print("Unsupported delivery status:", delivery_status)
    return False


def acknowledge_event(message_id):
    """Acknowledge a successfully processed Redis message."""
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
    """Apply the shared retry and dead-letter policy to a failed event."""
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
            print(f"Delivery event {message_id} will be retried.")

        elif result == "dead_lettered":
            print(
                f"Delivery event {message_id} "
                "moved to dead-letter stream."
            )

    except redis.exceptions.RedisError as redis_error:
        print(
            f"Could not apply retry policy to delivery event "
            f"{message_id}: {redis_error}"
        )


def process_message(message_id, fields):
    """Process one message and apply ACK, retry, or dead-letter behavior."""
    try:
        processed = process_event(message_id, fields)

    except Exception as error:
        print(
            f"Error processing delivery event {message_id}: {error}"
        )

        handle_processing_failure(
            message_id,
            fields,
            error,
        )
        return

    if not processed:
        handle_processing_failure(
            message_id,
            fields,
            "Event processing returned False",
        )
        return

    try:
        acknowledge_event(message_id)

    except redis.exceptions.RedisError as error:
        # Processing succeeded, but ACK failed.
        # Leave the message pending for recovery.
        print(
            f"Could not acknowledge delivery event "
            f"{message_id}: {error}"
        )


def recover_pending_messages():
    """Claim and retry eligible messages left pending by a consumer."""
    print("Checking for pending delivery events...")

    next_id = "0-0"

    while True:
        try:
            response = redis_client.xautoclaim(
                name=DELIVERY_EVENTS_STREAM,
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                min_idle_time=PENDING_IDLE_THRESHOLD_MS,
                start_id=next_id,
                count=CLAIM_BATCH_SIZE,
            )

            next_id, messages, _deleted_ids = response

        except redis.exceptions.RedisError as error:
            print(
                f"Redis error while recovering delivery events: {error}"
            )
            return

        except (TypeError, ValueError) as error:
            print(f"Unexpected XAUTOCLAIM response: {error}")
            return

        for message_id, fields in messages:
            process_message(message_id, fields)

        if next_id == "0-0":
            break


def main():
    """Consume new events and periodically recover pending messages."""
    ensure_consumer_group()

    recover_pending_messages()
    last_recovery_time = time.monotonic()

    print("FlowMesh Delivery Event Worker running...")
    print(f"Listening to: {DELIVERY_EVENTS_STREAM}")

    while True:
        try:
            messages = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={DELIVERY_EVENTS_STREAM: ">"},
                count=10,
                block=5000,
            )

            for _stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    process_message(message_id, fields)

            now = time.monotonic()

            if now - last_recovery_time >= RECOVERY_INTERVAL_SECONDS:
                recover_pending_messages()
                last_recovery_time = now

        except redis.exceptions.TimeoutError:
            continue

        except redis.exceptions.RedisError as error:
            print("Redis worker error:", error)
            time.sleep(2)

        except Exception as error:
            print("Unexpected worker error:", error)
            time.sleep(2)

        time.sleep(0.1)


if __name__ == "__main__":
    main()
