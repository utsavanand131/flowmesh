
import json
import time

import redis

from lib.events import ORDER_EVENTS_STREAM
from lib.redis import redis_client
from workers.delivery_client import create_delivery


CONSUMER_GROUP = "flowmesh-workers"
CONSUMER_NAME = "order-event-worker-1"

PENDING_IDLE_THRESHOLD_MS = 60_000
CLAIM_BATCH_SIZE = 10
RECOVERY_INTERVAL_SECONDS = 30


def ensure_consumer_group():
    """Create the Redis consumer group if it does not already exist."""
    try:
        redis_client.xgroup_create(
            name=ORDER_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        print(f"Created consumer group: {CONSUMER_GROUP}")

    except Exception as error:
        if "BUSYGROUP" in str(error):
            return
        raise


def process_event(message_id, fields=None):
    """Process an order event and return whether it can be acknowledged."""
    if fields is None:
        fields = message_id

    event_type = fields.get("event_type")
    order_id = fields.get("order_id")

    # Invalid JSON raises JSONDecodeError; the message must not be ACKed.
    data = json.loads(fields.get("data", "{}"))

    print(f"Received event: {event_type}")
    print(f"Message ID: {message_id}")
    print(f"Order ID: {order_id}")
    print(f"Data: {data}")

    if event_type == "order.created":
        if not order_id:
            print("Skipping order.created event without an order_id")
            return True

        # Let delivery exceptions propagate so the caller can leave
        # the message pending for retry.
        result = create_delivery(order_id=order_id)

        if isinstance(result, dict) and result.get("already_exists"):
            print(f"Delivery already exists for order {order_id}")
            return True

        if result is None:
            print(f"Could not create delivery for order {order_id}")
            return False

        print(f"Delivery created for order {order_id}")
        return True

    # Unsupported events are intentionally ignored and acknowledged.
    print(f"Ignoring unsupported event type: {event_type}")
    return True


def acknowledge_event(message_id):
    """Acknowledge a successfully processed message."""
    redis_client.xack(
        ORDER_EVENTS_STREAM,
        CONSUMER_GROUP,
        message_id,
    )


def recover_pending_messages():
    """Claim and retry messages left pending by previous consumers."""
    print("Checking for pending order events...")

    next_id = "0-0"

    while True:
        try:
            response = redis_client.xautoclaim(
                name=ORDER_EVENTS_STREAM,
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                min_idle_time=PENDING_IDLE_THRESHOLD_MS,
                start_id=next_id,
                count=CLAIM_BATCH_SIZE,
            )

            # redis-py returns (next_start_id, messages, deleted_ids).
            next_id, messages, _deleted_ids = response

        except redis.exceptions.RedisError as error:
            print(f"Redis error while recovering pending events: {error}")
            return

        except (TypeError, ValueError) as error:
            print(f"Unexpected XAUTOCLAIM response: {error}")
            return

        for message_id, fields in messages:
            try:
                processed = process_event(message_id, fields)

                if processed:
                    acknowledge_event(message_id)
                    print(f"Recovered and acknowledged event {message_id}")
                else:
                    print(
                        f"Recovered event {message_id} failed; "
                        "leaving it pending"
                    )

            except Exception as error:
                print(
                    f"Error processing recovered event {message_id}: {error}"
                )

        if next_id == "0-0":
            break


def main():
    """Consume new events and periodically recover pending messages."""
    ensure_consumer_group()

    # Retry eligible pending messages when the worker starts.
    recover_pending_messages()
    last_recovery_time = time.monotonic()

    print("Order event worker is running...")

    while True:
        try:
            response = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={ORDER_EVENTS_STREAM: ">"},
                count=10,
                block=5000,
            )

            for _stream_name, messages in response:
                for message_id, fields in messages:
                    try:
                        processed = process_event(message_id, fields)

                        if processed:
                            acknowledge_event(message_id)
                            print(f"Acknowledged event {message_id}")
                        else:
                            print(
                                f"Event {message_id} failed; "
                                "leaving it pending for recovery"
                            )

                    except Exception as error:
                        # Do not ACK events that failed processing.
                        print(f"Error processing event {message_id}: {error}")

            now = time.monotonic()

            if now - last_recovery_time >= RECOVERY_INTERVAL_SECONDS:
                recover_pending_messages()
                last_recovery_time = now

        except redis.exceptions.TimeoutError:
            print("Redis read timed out; retrying...")

        except redis.exceptions.RedisError as error:
            print(f"Redis error in order event worker: {error}")
            time.sleep(2)


if __name__ == "__main__":
    main()
