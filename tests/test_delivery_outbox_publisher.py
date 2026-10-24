
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from sqlalchemy.exc import SQLAlchemyError

from workers import delivery_outbox_publisher as publisher


def make_outbox_event(
    event_id=1,
    event_type="delivery.updated",
    aggregate_id="order_123",
    payload='{"delivery_id": "delivery_123", "status": "IN_TRANSIT"}',
    published=False,
):
    return SimpleNamespace(
        event_id=event_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload,
        published=published,
    )


def make_session(events=None):
    db = MagicMock()

    query = db.query.return_value
    query.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = (
        events if events is not None else []
    )

    return db


# -------------------------
# Successful publishing
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_publish_delivery_event_success(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event()
    db = make_session([event])

    mock_session_local.return_value = db
    mock_publish.return_value = "redis-message-1"

    publisher.publish_pending_events()

    mock_publish.assert_called_once_with(
        event_type="delivery.updated",
        order_id="order_123",
        data={
            "delivery_id": "delivery_123",
            "status": "IN_TRANSIT",
        },
    )

    assert event.published is True
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Empty outbox
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_no_pending_delivery_events(
    mock_session_local,
    mock_publish,
):
    db = make_session()
    mock_session_local.return_value = db

    publisher.publish_pending_events()

    mock_publish.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Redis publishing failure
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_delivery_publish_failure_rolls_back(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event()
    db = make_session([event])

    mock_session_local.return_value = db
    mock_publish.side_effect = RuntimeError(
        "Redis unavailable"
    )

    publisher.publish_pending_events()

    assert event.published is False
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    db.close.assert_called_once()


# -------------------------
# Invalid JSON payload
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_invalid_delivery_payload_rolls_back(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event(payload="{invalid-json")
    db = make_session([event])

    mock_session_local.return_value = db

    publisher.publish_pending_events()

    mock_publish.assert_not_called()
    assert event.published is False
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    db.close.assert_called_once()


# -------------------------
# Database query failure
# -------------------------

@patch.object(publisher, "SessionLocal")
def test_delivery_database_query_failure(
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    db.query.side_effect = SQLAlchemyError(
        "Database unavailable"
    )

    publisher.publish_pending_events()

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Multiple events
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_publishes_multiple_delivery_events(
    mock_session_local,
    mock_publish,
):
    first_event = make_outbox_event(
        event_id=1,
        aggregate_id="order_123",
    )

    second_event = make_outbox_event(
        event_id=2,
        aggregate_id="order_456",
        payload='{"delivery_id": "delivery_456", "status": "DELIVERED"}',
    )

    db = make_session([first_event, second_event])
    mock_session_local.return_value = db

    mock_publish.side_effect = [
        "redis-message-1",
        "redis-message-2",
    ]

    publisher.publish_pending_events()

    assert mock_publish.call_count == 2
    assert first_event.published is True
    assert second_event.published is True
    assert db.commit.call_count == 2
    db.rollback.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Continue after event failure
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_continues_after_delivery_event_failure(
    mock_session_local,
    mock_publish,
):
    first_event = make_outbox_event(event_id=1)
    second_event = make_outbox_event(
        event_id=2,
        aggregate_id="order_456",
    )

    db = make_session([first_event, second_event])
    mock_session_local.return_value = db

    mock_publish.side_effect = [
        RuntimeError("Redis unavailable"),
        "redis-message-2",
    ]

    publisher.publish_pending_events()

    assert mock_publish.call_count == 2
    assert first_event.published is False
    assert second_event.published is True
    db.rollback.assert_called_once()
    db.commit.assert_called_once()
    db.close.assert_called_once()


# -------------------------
# Database commit failure
# -------------------------

@patch.object(publisher, "publish_delivery_event")
@patch.object(publisher, "SessionLocal")
def test_delivery_commit_failure_rolls_back(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event()
    db = make_session([event])

    mock_session_local.return_value = db
    mock_publish.return_value = "redis-message-1"

    db.commit.side_effect = SQLAlchemyError(
        "Database commit failed"
    )

    publisher.publish_pending_events()

    mock_publish.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_called_once()
    db.close.assert_called_once()
