import json
import time

from lib.redis import redis_client
from lib.events import ORDER_EVENTS_STREAM


CONSUMER_GROUP = "flowmesh-workers"
CONSUMER_NAME = "order-event-worker-1"


def ensure_consumer_group():
    try:
        redis_client.xgroup_create(
            name=ORDER_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )

        print(
            f"Created consumer group: {CONSUMER_GROUP}"
        )

    except Exception as error:
        if "BUSYGROUP" in str(error):
            return

        raise


def process_event(message_id, fields):
    event_type = fields.get("event_type")
    order_id = fields.get("order_id")

    data = json.loads(
        fields.get("data", "{}")
    )

    print()
    print("Received order event")
    print("Message ID:", message_id)
    print("Event type:", event_type)
    print("Order ID:", order_id)
    print("Data:", data)
    print()


def main():
    ensure_consumer_group()

    print(
        "FlowMesh Order Event Worker running..."
    )

    print(
        f"Listening to: {ORDER_EVENTS_STREAM}"
    )

    while True:
        messages = redis_client.xreadgroup(
            groupname=CONSUMER_GROUP,
            consumername=CONSUMER_NAME,
            streams={
                ORDER_EVENTS_STREAM: ">"
            },
            count=10,
            block=5000,
        )

        for _, stream_messages in messages:
            for message_id, fields in stream_messages:
                try:
                    process_event(
                        message_id,
                        fields,
                    )

                    redis_client.xack(
                        ORDER_EVENTS_STREAM,
                        CONSUMER_GROUP,
                        message_id,
                    )

                    print(
                        "Event acknowledged:",
                        message_id,
                    )

                except Exception as error:
                    print(
                        "Event processing failed:",
                        error,
                    )

        time.sleep(0.1)


if __name__ == "__main__":
    main()