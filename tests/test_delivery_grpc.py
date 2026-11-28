from unittest.mock import MagicMock, patch

import grpc
import pytest

from sqlalchemy.exc import SQLAlchemyError

from services.delivery_service.app import delivery_pb2
from services.delivery_service.app.grpc_server import DeliveryService


def create_context():
    return MagicMock()


@patch("services.delivery_service.app.grpc_server.SessionLocal")
@patch("services.delivery_service.app.grpc_server.delivery_manager")
@pytest.mark.parametrize("days", [7, 14, 30])
def test_get_delivery_analytics_returns_analytics(
    mock_delivery_manager,
    mock_session_local,
    days,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_delivery_manager.get_delivery_analytics.return_value = {
        "days": days,
        "total_created": 12,
        "total_delivered": 8,
        "average_turnaround_hours": 5.5,
        "daily_analytics": [
            {
                "date": "2026-11-26",
                "created_count": 3,
                "delivered_count": 2,
                "backlog_count": 1,
            },
            {
                "date": "2026-11-27",
                "created_count": 4,
                "delivered_count": 3,
                "backlog_count": 2,
            },
        ],
    }

    service = DeliveryService()
    context = create_context()

    response = service.GetDeliveryAnalytics(
        delivery_pb2.GetDeliveryAnalyticsRequest(days=days),
        context,
    )

    assert response.days == days
    assert response.total_created == 12
    assert response.total_delivered == 8
    assert response.average_turnaround_hours == 5.5

    assert len(response.daily_analytics) == 2

    assert response.daily_analytics[0].date == "2026-11-26"
    assert response.daily_analytics[0].created_count == 3
    assert response.daily_analytics[0].delivered_count == 2
    assert response.daily_analytics[0].backlog_count == 1

    assert response.daily_analytics[1].date == "2026-11-27"
    assert response.daily_analytics[1].created_count == 4
    assert response.daily_analytics[1].delivered_count == 3
    assert response.daily_analytics[1].backlog_count == 2

    mock_delivery_manager.get_delivery_analytics.assert_called_once_with(
        db=db,
        days=days,
    )

    db.close.assert_called_once()


@patch("services.delivery_service.app.grpc_server.SessionLocal")
@patch("services.delivery_service.app.grpc_server.delivery_manager")
def test_get_delivery_analytics_rejects_unsupported_period(
    mock_delivery_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    service = DeliveryService()
    context = create_context()

    response = service.GetDeliveryAnalytics(
        delivery_pb2.GetDeliveryAnalyticsRequest(days=10),
        context,
    )

    assert response.total_created == 0
    assert response.total_delivered == 0
    assert len(response.daily_analytics) == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INVALID_ARGUMENT)

    context.set_details.assert_called_once_with("Days must be 7, 14, or 30")

    mock_delivery_manager.get_delivery_analytics.assert_not_called()

    db.close.assert_called_once()


@patch("services.delivery_service.app.grpc_server.SessionLocal")
@patch("services.delivery_service.app.grpc_server.delivery_manager")
def test_get_delivery_analytics_handles_database_error(
    mock_delivery_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_delivery_manager.get_delivery_analytics.side_effect = SQLAlchemyError(
        "Database unavailable"
    )

    service = DeliveryService()
    context = create_context()

    response = service.GetDeliveryAnalytics(
        delivery_pb2.GetDeliveryAnalyticsRequest(days=7),
        context,
    )

    assert response.total_created == 0
    assert response.total_delivered == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

    context.set_details.assert_called_once_with("Failed to retrieve delivery analytics")

    db.rollback.assert_called_once()
    db.close.assert_called_once()


@patch("services.delivery_service.app.grpc_server.SessionLocal")
@patch("services.delivery_service.app.grpc_server.delivery_manager")
def test_get_delivery_analytics_handles_unexpected_error(
    mock_delivery_manager,
    mock_session_local,
):
    db = MagicMock()
    mock_session_local.return_value = db

    mock_delivery_manager.get_delivery_analytics.side_effect = RuntimeError(
        "Unexpected failure"
    )

    service = DeliveryService()
    context = create_context()

    response = service.GetDeliveryAnalytics(
        delivery_pb2.GetDeliveryAnalyticsRequest(days=7),
        context,
    )

    assert response.total_created == 0

    context.set_code.assert_called_once_with(grpc.StatusCode.INTERNAL)

    context.set_details.assert_called_once_with(
        "Unexpected error retrieving delivery analytics"
    )

    db.rollback.assert_called_once()
    db.close.assert_called_once()
