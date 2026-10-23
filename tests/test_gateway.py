
from unittest.mock import MagicMock, patch

import grpc


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "api-gateway",
        "status": "healthy",
    }


def test_create_order_requires_authentication(client):
    response = client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 1,
        },
    )

    assert response.status_code == 401


def test_get_order_requires_authentication(client):
    response = client.get("/orders/test-order-id")

    assert response.status_code == 401


def test_update_delivery_status_requires_admin(client):
    response = client.patch(
        "/deliveries/test-delivery-id/status",
        json={"status": "PICKED_UP"},
    )

    assert response.status_code == 401


def test_create_order_rejects_zero_quantity(authenticated_client):
    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 0,
        },
    )

    assert response.status_code == 422


def test_create_order_rejects_negative_quantity(authenticated_client):
    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": -1,
        },
    )

    assert response.status_code == 422


def test_create_order_rejects_empty_product_id(authenticated_client):
    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "",
            "quantity": 1,
        },
    )

    assert response.status_code == 422


def test_create_order_rejects_missing_product_id(authenticated_client):
    response = authenticated_client.post(
        "/orders",
        json={
            "quantity": 1,
        },
    )

    assert response.status_code == 422


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_create_order_success_without_delivery(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.CreateOrder.return_value = MagicMock(
        order_id="test-order-123",
        status="PENDING",
        delivery_id="",
        delivery_status="",
    )

    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 1,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "order_id": "test-order-123",
        "status": "PENDING",
        "delivery": None,
    }

    mock_stub.CreateOrder.assert_called_once()
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_create_order_success_with_delivery(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.CreateOrder.return_value = MagicMock(
        order_id="test-order-456",
        status="PENDING",
        delivery_id="test-delivery-456",
        delivery_status="ASSIGNED",
    )

    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 1,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "order_id": "test-order-456",
        "status": "PENDING",
        "delivery": {
            "delivery_id": "test-delivery-456",
            "status": "ASSIGNED",
        },
    }

    mock_stub.CreateOrder.assert_called_once()
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_create_order_insufficient_inventory(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.FAILED_PRECONDITION
    error.details = lambda: "Insufficient inventory"

    mock_stub.CreateOrder.side_effect = error

    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient inventory"
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_create_order_service_unavailable(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.UNAVAILABLE
    error.details = lambda: "Service unavailable"

    mock_stub.CreateOrder.side_effect = error

    response = authenticated_client.post(
        "/orders",
        json={
            "product_id": "product_e2e_test",
            "quantity": 1,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Order service unavailable"
    mock_channel.close.assert_called_once()
