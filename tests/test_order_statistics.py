from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.order_service.app.database import Base
from services.order_service.app.models import Order
from services.order_service.app.order_service import OrderManager


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
def order_manager():
    return OrderManager()


def test_get_order_statistics_returns_correct_counts(
    db_session,
    order_manager,
):
    orders = [
        Order(
            order_id="order_1",
            user_id="user_1",
            product_id="product_1",
            quantity=1,
            status="PENDING",
        ),
        Order(
            order_id="order_2",
            user_id="user_1",
            product_id="product_2",
            quantity=2,
            status="PENDING",
        ),
        Order(
            order_id="order_3",
            user_id="user_2",
            product_id="product_3",
            quantity=1,
            status="PROCESSING",
        ),
        Order(
            order_id="order_4",
            user_id="user_2",
            product_id="product_4",
            quantity=3,
            status="DELIVERED",
        ),
    ]

    db_session.add_all(orders)
    db_session.commit()

    statistics = order_manager.get_order_statistics(db_session)

    assert statistics == {
        "total_orders": 4,
        "pending_orders": 2,
        "confirmed_orders": 0,
        "processing_orders": 1,
        "delivered_orders": 1,
        "completion_rate": 25.0,
    }


def test_get_order_statistics_returns_zero_for_empty_database(
    db_session,
    order_manager,
):
    statistics = order_manager.get_order_statistics(db_session)

    assert statistics == {
        "total_orders": 0,
        "pending_orders": 0,
        "confirmed_orders": 0,
        "processing_orders": 0,
        "delivered_orders": 0,
        "completion_rate": 0.0,
    }


def test_order_statistics_update_after_status_change(
    db_session,
    order_manager,
):
    order = Order(
        order_id="order_5",
        user_id="user_1",
        product_id="product_5",
        quantity=1,
        status="PENDING",
    )

    db_session.add(order)
    db_session.commit()

    initial_statistics = order_manager.get_order_statistics(db_session)

    assert initial_statistics == {
        "total_orders": 1,
        "pending_orders": 1,
        "confirmed_orders": 0,
        "processing_orders": 0,
        "delivered_orders": 0,
        "completion_rate": 0.0,
    }

    updated_order, error = order_manager.update_order_status(
        db=db_session,
        order_id="order_5",
        new_status="PROCESSING",
    )

    assert error is None
    assert updated_order.status == "PROCESSING"

    updated_order, error = order_manager.update_order_status(
        db=db_session,
        order_id="order_5",
        new_status="DELIVERED",
    )

    assert error is None
    assert updated_order.status == "DELIVERED"

    final_statistics = order_manager.get_order_statistics(db_session)

    assert final_statistics == {
        "total_orders": 1,
        "pending_orders": 0,
        "confirmed_orders": 0,
        "processing_orders": 0,
        "delivered_orders": 1,
        "completion_rate": 100.0,
    }


def test_daily_order_trends_returns_correct_counts(
    db_session,
    order_manager,
):
    today = date.today()

    orders = [
        Order(
            order_id="trend_order_1",
            user_id="user_1",
            product_id="product_1",
            quantity=1,
            status="PENDING",
            created_at=datetime.combine(
                today,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
        ),
        Order(
            order_id="trend_order_2",
            user_id="user_1",
            product_id="product_2",
            quantity=1,
            status="PROCESSING",
            created_at=datetime.combine(
                today,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
        ),
        Order(
            order_id="trend_order_3",
            user_id="user_2",
            product_id="product_3",
            quantity=1,
            status="DELIVERED",
            created_at=datetime.combine(
                today - timedelta(days=1),
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
        ),
    ]

    db_session.add_all(orders)
    db_session.commit()

    trends = order_manager.get_daily_order_trends(
        db_session,
        days=3,
    )

    assert trends == [
        {
            "date": (today - timedelta(days=2)).isoformat(),
            "order_count": 0,
        },
        {
            "date": (today - timedelta(days=1)).isoformat(),
            "order_count": 1,
        },
        {
            "date": today.isoformat(),
            "order_count": 2,
        },
    ]


def test_daily_order_trends_includes_zero_order_days(
    db_session,
    order_manager,
):
    today = date.today()

    order = Order(
        order_id="trend_order_4",
        user_id="user_1",
        product_id="product_4",
        quantity=1,
        status="PENDING",
        created_at=datetime.combine(
            today,
            datetime.min.time(),
            tzinfo=timezone.utc,
        ),
    )

    db_session.add(order)
    db_session.commit()

    trends = order_manager.get_daily_order_trends(
        db_session,
        days=5,
    )

    assert len(trends) == 5
    assert trends[-1]["order_count"] == 1

    assert all(trend["order_count"] == 0 for trend in trends[:-1])


def test_daily_order_trends_returns_default_seven_days(
    db_session,
    order_manager,
):
    trends = order_manager.get_daily_order_trends(db_session)

    assert len(trends) == 7

    assert trends[0]["date"] == (date.today() - timedelta(days=6)).isoformat()

    assert trends[-1]["date"] == date.today().isoformat()

    assert all(trend["order_count"] == 0 for trend in trends)


def test_daily_order_trends_rejects_invalid_days(
    db_session,
    order_manager,
):
    with pytest.raises(ValueError, match="Days must be at least 1"):
        order_manager.get_daily_order_trends(
            db_session,
            days=0,
        )
