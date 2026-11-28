import json

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

from services.delivery_service.app.database import Base
from services.delivery_service.app.models import (
    Delivery,
    DeliveryStatusHistory,
    OutboxEvent,
    ProcessedEvent,
)
from services.delivery_service.app.delivery_service import DeliveryManager


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def delivery_manager():
    return DeliveryManager()


def test_create_delivery_creates_delivery_and_records_event(
    db_session,
    delivery_manager,
):
    delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="order_123",
        event_id="event_123",
    )

    assert delivery is not None
    assert delivery.order_id == "order_123"
    assert delivery.status == "ASSIGNED"

    processed_event = db_session.get(
        ProcessedEvent,
        "event_123",
    )

    assert processed_event is not None
    assert processed_event.event_type == "order.created"
    assert processed_event.aggregate_id == "order_123"

    outbox_events = db_session.query(OutboxEvent).all()

    assert len(outbox_events) == 1
    assert outbox_events[0].event_type == "delivery.assigned"
    assert outbox_events[0].aggregate_id == "order_123"
    assert outbox_events[0].published is False

    payload = json.loads(outbox_events[0].payload)

    assert payload["delivery_id"] == delivery.delivery_id
    assert payload["status"] == "ASSIGNED"

    # Verify the initial delivery status was recorded.
    history = (
        db_session.query(DeliveryStatusHistory)
        .filter_by(delivery_id=delivery.delivery_id)
        .all()
    )

    assert len(history) == 1
    assert history[0].previous_status is None
    assert history[0].new_status == "ASSIGNED"
    assert history[0].changed_at is not None


def test_duplicate_event_does_not_create_another_delivery(
    db_session,
    delivery_manager,
):
    first_delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="order_123",
        event_id="event_123",
    )

    second_delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="order_123",
        event_id="event_123",
    )

    assert first_delivery is not None
    assert second_delivery is not None

    assert second_delivery.delivery_id == first_delivery.delivery_id

    delivery_count = db_session.scalar(select(func.count()).select_from(Delivery))

    outbox_count = db_session.scalar(select(func.count()).select_from(OutboxEvent))

    processed_event_count = db_session.scalar(
        select(func.count()).select_from(ProcessedEvent)
    )

    history_count = db_session.scalar(
        select(func.count()).select_from(DeliveryStatusHistory)
    )

    assert delivery_count == 1
    assert outbox_count == 1
    assert processed_event_count == 1
    assert history_count == 1


def test_delivery_processed_event_and_outbox_are_committed_together(
    db_session,
    delivery_manager,
):
    delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="order_456",
        event_id="event_456",
    )

    assert delivery is not None

    assert db_session.query(Delivery).count() == 1
    assert db_session.query(ProcessedEvent).count() == 1
    assert db_session.query(OutboxEvent).count() == 1
    assert db_session.query(DeliveryStatusHistory).count() == 1

    db_session.expire_all()

    assert (
        db_session.get(
            ProcessedEvent,
            "event_456",
        )
        is not None
    )

    assert (
        db_session.query(Delivery).filter_by(order_id="order_456").first() is not None
    )


def test_delivery_status_update_records_history(
    db_session,
    delivery_manager,
):
    delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="order_789",
        event_id="event_789",
    )

    assert delivery is not None

    updated_delivery, error = delivery_manager.update_delivery_status(
        db=db_session,
        delivery_id=delivery.delivery_id,
        new_status="PICKED_UP",
    )

    assert error is None
    assert updated_delivery is not None
    assert updated_delivery.status == "PICKED_UP"

    history = (
        db_session.query(DeliveryStatusHistory)
        .filter_by(delivery_id=delivery.delivery_id)
        .order_by(DeliveryStatusHistory.changed_at)
        .all()
    )

    assert len(history) == 2

    assert history[0].previous_status is None
    assert history[0].new_status == "ASSIGNED"
    assert history[0].changed_at is not None

    assert history[1].previous_status == "ASSIGNED"
    assert history[1].new_status == "PICKED_UP"
    assert history[1].changed_at is not None


def test_failed_transaction_rolls_back_all_records(
    db_session,
    delivery_manager,
    monkeypatch,
):
    def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        db_session,
        "commit",
        fail_commit,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated database failure",
    ):
        delivery_manager.create_delivery(
            db=db_session,
            order_id="order_789",
            event_id="event_789",
        )

    assert db_session.query(Delivery).count() == 0
    assert db_session.query(ProcessedEvent).count() == 0
    assert db_session.query(OutboxEvent).count() == 0
    assert db_session.query(DeliveryStatusHistory).count() == 0


def test_delivery_analytics_tracks_created_and_delivered(
    db_session,
    delivery_manager,
):
    delivery = delivery_manager.create_delivery(
        db=db_session,
        order_id="analytics_order_1",
        event_id="analytics_event_1",
    )

    assert delivery is not None

    # Complete the valid delivery lifecycle.
    for status in ("PICKED_UP", "IN_TRANSIT", "DELIVERED"):
        updated_delivery, error = delivery_manager.update_delivery_status(
            db=db_session,
            delivery_id=delivery.delivery_id,
            new_status=status,
        )

        assert error is None
        assert updated_delivery.status == status

    analytics = delivery_manager.get_delivery_analytics(
        db=db_session,
        days=7,
    )

    assert analytics["days"] == 7
    assert analytics["total_created"] == 1
    assert analytics["total_delivered"] == 1
    assert analytics["average_turnaround_hours"] >= 0

    assert len(analytics["daily_analytics"]) == 7

    today = datetime.now(timezone.utc).date().isoformat()
    today_data = analytics["daily_analytics"][-1]

    assert today_data["date"] == today
    assert today_data["created_count"] == 1
    assert today_data["delivered_count"] == 1
    assert today_data["backlog_count"] == 0


def test_delivery_analytics_returns_empty_period_data(
    db_session,
    delivery_manager,
):
    analytics = delivery_manager.get_delivery_analytics(
        db=db_session,
        days=7,
    )

    assert analytics["days"] == 7
    assert analytics["total_created"] == 0
    assert analytics["total_delivered"] == 0
    assert analytics["average_turnaround_hours"] == 0.0
    assert len(analytics["daily_analytics"]) == 7

    for day in analytics["daily_analytics"]:
        assert day["created_count"] == 0
        assert day["delivered_count"] == 0
        assert day["backlog_count"] == 0


def test_delivery_analytics_rejects_unsupported_period(
    db_session,
    delivery_manager,
):
    with pytest.raises(ValueError, match="days must be 7, 14, or 30"):
        delivery_manager.get_delivery_analytics(
            db=db_session,
            days=10,
        )
