from unittest.mock import MagicMock, patch

import grpc

from services.order_service.app import order_pb2
from services.order_service.app.grpc_server import OrderService
from sqlalchemy.exc import SQLAlchemyError


def create_context():
    return MagicMock()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_daily_order_trends_returns_trends(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_daily_order_trends.return_value = [
        {
            "date": "2026-11-24",
            "order_count": 3,
        },
        {
            "date": "2026-11-25",
            "order_count": 5,
        },
        {
            "date": "2026-11-26",
            "order_count": 2,
        },
    ]

    service = OrderService()
    context = create_context()

    response = service.GetDailyOrderTrends(
        order_pb2.GetDailyOrderTrendsRequest(days=3),
        context,
    )

    assert len(response.trends) == 3

    assert response.trends[0].date == "2026-11-24"
    assert response.trends[0].order_count == 3

    assert response.trends[1].date == "2026-11-25"
    assert response.trends[1].order_count == 5

    assert response.trends[2].date == "2026-11-26"
    assert response.trends[2].order_count == 2

    mock_order_manager.get_daily_order_trends.assert_called_once_with(
        db=db,
        days=3,
    )

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_daily_order_trends_uses_default_seven_days(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_daily_order_trends.return_value = []

    service = OrderService()
    context = create_context()

    response = service.GetDailyOrderTrends(
        order_pb2.GetDailyOrderTrendsRequest(),
        context,
    )

    assert len(response.trends) == 0

    mock_order_manager.get_daily_order_trends.assert_called_once_with(
        db=db,
        days=7,
    )

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_daily_order_trends_rejects_negative_days(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    service = OrderService()
    context = create_context()

    response = service.GetDailyOrderTrends(
        order_pb2.GetDailyOrderTrendsRequest(days=-1),
        context,
    )

    assert len(response.trends) == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)

    context.set_details.assert_called_once_with("Days must be at least 1")

    mock_order_manager.get_daily_order_trends.assert_not_called()

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_daily_order_trends_handles_database_error(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_daily_order_trends.side_effect = SQLAlchemyError(
        "Database unavailable"
    )

    service = OrderService()
    context = create_context()

    response = service.GetDailyOrderTrends(
        order_pb2.GetDailyOrderTrendsRequest(days=7),
        context,
    )

    assert len(response.trends) == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

    context.set_details.assert_called_once_with("Failed to retrieve daily order trends")

    db.rollback.assert_called_once()
    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_period_order_statistics_returns_statistics(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_period_order_statistics.return_value = {
        "total_orders": 12,
        "pending_orders": 3,
        "confirmed_orders": 2,
        "processing_orders": 4,
        "delivered_orders": 3,
        "completion_rate": 25.0,
    }

    service = OrderService()
    context = create_context()

    response = service.GetPeriodOrderStatistics(
        order_pb2.GetPeriodOrderStatisticsRequest(days=30),
        context,
    )

    assert response.total_orders == 12
    assert response.pending_orders == 3
    assert response.confirmed_orders == 2
    assert response.processing_orders == 4
    assert response.delivered_orders == 3
    assert response.completion_rate == 25.0

    mock_order_manager.get_period_order_statistics.assert_called_once_with(
        db=db,
        days=30,
    )

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_period_order_statistics_uses_default_seven_days(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_period_order_statistics.return_value = {
        "total_orders": 0,
        "pending_orders": 0,
        "confirmed_orders": 0,
        "processing_orders": 0,
        "delivered_orders": 0,
        "completion_rate": 0.0,
    }

    service = OrderService()
    context = create_context()

    response = service.GetPeriodOrderStatistics(
        order_pb2.GetPeriodOrderStatisticsRequest(),
        context,
    )

    assert response.total_orders == 0

    mock_order_manager.get_period_order_statistics.assert_called_once_with(
        db=db,
        days=7,
    )

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_period_order_statistics_rejects_negative_days(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    service = OrderService()
    context = create_context()

    response = service.GetPeriodOrderStatistics(
        order_pb2.GetPeriodOrderStatisticsRequest(days=-1),
        context,
    )

    assert response.total_orders == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)

    context.set_details.assert_called_once_with("Days must be at least 1")

    mock_order_manager.get_period_order_statistics.assert_not_called()

    db.close.assert_called_once()


@patch("services.order_service.app.grpc_server.SessionLocal")
@patch("services.order_service.app.grpc_server.order_manager")
def test_get_period_order_statistics_handles_database_error(
    mock_order_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_order_manager.get_period_order_statistics.side_effect = SQLAlchemyError(
        "Database unavailable"
    )

    service = OrderService()
    context = create_context()

    response = service.GetPeriodOrderStatistics(
        order_pb2.GetPeriodOrderStatisticsRequest(days=7),
        context,
    )

    assert response.total_orders == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

    context.set_details.assert_called_once_with(
        "Failed to retrieve period order statistics"
    )

    db.rollback.assert_called_once()
    db.close.assert_called_once()
