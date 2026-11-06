
import json

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.delivery_service.app.database import Base
from services.delivery_service.app.models import (
    Delivery,
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

    delivery_count = db_session.scalar(
        select(func.count()).select_from(Delivery)
    )

    outbox_count = db_session.scalar(
        select(func.count()).select_from(OutboxEvent)
    )

    processed_event_count = db_session.scalar(
        select(func.count()).select_from(ProcessedEvent)
    )

    assert delivery_count == 1
    assert outbox_count == 1
    assert processed_event_count == 1


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

    db_session.expire_all()

    assert db_session.get(
        ProcessedEvent,
        "event_456",
    ) is not None

    assert db_session.query(Delivery).filter_by(
        order_id="order_456"
    ).first() is not None


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
