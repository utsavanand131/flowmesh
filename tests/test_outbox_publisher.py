
import json
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from workers import outbox_publisher as publisher


def make_outbox_event(
    event_id=1,
    event_type="order.created",
    aggregate_id="order_123",
    payload='{"product_id": "product_123"}',
    published=False,
):
    return MagicMock(
        event_id=event_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        payload=payload,
        published=published,
    )


# -------------------------
# Successful publishing
# -------------------------

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_publish_pending_event_success(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event()

    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = [
        event
    ]
    mock_publish.return_value = "redis-message-1"

    publisher.publish_pending_events()

    mock_publish.assert_called_once_with(
        event_type="order.created",
        order_id="order_123",
        data={"product_id": "product_123"},
    )

    assert event.published is True
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# No pending events
# -------------------------

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_publish_pending_events_when_none_exist(
    mock_session_local,
    mock_publish,
):
    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = []

    publisher.publish_pending_events()

    mock_publish.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Publishing failure
# -------------------------

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_publish_event_failure_rolls_back(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event()

    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = [
        event
    ]
    mock_publish.side_effect = RuntimeError(
        "Redis unavailable"
    )

    publisher.publish_pending_events()

    mock_publish.assert_called_once()
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Invalid JSON payload
# -------------------------

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_invalid_payload_rolls_back(
    mock_session_local,
    mock_publish,
):
    event = make_outbox_event(payload="{invalid-json")

    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = [
        event
    ]

    publisher.publish_pending_events()

    mock_publish.assert_not_called()
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    db.close.assert_called_once()


# -------------------------
# Database query failure
# -------------------------

@patch.object(publisher, "SessionLocal")
def test_database_query_failure_rolls_back_and_closes(
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

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_publishes_multiple_events(
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
        payload='{"product_id": "product_456"}',
    )

    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = [
        first_event,
        second_event,
    ]
    mock_publish.side_effect = [
        "redis-message-1",
        "redis-message-2",
    ]

    publisher.publish_pending_events()

    assert mock_publish.call_count == 2
    assert first_event.published is True
    assert second_event.published is True
    assert db.commit.call_count == 2
    db.close.assert_called_once()


# -------------------------
# Continue after one event fails
# -------------------------

@patch.object(publisher, "publish_order_event")
@patch.object(publisher, "SessionLocal")
def test_continues_after_one_event_fails(
    mock_session_local,
    mock_publish,
):
    first_event = make_outbox_event(event_id=1)
    second_event = make_outbox_event(
        event_id=2,
        aggregate_id="order_456",
    )

    db = MagicMock()
    mock_session_local.return_value = db
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.with_for_update.return_value.all.return_value = [
        first_event,
        second_event,
    ]
    mock_publish.side_effect = [
        RuntimeError("Redis unavailable"),
        "redis-message-2",
    ]

    publisher.publish_pending_events()

    assert mock_publish.call_count == 2
    assert first_event.published is False
    assert second_event.published is True
    assert db.rollback.call_count == 1
    assert db.commit.call_count == 1
    db.close.assert_called_once()
