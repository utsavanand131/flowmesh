
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import signal
import redis
from sqlalchemy.exc import SQLAlchemyError


ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from workers import delivery_event_worker as worker


@pytest.fixture
def mock_redis():
    with patch.object(worker, "redis_client") as mock:
        yield mock


@pytest.fixture
def mock_db():
    with patch.object(worker, "SessionLocal") as session_factory:
        db = MagicMock()
        session_factory.return_value = db
        yield db


@pytest.fixture
def order():
    fake_order = MagicMock()
    fake_order.order_id = "order_123"
    fake_order.status = "PENDING"
    return fake_order


# -------------------------
# Consumer group tests
# -------------------------


def test_ensure_consumer_group_creates_group(mock_redis):
    worker.ensure_consumer_group()

    mock_redis.xgroup_create.assert_called_once_with(
        name=worker.DELIVERY_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        id="0",
        mkstream=True,
    )


def test_ensure_consumer_group_ignores_existing_group(mock_redis):
    mock_redis.xgroup_create.side_effect = Exception(
        "BUSYGROUP Consumer Group name already exists"
    )

    worker.ensure_consumer_group()


def test_ensure_consumer_group_reraises_other_errors(mock_redis):
    mock_redis.xgroup_create.side_effect = RuntimeError(
        "Redis connection failed"
    )

    with pytest.raises(RuntimeError, match="Redis connection failed"):
        worker.ensure_consumer_group()


# -------------------------
# Delivery assignment tests
# -------------------------


def test_delivery_assigned_confirms_pending_order(mock_db, order):
    result = worker.handle_delivery_assigned(
        db=mock_db,
        order=order,
        order_id="order_123",
    )

    assert result is True
    assert order.status == "CONFIRMED"
    mock_db.commit.assert_called_once()


def test_delivery_assigned_does_not_commit_confirmed_order(
    mock_db, order
):
    order.status = "CONFIRMED"

    result = worker.handle_delivery_assigned(
        db=mock_db,
        order=order,
        order_id="order_123",
    )

    assert result is True
    assert order.status == "CONFIRMED"
    mock_db.commit.assert_not_called()


@pytest.mark.parametrize(
    "status",
    ["PROCESSING", "DELIVERED", "CANCELLED"],
)
def test_delivery_assigned_rejects_other_order_statuses(
    mock_db, order, status
):
    order.status = status

    result = worker.handle_delivery_assigned(
        db=mock_db,
        order=order,
        order_id="order_123",
    )

    assert result is False
    assert order.status == status
    mock_db.commit.assert_not_called()


def test_delivery_assigned_database_error_rolls_back(
    mock_db, order
):
    mock_db.commit.side_effect = SQLAlchemyError(
        "Database commit failed"
    )

    result = worker.handle_delivery_assigned(
        db=mock_db,
        order=order,
        order_id="order_123",
    )

    assert result is False
    mock_db.rollback.assert_called_once()


# -------------------------
# Delivery status tests
# -------------------------


@pytest.mark.parametrize(
    "status",
    ["PICKED_UP", "IN_TRANSIT", "DELIVERED"],
)
def test_delivery_status_updated_does_not_change_order_status(
    mock_db, order, status
):
    original_status = order.status

    result = worker.handle_delivery_status_updated(
        db=mock_db,
        order=order,
        order_id="order_123",
        data={"status": status},
    )

    assert result is True
    assert order.status == original_status
    mock_db.commit.assert_not_called()


def test_delivery_status_updated_rejects_missing_status(
    mock_db, order
):
    result = worker.handle_delivery_status_updated(
        db=mock_db,
        order=order,
        order_id="order_123",
        data={},
    )

    assert result is False
    mock_db.commit.assert_not_called()


def test_delivery_status_updated_rejects_unknown_status(
    mock_db, order
):
    result = worker.handle_delivery_status_updated(
        db=mock_db,
        order=order,
        order_id="order_123",
        data={"status": "UNKNOWN"},
    )

    assert result is False
    assert order.status == "PENDING"
    mock_db.commit.assert_not_called()


# -------------------------
# process_event tests
# -------------------------


