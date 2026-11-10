
import json
from unittest.mock import patch

import pytest

from workers import order_event_worker as worker

import signal

# ensure_consumer_group tests

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
        "status": "ASSIGNED",
    }

    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": json.dumps({"product_id": "product_123"}),
    }

    result = worker.process_event("message_1", fields)

    assert result is True

    mock_create_delivery.assert_called_once_with(
        order_id="order_123",
        event_id="event_123",
    )


@patch.object(worker, "create_delivery")
def test_process_order_created_event_handles_existing_delivery(
    mock_create_delivery,
):
    mock_create_delivery.return_value = {
        "already_exists": True,
        "status": "ALREADY_EXISTS",
    }

    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    result = worker.process_event("message_2", fields)

    assert result is True

    mock_create_delivery.assert_called_once_with(
        order_id="order_123",
        event_id="event_123",
    )


@patch.object(worker, "create_delivery")
def test_process_order_created_event_rejects_missing_event_id(
    mock_create_delivery,
):
    fields = {
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    result = worker.process_event("message_3", fields)

    assert result is False
    mock_create_delivery.assert_not_called()


@patch.object(worker, "create_delivery")
def test_process_unknown_event_does_not_create_delivery(
    mock_create_delivery,
):
    fields = {
        "event_type": "order.cancelled",
        "order_id": "order_123",
        "data": "{}",
    }

    result = worker.process_event("message_4", fields)

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
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    with pytest.raises(
        RuntimeError,
        match="Delivery service unavailable",
    ):
        worker.process_event("message_5", fields)

    mock_create_delivery.assert_called_once_with(
        order_id="order_123",
        event_id="event_123",
    )


def test_process_event_rejects_invalid_json():
    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{invalid-json",
    }

    result = worker.process_event("message_6", fields)

    assert result is False


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
        "event_id": "event_123",
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
@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_does_not_acknowledge_failed_event(
    mock_redis,
    mock_ensure_group,
    mock_process_event,
    mock_handle_failure,
    mock_sleep,
):
    mock_process_event.side_effect = RuntimeError(
        "Delivery service unavailable"
    )

    event_fields = {
        "event_id": "event_123",
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

    mock_handle_failure.assert_called_once()
    mock_redis.xack.assert_not_called()

# pending-message recovery tests

@patch.object(worker, "acknowledge_event")
@patch.object(worker, "process_event")
@patch.object(worker, "redis_client")
def test_recover_pending_messages_processes_and_acknowledges_event(
    mock_redis,
    mock_process_event,
    mock_acknowledge,
):
    mock_process_event.return_value = True

    event_fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xautoclaim.side_effect = [
        ("0-0", [("message_10", event_fields)], []),
    ]

    worker.recover_pending_messages()

    mock_redis.xautoclaim.assert_called_once_with(
        name=worker.ORDER_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        consumername=worker.CONSUMER_NAME,
        min_idle_time=worker.PENDING_IDLE_THRESHOLD_MS,
        start_id="0-0",
        count=worker.CLAIM_BATCH_SIZE,
    )

    mock_process_event.assert_called_once_with(
        "message_10",
        event_fields,
    )

    mock_acknowledge.assert_called_once_with("message_10")


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "redis_client")
def test_recover_pending_messages_does_not_acknowledge_failed_event(
    mock_redis,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = False

    event_fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_11", event_fields)],
        [],
    )

    worker.recover_pending_messages()

    mock_process_event.assert_called_once_with(
        "message_11",
        event_fields,
    )

    mock_handle_failure.assert_called_once()
    mock_redis.xack.assert_not_called()


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "redis_client")
def test_recover_pending_messages_leaves_exception_event_pending(
    mock_redis,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.side_effect = RuntimeError(
        "Delivery service unavailable"
    )

    event_fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_12", event_fields)],
        [],
    )

    worker.recover_pending_messages()

    mock_process_event.assert_called_once_with(
        "message_12",
        event_fields,
    )

    mock_handle_failure.assert_called_once()
    mock_redis.xack.assert_not_called()


@patch.object(worker, "redis_client")
def test_recover_pending_messages_handles_redis_error(mock_redis):
    import redis

    mock_redis.xautoclaim.side_effect = redis.exceptions.RedisError(
        "Redis unavailable"
    )

    worker.recover_pending_messages()

    mock_redis.xautoclaim.assert_called_once()

