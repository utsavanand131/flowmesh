
import json
import time

import redis
from sqlalchemy.exc import SQLAlchemyError

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
    event_type = fields.get("event_type")
    order_id = fields.get("order_id")

    data = json.loads(fields.get("data", "{}"))

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
        return

    db = SessionLocal()

    try:
        order = db.get(Order, order_id)

        if order is None:
            print(f"Order not found. Order ID: {order_id}")
            return

        print("Current order status:", order.status)

        if event_type == "delivery.assigned":
            handle_delivery_assigned(
                db=db,
                order=order,
                order_id=order_id,
            )

        elif event_type == "delivery.status_updated":
            handle_delivery_status_updated(
                db=db,
                order=order,
                order_id=order_id,
                data=data,
            )

    except SQLAlchemyError:
        db.rollback()
        print(
            "Database error while processing "
            f"delivery event for order {order_id}"
        )
        raise

    finally:
        db.close()

    print()


def handle_delivery_assigned(db, order, order_id):
    if order.status == "PENDING":
        order.status = "CONFIRMED"
        db.commit()
        print("Order status updated:", f"{order_id} -> CONFIRMED")

    elif order.status == "CONFIRMED":
        print(
            "Order already confirmed. "
            "Treating event as already processed."
        )

    else:
        print(
            "Order is not in PENDING state. "
            f"Current status: {order.status}"
        )


def handle_delivery_status_updated(db, order, order_id, data):
    delivery_status = data.get("status")

    if delivery_status is None:
        print("Delivery status missing from event.")
        return

    print("Delivery status:", delivery_status)

    if delivery_status in {"PICKED_UP", "IN_TRANSIT", "DELIVERED"}:
        print(
            "Delivery progress is handled by "
            "order_status_worker. Order status remains:",
            order.status,
        )
        return

    print("Ignoring unsupported delivery status:", delivery_status)


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
            print(f"Redis error while recovering delivery events: {error}")
            return

        except (TypeError, ValueError) as error:
            print(f"Unexpected XAUTOCLAIM response: {error}")
            return

        for message_id, fields in messages:
            try:
                process_event(message_id, fields)
                acknowledge_event(message_id)
                print(f"Recovered and acknowledged event {message_id}")

            except Exception as error:
                print(
                    f"Recovered event {message_id} failed; "
                    f"leaving it pending: {error}"
                )

        if next_id == "0-0":
            break


def main():
    ensure_consumer_group()

    # Recover eligible pending events when the worker starts.
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

            for _, stream_messages in messages:
                for message_id, fields in stream_messages:
                    try:
                        process_event(message_id, fields)
                        acknowledge_event(message_id)
                        print("Event acknowledged:", message_id)

                    except Exception as error:
                        print("Event processing failed:", error)

            now = time.monotonic()

            if now - last_recovery_time >= RECOVERY_INTERVAL_SECONDS:
                recover_pending_messages()
                last_recovery_time = now

        except redis.exceptions.TimeoutError:
            continue

        except Exception as error:
            print("Redis worker error:", error)
            time.sleep(2)

        time.sleep(0.1)


if __name__ == "__main__":
    main()
