
import json
from unittest.mock import patch

import pytest

from workers import order_event_worker as worker


# -------------------------
# ensure_consumer_group tests
# -------------------------

@patch.object(worker, "redis_client")
def test_ensure_consumer_group_creates_group(mock_redis):
    worker.ensure_consumer_group()

    mock_redis.xgroup_create.assert_called_once_with(
        name=worker.ORDER_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        id="0",
        mkstream=True,
    )


@patch.object(worker, "redis_client")
def test_ensure_consumer_group_ignores_existing_group(mock_redis):
    mock_redis.xgroup_create.side_effect = Exception(
        "BUSYGROUP Consumer Group name already exists"
    )

    worker.ensure_consumer_group()

    mock_redis.xgroup_create.assert_called_once()


@patch.object(worker, "redis_client")
def test_ensure_consumer_group_reraises_other_errors(mock_redis):
    mock_redis.xgroup_create.side_effect = Exception(
        "Redis connection failed"
    )

    with pytest.raises(Exception, match="Redis connection failed"):
        worker.ensure_consumer_group()


# -------------------------
# process_event tests
# -------------------------

@patch.object(worker, "create_delivery")
def test_process_order_created_event_creates_delivery(mock_create_delivery):
    mock_create_delivery.return_value = {
        "delivery_id": "delivery_123",
        "already_exists": False,
    }

    fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": json.dumps({"product_id": "product_123"}),
    }

    result = worker.process_event("message_1", fields)

    assert result is True
    mock_create_delivery.assert_called_once_with(
        order_id="order_123"
    )


@patch.object(worker, "create_delivery")
def test_process_order_created_event_handles_existing_delivery(
    mock_create_delivery,
):
    mock_create_delivery.return_value = {
        "delivery_id": "delivery_123",
        "already_exists": True,
    }

    fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    result = worker.process_event("message_2", fields)

    assert result is True
    mock_create_delivery.assert_called_once_with(
        order_id="order_123"
    )


@patch.object(worker, "create_delivery")
def test_process_unknown_event_does_not_create_delivery(
    mock_create_delivery,
):
    fields = {
        "event_type": "order.cancelled",
        "order_id": "order_123",
        "data": "{}",
    }

    result = worker.process_event("message_3", fields)

    assert result is True
    mock_create_delivery.assert_not_called()


@patch.object(worker, "create_delivery")
def test_process_event_propagates_delivery_failure(
    mock_create_delivery,
):
    mock_create_delivery.side_effect = RuntimeError(
        "Delivery service unavailable"
    )

    fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    with pytest.raises(
        RuntimeError,
        match="Delivery service unavailable",
    ):
        worker.process_event("message_4", fields)

    mock_create_delivery.assert_called_once_with(
        order_id="order_123"
    )


def test_process_event_rejects_invalid_json():
    fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{invalid-json",
    }

    with pytest.raises(json.JSONDecodeError):
        worker.process_event("message_5", fields)


# -------------------------
# main loop acknowledgment tests
# -------------------------

@patch.object(worker.time, "sleep")
@patch.object(worker, "process_event")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_acknowledges_successfully_processed_event(
    mock_redis,
    mock_ensure_group,
    mock_process_event,
    mock_sleep,
):
    mock_process_event.return_value = True

    event_fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.ORDER_EVENTS_STREAM,
                [("message_1", event_fields)],
            )
        ],
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "recover_pending_messages"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    mock_process_event.assert_called_once_with(
        "message_1",
        event_fields,
    )

    mock_redis.xack.assert_called_once_with(
        worker.ORDER_EVENTS_STREAM,
        worker.CONSUMER_GROUP,
        "message_1",
    )


@patch.object(worker.time, "sleep")
@patch.object(worker, "process_event")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_does_not_acknowledge_failed_event(
    mock_redis,
    mock_ensure_group,
    mock_process_event,
    mock_sleep,
):
    mock_process_event.side_effect = RuntimeError(
        "Delivery service unavailable"
    )

    event_fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.ORDER_EVENTS_STREAM,
                [("message_2", event_fields)],
            )
        ],
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "recover_pending_messages"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    mock_process_event.assert_called_once_with(
        "message_2",
        event_fields,
    )

    mock_redis.xack.assert_not_called()
