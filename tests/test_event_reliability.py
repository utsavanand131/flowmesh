
from unittest.mock import MagicMock

import pytest

from lib.event_reliability import (
    DEAD_LETTER_STREAM,
    MAX_DELIVERY_ATTEMPTS,
    get_delivery_attempts,
    handle_failed_message,
    publish_dead_letter,
)


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def event_fields():
    return {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": '{"product_id": "product_123"}',
    }


@pytest.mark.parametrize(
    ("delivery_count", "expected"),
    [
        (1, 1),
        (2, 2),
        (5, 5),
        (8, 8),
    ],
)
def test_get_delivery_attempts(
    mock_redis,
    delivery_count,
    expected,
):
    mock_redis.xpending_range.return_value = [
        {"times_delivered": delivery_count}
    ]

    result = get_delivery_attempts(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
    )

    assert result == delivery_count

    mock_redis.xpending_range.assert_called_once_with(
        name="flowmesh:order-events",
        groupname="flowmesh-workers",
        min="message_123",
        max="message_123",
        count=1,
    )


def test_get_delivery_attempts_returns_zero_when_not_pending(
    mock_redis,
):
    mock_redis.xpending_range.return_value = []

    result = get_delivery_attempts(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
    )

    assert result == 0


def test_publish_dead_letter_preserves_original_event(
    mock_redis,
    event_fields,
):
    mock_redis.xadd.return_value = "dead-letter-123"
    mock_redis.xack.return_value = 1

    result = publish_dead_letter(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
        fields=event_fields,
        attempts=5,
        error="Delivery service unavailable",
    )

    assert result == "dead-letter-123"

    mock_redis.xadd.assert_called_once()

    args, kwargs = mock_redis.xadd.call_args

    assert args[0] == DEAD_LETTER_STREAM

    record = args[1] if len(args) > 1 else kwargs["fields"]

    assert record["original_stream"] == "flowmesh:order-events"
    assert record["original_group"] == "flowmesh-workers"
    assert record["original_message_id"] == "message_123"
    assert record["event_id"] == "event_123"
    assert record["event_type"] == "order.created"
    assert record["attempts"] == "5"
    assert record["error"] == "Delivery service unavailable"

    mock_redis.xack.assert_called_once_with(
        "flowmesh:order-events",
        "flowmesh-workers",
        "message_123",
    )


def test_publish_dead_letter_acknowledges_only_after_xadd(
    mock_redis,
    event_fields,
):
    operations = []

    def record_xadd(*args, **kwargs):
        operations.append("xadd")
        return "dead-letter-123"

    def record_xack(*args, **kwargs):
        operations.append("xack")
        return 1

    mock_redis.xadd.side_effect = record_xadd
    mock_redis.xack.side_effect = record_xack

    publish_dead_letter(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
        fields=event_fields,
        attempts=5,
        error="Processing failed",
    )

    assert operations == ["xadd", "xack"]


def test_publish_dead_letter_does_not_ack_if_xadd_fails(
    mock_redis,
    event_fields,
):
    mock_redis.xadd.side_effect = RuntimeError(
        "Redis publication failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Redis publication failed",
    ):
        publish_dead_letter(
            redis_client=mock_redis,
            stream="flowmesh:order-events",
            group="flowmesh-workers",
            message_id="message_123",
            fields=event_fields,
            attempts=5,
            error="Processing failed",
        )

    mock_redis.xack.assert_not_called()


def test_handle_failed_message_keeps_message_pending_before_limit(
    mock_redis,
    event_fields,
):
    mock_redis.xpending_range.return_value = [
        {"times_delivered": MAX_DELIVERY_ATTEMPTS - 1}
    ]

    result = handle_failed_message(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
        fields=event_fields,
        error="Temporary failure",
    )

    assert result == "retry"
    mock_redis.xadd.assert_not_called()
    mock_redis.xack.assert_not_called()


def test_handle_failed_message_dead_letters_at_limit(
    mock_redis,
    event_fields,
):
    mock_redis.xpending_range.return_value = [
        {"times_delivered": MAX_DELIVERY_ATTEMPTS}
    ]
    mock_redis.xadd.return_value = "dead-letter-123"
    mock_redis.xack.return_value = 1

    result = handle_failed_message(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
        fields=event_fields,
        error="Permanent failure",
    )

    assert result == "dead_lettered"

    mock_redis.xadd.assert_called_once()
    mock_redis.xack.assert_called_once_with(
        "flowmesh:order-events",
        "flowmesh-workers",
        "message_123",
    )


def test_handle_failed_message_retries_when_delivery_count_is_zero(
    mock_redis,
    event_fields,
):
    mock_redis.xpending_range.return_value = []

    result = handle_failed_message(
        redis_client=mock_redis,
        stream="flowmesh:order-events",
        group="flowmesh-workers",
        message_id="message_123",
        fields=event_fields,
        error="Processing failed",
    )

    assert result == "retry"
    mock_redis.xadd.assert_not_called()
    mock_redis.xack.assert_not_called()


def test_handle_failed_message_does_not_ack_if_dead_letter_fails(
    mock_redis,
    event_fields,
):
    mock_redis.xpending_range.return_value = [
        {"times_delivered": MAX_DELIVERY_ATTEMPTS}
    ]
    mock_redis.xadd.side_effect = RuntimeError(
        "Dead-letter publication failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Dead-letter publication failed",
    ):
        handle_failed_message(
            redis_client=mock_redis,
            stream="flowmesh:order-events",
            group="flowmesh-workers",
            message_id="message_123",
            fields=event_fields,
            error="Processing failed",
        )

    mock_redis.xack.assert_not_called()