def test_process_event_confirms_order_and_closes_session(
    mock_db, order
):
    mock_db.get.return_value = order

    result = worker.process_event(
        "message_1",
        {
            "event_type": "delivery.assigned",
            "order_id": "order_123",
            "data": "{}",
        },
    )

    assert result is True
    assert order.status == "CONFIRMED"
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()


def test_process_event_delivery_status_does_not_update_order(
    mock_db, order
):
    mock_db.get.return_value = order

    result = worker.process_event(
        "message_2",
        {
            "event_type": "delivery.status_updated",
            "order_id": "order_123",
            "data": json.dumps({"status": "DELIVERED"}),
        },
    )

    assert result is True
    assert order.status == "PENDING"
    mock_db.commit.assert_not_called()
    mock_db.close.assert_called_once()


def test_process_event_ignores_unsupported_event_type():
    with patch.object(worker, "SessionLocal") as session_factory:
        result = worker.process_event(
            "message_3",
            {
                "event_type": "order.created",
                "order_id": "order_123",
                "data": "{}",
            },
        )

        assert result is True
        session_factory.assert_not_called()


def test_process_event_missing_order_returns_false(mock_db):
    mock_db.get.return_value = None

    result = worker.process_event(
        "message_4",
        {
            "event_type": "delivery.assigned",
            "order_id": "missing_order",
            "data": "{}",
        },
    )

    assert result is False
    mock_db.commit.assert_not_called()
    mock_db.close.assert_called_once()


def test_process_event_missing_order_id_returns_false():
    result = worker.process_event(
        "message_missing_order_id",
        {
            "event_type": "delivery.assigned",
            "order_id": "",
            "data": "{}",
        },
    )

    assert result is False


def test_process_event_database_error_rolls_back_and_closes(
    mock_db,
):
    mock_db.get.side_effect = SQLAlchemyError("database failure")

    result = worker.process_event(
        "message_5",
        {
            "event_type": "delivery.assigned",
            "order_id": "order_123",
            "data": "{}",
        },
    )

    assert result is False
    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()


def test_process_event_unexpected_error_rolls_back_and_closes(
    mock_db,
):
    mock_db.get.side_effect = RuntimeError("unexpected failure")

    result = worker.process_event(
        "message_5b",
        {
            "event_type": "delivery.assigned",
            "order_id": "order_123",
            "data": "{}",
        },
    )

    assert result is False
    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()


@pytest.mark.parametrize(
    "bad_data",
    [
        "{invalid-json",
        None,
        "[]",
        '"not-an-object"',
    ],
)
def test_process_event_invalid_data_returns_false(bad_data):
    with patch.object(worker, "SessionLocal") as session_factory:
        result = worker.process_event(
            "message_6",
            {
                "event_type": "delivery.assigned",
                "order_id": "order_123",
                "data": bad_data,
            },
        )

        assert result is False
        session_factory.assert_not_called()


# -------------------------
# Main loop tests
# -------------------------


