
from unittest.mock import patch

from lib import events


@patch.object(events, "redis_client")
def test_publish_order_event_includes_event_id(mock_redis):
    mock_redis.xadd.return_value = "redis-message-1"

    result = events.publish_order_event(
        event_id="event-123",
        event_type="order.created",
        order_id="order-123",
        data={"product_id": "product-123"},
    )

    assert result == "redis-message-1"

    mock_redis.xadd.assert_called_once_with(
        events.ORDER_EVENTS_STREAM,
        {
            "event_id": "event-123",
            "event_type": "order.created",
            "order_id": "order-123",
            "data": '{"product_id": "product-123"}',
        },
    )


@patch.object(events, "redis_client")
def test_publish_delivery_event_includes_event_id(mock_redis):
    mock_redis.xadd.return_value = "redis-message-2"

    result = events.publish_delivery_event(
        event_id="event-456",
        event_type="delivery.assigned",
        order_id="order-456",
        data={
            "delivery_id": "delivery-456",
            "status": "ASSIGNED",
        },
    )

    assert result == "redis-message-2"

    mock_redis.xadd.assert_called_once_with(
        events.DELIVERY_EVENTS_STREAM,
        {
            "event_id": "event-456",
            "event_type": "delivery.assigned",
            "order_id": "order-456",
            "data": (
                '{"delivery_id": "delivery-456", '
                '"status": "ASSIGNED"}'
            ),
        },
    )
