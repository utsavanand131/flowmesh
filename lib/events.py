import json
from typing import Any

from lib.redis import redis_client


ORDER_EVENTS_STREAM = "flowmesh:order-events"
DELIVERY_EVENTS_STREAM = "flowmesh:delivery-events"


def publish_order_event(
    event_type: str,
    order_id: str,
    data: dict[str, Any],
):
    event = {
        "event_type": event_type,
        "order_id": order_id,
        "data": json.dumps(data),
    }

    message_id = redis_client.xadd(
        ORDER_EVENTS_STREAM,
        event,
    )

    return message_id


def publish_delivery_event(
    event_type: str,
    order_id: str,
    data: dict[str, Any],
):
    event = {
        "event_type": event_type,
        "order_id": order_id,
        "data": json.dumps(data),
    }

    message_id = redis_client.xadd(
        DELIVERY_EVENTS_STREAM,
        event,
    )

    return message_id