def test_main_acknowledges_successful_event(mock_redis):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.DELIVERY_EVENTS_STREAM,
                [(b"message_1", event_fields)],
            )
        ],
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "ensure_consumer_group"),
        patch.object(worker, "recover_pending_messages"),
        patch.object(
            worker,
            "process_event",
            return_value=True,
        ) as process_event,
        patch.object(worker.time, "sleep"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    process_event.assert_called_once_with(
        b"message_1",
        event_fields,
    )

    mock_redis.xack.assert_called_once_with(
        worker.DELIVERY_EVENTS_STREAM,
        worker.CONSUMER_GROUP,
        b"message_1",
    )


def test_main_does_not_acknowledge_false_result(mock_redis):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "missing_order",
        "data": "{}",
    }

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.DELIVERY_EVENTS_STREAM,
                [(b"message_2", event_fields)],
            )
        ],
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "ensure_consumer_group"),
        patch.object(worker, "recover_pending_messages"),
        patch.object(
            worker,
            "process_event",
            return_value=False,
        ),
        patch.object(worker.time, "sleep"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    mock_redis.xack.assert_not_called()


def test_main_does_not_acknowledge_processing_exception(mock_redis):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xreadgroup.side_effect = [
        [
            (
                worker.DELIVERY_EVENTS_STREAM,
                [(b"message_3", event_fields)],
            )
        ],
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "ensure_consumer_group"),
        patch.object(worker, "recover_pending_messages"),
        patch.object(
            worker,
            "process_event",
            side_effect=RuntimeError("processing failed"),
        ),
        patch.object(worker.time, "sleep"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    mock_redis.xack.assert_not_called()


def test_main_retries_after_redis_timeout(mock_redis):
    mock_redis.xreadgroup.side_effect = [
        redis.exceptions.TimeoutError("timeout"),
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "ensure_consumer_group"),
        patch.object(worker, "recover_pending_messages"),
        patch.object(worker.time, "sleep"),
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    mock_redis.xreadgroup.assert_called()


def test_main_handles_redis_worker_error(mock_redis):
    mock_redis.xreadgroup.side_effect = [
        RuntimeError("connection failed"),
        KeyboardInterrupt,
    ]

    with (
        patch.object(worker, "ensure_consumer_group"),
        patch.object(worker, "recover_pending_messages"),
        patch.object(worker.time, "sleep") as sleep,
        pytest.raises(KeyboardInterrupt),
    ):
        worker.main()

    sleep.assert_any_call(2)


# -------------------------
# Pending-message recovery tests
# -------------------------


def test_recover_pending_messages_acknowledges_success(mock_redis):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_10", event_fields)],
        [],
    )

    with patch.object(
        worker,
        "process_event",
        return_value=True,
    ) as process_event:
        worker.recover_pending_messages()

    mock_redis.xautoclaim.assert_called_once_with(
        name=worker.DELIVERY_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        consumername=worker.CONSUMER_NAME,
        min_idle_time=worker.PENDING_IDLE_THRESHOLD_MS,
        start_id="0-0",
        count=worker.CLAIM_BATCH_SIZE,
    )

    process_event.assert_called_once_with(
        "message_10",
        event_fields,
    )

    mock_redis.xack.assert_called_once_with(
        worker.DELIVERY_EVENTS_STREAM,
        worker.CONSUMER_GROUP,
        "message_10",
    )


def test_recover_pending_messages_does_not_acknowledge_false_result(
    mock_redis,
):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "missing_order",
        "data": "{}",
    }

    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_11", event_fields)],
        [],
    )

    with patch.object(
        worker,
        "process_event",
        return_value=False,
    ):
        worker.recover_pending_messages()

    mock_redis.xack.assert_not_called()


def test_recover_pending_messages_does_not_acknowledge_exception(
    mock_redis,
):
    event_fields = {
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_12", event_fields)],
        [],
    )

    with patch.object(
        worker,
        "process_event",
        side_effect=RuntimeError("processing failed"),
    ):
        worker.recover_pending_messages()

    mock_redis.xack.assert_not_called()


def test_recover_pending_messages_handles_redis_error(mock_redis):
    mock_redis.xautoclaim.side_effect = redis.exceptions.RedisError(
        "Redis unavailable"
    )

    worker.recover_pending_messages()

    mock_redis.xautoclaim.assert_called_once()


def test_recover_pending_messages_handles_invalid_response(mock_redis):
    mock_redis.xautoclaim.return_value = ()

    worker.recover_pending_messages()

    mock_redis.xack.assert_not_called()


