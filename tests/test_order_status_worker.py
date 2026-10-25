
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import redis
import pytest


# -------------------------
# Import setup
# -------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ORDER_APP_PATH = (
    PROJECT_ROOT
    / "services"
    / "order_service"
    / "app"
)

order_app_path = str(ORDER_APP_PATH)

if order_app_path in sys.path:
    sys.path.remove(order_app_path)

sys.path.insert(0, order_app_path)

# Remove conflicting generic module names from other services.
sys.modules.pop("models", None)
sys.modules.pop("database", None)

from workers import order_status_worker as worker


# -------------------------
# Helpers
# -------------------------

def make_order(order_id="order_123", status="PROCESSING"):
    return MagicMock(order_id=order_id, status=status)


def delivery_event(
    event_type="delivery.status_updated",
    order_id="order_123",
    status="IN_TRANSIT",
):
    return {
        "event_type": event_type,
        "order_id": order_id,
        "data": json.dumps({"status": status}),
    }


# -------------------------
# Consumer group tests
# -------------------------

@patch.object(worker, "redis_client")
def test_ensure_consumer_group_creates_group(mock_redis):
    worker.ensure_consumer_group()

    mock_redis.xgroup_create.assert_called_once_with(
        name=worker.DELIVERY_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        id="0",
        mkstream=True,
    )


@patch.object(worker, "redis_client")
def test_ensure_consumer_group_ignores_existing_group(mock_redis):
    mock_redis.xgroup_create.side_effect = redis.exceptions.ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )

    worker.ensure_consumer_group()

    mock_redis.xgroup_create.assert_called_once()


@patch.object(worker, "redis_client")
def test_ensure_consumer_group_reraises_other_errors(mock_redis):
    mock_redis.xgroup_create.side_effect = redis.exceptions.ResponseError(
        "Permission denied"
    )

    with pytest.raises(redis.exceptions.ResponseError, match="Permission denied"):
        worker.ensure_consumer_group()


# -------------------------
# Event processing tests
# -------------------------

@pytest.mark.parametrize(
    ("delivery_status", "expected_order_status"),
    [
        ("PICKED_UP", "PROCESSING"),
        ("IN_TRANSIT", "PROCESSING"),
        ("DELIVERED", "DELIVERED"),
    ],
)
@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_maps_delivery_status(
    mock_update,
    mock_session_local,
    delivery_status,
    expected_order_status,
):
    db = MagicMock()
    mock_session_local.return_value = db
    order = make_order(status=expected_order_status)
    mock_update.return_value = (order, None)

    result = worker.process_event(
        "message_1",
        delivery_event(status=delivery_status),
    )

    assert result is True
    mock_update.assert_called_once_with(
        db=db,
        order_id="order_123",
        new_status=expected_order_status,
    )
    db.close.assert_called_once()
    db.rollback.assert_not_called()


@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_does_not_update_for_other_event_type(
    mock_update,
    mock_session_local,
):
    result = worker.process_event(
        "message_2",
        delivery_event(event_type="delivery.created"),
    )

    assert result is True
    mock_session_local.assert_not_called()
    mock_update.assert_not_called()


@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_ignores_unsupported_delivery_status(
    mock_update,
    mock_session_local,
):
    result = worker.process_event(
        "message_3",
        delivery_event(status="CANCELLED"),
    )

    assert result is True
    mock_session_local.assert_not_called()
    mock_update.assert_not_called()


@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_skips_missing_order_id(
    mock_update,
    mock_session_local,
):
    result = worker.process_event(
        "message_4",
        delivery_event(order_id=""),
    )

    assert result is True
    mock_session_local.assert_not_called()
    mock_update.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        "NOT_FOUND",
        "INVALID_STATUS",
        "INVALID_TRANSITION",
    ],
)
@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_acknowledgeable_business_errors(
    mock_update,
    mock_session_local,
    error,
):
    db = MagicMock()
    mock_session_local.return_value = db
    mock_update.return_value = (None, error)

    result = worker.process_event(
        "message_5",
        delivery_event(),
    )

    assert result is True
    db.close.assert_called_once()
    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    "bad_data",
    [
        "{invalid-json",
        None,
    ],
)
@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_invalid_data_returns_false(
    mock_update,
    mock_session_local,
    bad_data,
):
    fields = {
        "event_type": "delivery.status_updated",
        "order_id": "order_123",
        "data": bad_data,
    }

    result = worker.process_event("message_6", fields)

    assert result is False
    mock_session_local.assert_not_called()
    mock_update.assert_not_called()


@patch.object(worker, "SessionLocal")
@patch.object(worker.order_manager, "update_order_status")
def test_process_event_database_failure_rolls_back(
    mock_update,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db
    mock_update.side_effect = RuntimeError("Database failure")

    result = worker.process_event(
        "message_7",
        delivery_event(),
    )

    assert result is False
    db.rollback.assert_called_once()
    db.close.assert_called_once()


# -------------------------
# Acknowledgment tests
# -------------------------

@patch.object(worker, "redis_client")
def test_acknowledge_event_calls_xack(mock_redis):
    mock_redis.xack.return_value = 1

    worker.acknowledge_event("message_8")

    mock_redis.xack.assert_called_once_with(
        worker.DELIVERY_EVENTS_STREAM,
        worker.CONSUMER_GROUP,
        "message_8",
    )


@patch.object(worker, "redis_client")
def test_acknowledge_event_handles_unacknowledged_message(mock_redis):
    mock_redis.xack.return_value = 0

    worker.acknowledge_event("message_9")

    mock_redis.xack.assert_called_once()


# -------------------------
# Pending-message recovery
# -------------------------

@patch.object(worker, "acknowledge_event")
@patch.object(worker, "process_event", return_value=True)
@patch.object(worker, "redis_client")
def test_recovery_processes_and_acknowledges_claimed_message(
    mock_redis,
    mock_process,
    mock_acknowledge,
):
    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_10", delivery_event())],
        [],
    )

    worker.recover_pending_messages()

    mock_process.assert_called_once_with(
        "message_10",
        delivery_event(),
    )
    mock_acknowledge.assert_called_once_with("message_10")
    mock_redis.xautoclaim.assert_called_once_with(
        name=worker.DELIVERY_EVENTS_STREAM,
        groupname=worker.CONSUMER_GROUP,
        consumername=worker.CONSUMER_NAME,
        min_idle_time=worker.PENDING_IDLE_THRESHOLD_MS,
        start_id="0-0",
        count=worker.CLAIM_BATCH_SIZE,
    )


@patch.object(worker, "acknowledge_event")
@patch.object(worker, "process_event", return_value=False)
@patch.object(worker, "redis_client")
def test_recovery_leaves_failed_message_pending(
    mock_redis,
    mock_process,
    mock_acknowledge,
):
    mock_redis.xautoclaim.return_value = (
        "0-0",
        [("message_11", delivery_event())],
        [],
    )

    worker.recover_pending_messages()

    mock_process.assert_called_once()
    mock_acknowledge.assert_not_called()


@patch.object(worker, "redis_client")
def test_recovery_reraises_redis_errors(mock_redis):
    mock_redis.xautoclaim.side_effect = redis.exceptions.RedisError(
        "Redis unavailable"
    )

    with pytest.raises(redis.exceptions.RedisError, match="Redis unavailable"):
        worker.recover_pending_messages()