# process_message tests


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_acknowledges_success(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = True

    worker.process_message(
        "message_123",
        {"event_type": "order.created"},
    )

    mock_acknowledge.assert_called_once_with("message_123")
    mock_handle_failure.assert_not_called()


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_retries_failed_event(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = False

    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    worker.process_message("message_123", fields)

    mock_acknowledge.assert_not_called()

    mock_handle_failure.assert_called_once_with(
        "message_123",
        fields,
        "Event processing returned False",
    )


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_handles_processing_exception(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.side_effect = RuntimeError(
        "Delivery unavailable"
    )

    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    worker.process_message("message_123", fields)

    mock_acknowledge.assert_not_called()

    mock_handle_failure.assert_called_once()

    call_args = mock_handle_failure.call_args

    assert call_args.args[0] == "message_123"
    assert call_args.args[1] == fields
    assert isinstance(call_args.args[2], RuntimeError)
    assert str(call_args.args[2]) == "Delivery unavailable"


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_does_not_ack_failed_dead_letter_publication(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = False

    fields = {
        "event_id": "event_123",
        "event_type": "order.created",
        "order_id": "order_123",
        "data": "{}",
    }

    worker.process_message("message_123", fields)

    mock_acknowledge.assert_not_called()

    mock_handle_failure.assert_called_once_with(
        "message_123",
        fields,
        "Event processing returned False",
    )

# Graceful shutdown tests

def test_request_shutdown_sets_shutdown_event():
    worker.shutdown_event.clear()

    worker.request_shutdown(None, None)

    assert worker.shutdown_event.is_set()

    worker.shutdown_event.clear()


@patch.object(worker.signal, "signal")
def test_install_signal_handlers_registers_sigint_and_sigterm(
    mock_signal,
):
    worker.install_signal_handlers()

    assert mock_signal.call_count == 2

    registered_signals = [
        call.args[0] for call in mock_signal.call_args_list
    ]

    assert signal.SIGINT in registered_signals
    assert signal.SIGTERM in registered_signals

    for call in mock_signal.call_args_list:
        assert call.args[1] == worker.request_shutdown


@patch.object(worker, "process_message")
@patch.object(worker, "recover_pending_messages")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_finishes_fetched_batch_before_shutdown(
    mock_redis,
    mock_ensure_group,
    mock_recover,
    mock_process,
):
    worker.shutdown_event.clear()

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.ORDER_EVENTS_STREAM,
                [
                    ("message_1", {"event_type": "order.created"}),
                    ("message_2", {"event_type": "order.created"}),
                ],
            )
        ]
    ]

    def process_and_request_shutdown(message_id, fields):
        if message_id == "message_1":
            worker.shutdown_event.set()

    mock_process.side_effect = process_and_request_shutdown

    try:
        worker.main()

        assert mock_process.call_count == 2
        assert mock_process.call_args_list[0].args[0] == "message_1"
        assert mock_process.call_args_list[1].args[0] == "message_2"
        mock_redis.xreadgroup.assert_called_once()

    finally:
        worker.shutdown_event.clear()


@patch.object(worker, "process_message")
@patch.object(worker, "recover_pending_messages")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_does_not_read_messages_when_shutdown_already_requested(
    mock_redis,
    mock_ensure_group,
    mock_recover,
    mock_process,
):
    worker.shutdown_event.set()

    try:
        worker.main()

        mock_redis.xreadgroup.assert_not_called()
        mock_process.assert_not_called()
        mock_recover.assert_not_called()

    finally:
        worker.shutdown_event.clear()


@patch.object(worker, "recover_pending_messages")
@patch.object(worker, "ensure_consumer_group")
@patch.object(worker, "redis_client")
def test_main_exits_cleanly_after_empty_read_and_shutdown(
    mock_redis,
    mock_ensure_group,
    mock_recover,
):
    worker.shutdown_event.clear()

    def read_and_request_shutdown(**kwargs):
        worker.shutdown_event.set()
        return []

    mock_redis.xreadgroup.side_effect = read_and_request_shutdown

    try:
        worker.main()

        mock_redis.xreadgroup.assert_called_once()

    finally:
        worker.shutdown_event.clear()