def test_recover_pending_messages_processes_multiple_batches(
    mock_redis,
):
    first_fields = {
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    second_fields = {
        "event_type": "delivery.status_updated",
        "order_id": "order_456",
        "data": json.dumps({"status": "DELIVERED"}),
    }

    mock_redis.xautoclaim.side_effect = [
        (
            "next_cursor",
            [("message_13", first_fields)],
            [],
        ),
        (
            "0-0",
            [("message_14", second_fields)],
            [],
        ),
    ]

    with patch.object(
        worker,
        "process_event",
        return_value=True,
    ) as process_event:
        worker.recover_pending_messages()

    assert process_event.call_count == 2
    assert mock_redis.xack.call_count == 2
    assert mock_redis.xautoclaim.call_count == 2

    assert (
        mock_redis.xautoclaim.call_args_list[1].kwargs["start_id"]
        == "next_cursor"
    )

# Retry and dead-letter tests

@patch.object(worker, "handle_failed_message")
def test_handle_processing_failure_delegates_retry_policy(
    mock_handle_failed,
):
    mock_handle_failed.return_value = "retry"

    fields = {
        "event_id": "event_123",
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    worker.handle_processing_failure(
        "message_123",
        fields,
        "Temporary processing failure",
    )

    mock_handle_failed.assert_called_once_with(
        redis_client=worker.redis_client,
        stream=worker.DELIVERY_EVENTS_STREAM,
        group=worker.CONSUMER_GROUP,
        message_id="message_123",
        fields=fields,
        error="Temporary processing failure",
    )


@patch.object(worker, "handle_failed_message")
def test_handle_processing_failure_handles_dead_letter_result(
    mock_handle_failed,
):
    mock_handle_failed.return_value = "dead_lettered"

    fields = {"event_id": "event_123"}

    worker.handle_processing_failure(
        "message_123",
        fields,
        "Repeated processing failure",
    )

    mock_handle_failed.assert_called_once()


@patch.object(worker, "handle_failed_message")
def test_handle_processing_failure_handles_redis_error(
    mock_handle_failed,
):
    mock_handle_failed.side_effect = redis.exceptions.RedisError(
        "Redis unavailable"
    )

    worker.handle_processing_failure(
        "message_123",
        {"event_id": "event_123"},
        "Processing failed",
    )

    mock_handle_failed.assert_called_once()


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_acknowledges_successful_event(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = True

    worker.process_message(
        "message_123",
        {"event_id": "event_123"},
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
        "event_type": "delivery.assigned",
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
        "Database unavailable"
    )

    fields = {
        "event_id": "event_123",
        "event_type": "delivery.assigned",
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
    assert str(call_args.args[2]) == "Database unavailable"


@patch.object(worker, "handle_processing_failure")
@patch.object(worker, "process_event")
@patch.object(worker, "acknowledge_event")
def test_process_message_does_not_acknowledge_failed_event(
    mock_acknowledge,
    mock_process_event,
    mock_handle_failure,
):
    mock_process_event.return_value = False

    fields = {
        "event_id": "event_123",
        "event_type": "delivery.assigned",
        "order_id": "order_123",
        "data": "{}",
    }

    worker.process_message("message_123", fields)

    mock_acknowledge.assert_not_called()
    mock_handle_failure.assert_called_once()


@patch.object(worker, "acknowledge_event")
@patch.object(worker, "process_event")
def test_process_message_leaves_event_pending_when_ack_fails(
    mock_process_event,
    mock_acknowledge,
):
    mock_process_event.return_value = True

    mock_acknowledge.side_effect = redis.exceptions.RedisError(
        "ACK failed"
    )

    worker.process_message(
        "message_123",
        {"event_id": "event_123"},
    )

    mock_acknowledge.assert_called_once_with("message_123")

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

    mock_redis.xreadgroup.return_value = [
        (
            worker.DELIVERY_EVENTS_STREAM,
            [
                ("message_1", {"event_type": "delivery.assigned"}),
                ("message_2", {"event_type": "delivery.assigned"}),
            ],
        )
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


@patch.object(worker, "process_message")
@patch.object(worker, "redis_client")
def test_recovery_finishes_claimed_batch_before_shutdown(
    mock_redis,
    mock_process,
):
    worker.shutdown_event.clear()

    mock_redis.xautoclaim.return_value = (
        "10-0",
        [
            ("message_3", {"event_type": "delivery.assigned"}),
            ("message_4", {"event_type": "delivery.assigned"}),
        ],
        [],
    )

    def process_and_request_shutdown(message_id, fields):
        if message_id == "message_3":
            worker.shutdown_event.set()

    mock_process.side_effect = process_and_request_shutdown

    try:
        worker.recover_pending_messages()

        assert mock_process.call_count == 2
        assert mock_process.call_args_list[0].args[0] == "message_3"
        assert mock_process.call_args_list[1].args[0] == "message_4"

        # No second recovery batch should be claimed.
        mock_redis.xautoclaim.assert_called_once()

    finally:
        worker.shutdown_event.clear()
