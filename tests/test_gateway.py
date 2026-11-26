from unittest.mock import MagicMock, patch

import grpc
from redis.exceptions import RedisError


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


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_get_order_success_without_delivery(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.GetOrder.return_value = MagicMock(
        order_id="test-order-789",
        user_id="test-user-id",
        product_id="product_e2e_test",
        quantity=2,
        status="PENDING",
        delivery_id="",
        delivery_status="",
    )

    response = authenticated_client.get("/orders/test-order-789")

    assert response.status_code == 200
    assert response.json() == {
        "order_id": "test-order-789",
        "user_id": "test-user-id",
        "product_id": "product_e2e_test",
        "quantity": 2,
        "status": "PENDING",
        "delivery": None,
    }

    mock_stub.GetOrder.assert_called_once()
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_get_order_success_with_delivery(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.GetOrder.return_value = MagicMock(
        order_id="test-order-101",
        user_id="test-user-id",
        product_id="product_e2e_test",
        quantity=1,
        status="PROCESSING",
        delivery_id="test-delivery-101",
        delivery_status="IN_TRANSIT",
    )

    response = authenticated_client.get("/orders/test-order-101")

    assert response.status_code == 200
    assert response.json() == {
        "order_id": "test-order-101",
        "user_id": "test-user-id",
        "product_id": "product_e2e_test",
        "quantity": 1,
        "status": "PROCESSING",
        "delivery": {
            "delivery_id": "test-delivery-101",
            "status": "IN_TRANSIT",
        },
    }

    mock_stub.GetOrder.assert_called_once()
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_get_order_not_found(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.NOT_FOUND
    error.details = lambda: "Order not found"

    mock_stub.GetOrder.side_effect = error

    response = authenticated_client.get("/orders/missing-order")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_get_order_hides_another_users_order(
    mock_stub_class,
    mock_channel_factory,
    authenticated_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.GetOrder.return_value = MagicMock(
        order_id="another-users-order",
        user_id="different-user-id",
        product_id="product_e2e_test",
        quantity=1,
        status="PENDING",
        delivery_id="",
        delivery_status="",
    )

    response = authenticated_client.get("/orders/another-users-order")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_get_order_service_unavailable(
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

    mock_stub.GetOrder.side_effect = error

    response = authenticated_client.get("/orders/test-order-123")

    assert response.status_code == 503
    assert response.json()["detail"] == "Order service unavailable"
    mock_channel.close.assert_called_once()


def test_customer_cannot_update_delivery_status(authenticated_client):
    response = authenticated_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "PICKED_UP"},
    )

    assert response.status_code == 403


def test_admin_update_rejects_invalid_delivery_status(admin_client):
    response = admin_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "UNKNOWN"},
    )

    assert response.status_code == 400
    assert "Invalid delivery status" in response.json()["detail"]


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
def test_admin_updates_delivery_status_successfully(
    mock_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub
    mock_stub.UpdateDeliveryStatus.return_value = MagicMock(
        delivery_id="test-delivery-123",
        order_id="test-order-123",
        status="PICKED_UP",
    )

    response = admin_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "PICKED_UP"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "delivery_id": "test-delivery-123",
        "order_id": "test-order-123",
        "status": "PICKED_UP",
    }

    mock_stub.UpdateDeliveryStatus.assert_called_once()
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
def test_admin_update_delivery_not_found(
    mock_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.NOT_FOUND
    error.details = lambda: "Delivery not found"

    mock_stub.UpdateDeliveryStatus.side_effect = error

    response = admin_client.patch(
        "/deliveries/missing-delivery/status",
        json={"status": "DELIVERED"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Delivery not found"
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
def test_admin_update_delivery_failed_precondition(
    mock_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.FAILED_PRECONDITION
    error.details = lambda: "Invalid delivery transition"

    mock_stub.UpdateDeliveryStatus.side_effect = error

    response = admin_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "DELIVERED"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid delivery transition"
    mock_channel.close.assert_called_once()


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
def test_admin_update_delivery_service_unavailable(
    mock_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.UNAVAILABLE
    error.details = lambda: "Service unavailable"

    mock_stub.UpdateDeliveryStatus.side_effect = error

    response = admin_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "IN_TRANSIT"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Delivery service unavailable"
    mock_channel.close.assert_called_once()


def test_customer_cannot_access_metrics(authenticated_client):
    response = authenticated_client.get("/metrics")

    assert response.status_code == 403


@patch("gateway.app.main.get_metric")
def test_admin_can_access_metrics(mock_get_metric, admin_client):
    mock_get_metric.return_value = 0

    response = admin_client.get("/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "events_processed_total": 0,
        "events_failed_total": 0,
        "events_retried_total": 0,
        "events_dead_lettered_total": 0,
        "events_recovered_total": 0,
        "events_ack_failed_total": 0,
        "events_ack_zero_total": 0,
        "events_ack_exception_total": 0,
    }

    assert mock_get_metric.call_count == 8


@patch("gateway.app.main.get_metric")
def test_metrics_returns_503_when_redis_is_unavailable(
    mock_get_metric,
    admin_client,
):
    mock_get_metric.side_effect = RedisError("Redis unavailable")

    response = admin_client.get("/metrics")

    assert response.status_code == 503
    assert response.json()["detail"] == "Metrics service unavailable"


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
def test_admin_update_delivery_invalid_argument(
    mock_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channel = MagicMock()
    mock_channel_factory.return_value = mock_channel

    mock_stub = MagicMock()
    mock_stub_class.return_value = mock_stub

    error = grpc.RpcError()
    error.code = lambda: grpc.StatusCode.INVALID_ARGUMENT
    error.details = lambda: "Invalid delivery status"

    mock_stub.UpdateDeliveryStatus.side_effect = error

    response = admin_client.patch(
        "/deliveries/test-delivery-123/status",
        json={"status": "PICKED_UP"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid delivery status"

    mock_channel.close.assert_called_once()


# -------------------------------------------------------------------
# Admin event monitoring tests
# -------------------------------------------------------------------


def test_customer_cannot_access_event_monitoring_endpoints(
    authenticated_client,
):
    endpoints = [
        "/admin/events/overview",
        "/admin/events/streams",
        "/admin/events/activity",
        "/admin/events/consumer-groups",
        "/admin/events/dead-letters",
    ]

    for endpoint in endpoints:
        response = authenticated_client.get(endpoint)
        assert response.status_code == 403


@patch("gateway.app.main._get_consumer_group_info")
@patch("gateway.app.main.redis_client.xlen")
@patch("gateway.app.main.get_metric")
def test_admin_can_access_event_overview(
    mock_get_metric,
    mock_xlen,
    mock_get_groups,
    admin_client,
):
    mock_get_metric.return_value = 0
    mock_xlen.side_effect = [3, 2, 1]
    mock_get_groups.return_value = []

    response = admin_client.get("/admin/events/overview")

    assert response.status_code == 200

    data = response.json()

    assert data["metrics"]["events_processed_total"] == 0
    assert data["streams"]["order"]["length"] == 3
    assert data["streams"]["delivery"]["length"] == 2
    assert data["streams"]["dead_letter"]["length"] == 1

    assert data["current_state"] == {
        "total_stream_entries": 6,
        "total_pending_messages": 0,
    }

    assert "checked_at" in data


@patch("gateway.app.main.redis_client.xlen")
def test_event_overview_returns_503_when_redis_is_unavailable(
    mock_xlen,
    admin_client,
):
    mock_xlen.side_effect = RedisError("Redis unavailable")

    response = admin_client.get("/admin/events/overview")

    assert response.status_code == 503
    assert response.json()["detail"] == ("Event monitoring service unavailable")


@patch("gateway.app.main._get_stream_info")
def test_admin_can_access_event_streams(
    mock_get_stream_info,
    admin_client,
):
    mock_get_stream_info.side_effect = [
        {
            "exists": True,
            "length": 2,
            "first_entry": {
                "message_id": "1000-0",
                "fields": {"event_type": "order.created"},
            },
            "last_entry": {
                "message_id": "2000-0",
                "fields": {"event_type": "order.updated"},
            },
            "groups": 1,
        },
        {
            "exists": False,
            "length": 0,
            "first_entry": None,
            "last_entry": None,
            "groups": 0,
        },
        {
            "exists": False,
            "length": 0,
            "first_entry": None,
            "last_entry": None,
            "groups": 0,
        },
    ]

    response = admin_client.get("/admin/events/streams")

    assert response.status_code == 200

    data = response.json()

    assert data["streams"]["order"]["length"] == 2
    assert data["streams"]["order"]["exists"] is True
    assert data["streams"]["order"]["groups"] == 1

    assert data["streams"]["delivery"]["exists"] is False
    assert data["streams"]["dead_letter"]["length"] == 0

    assert "checked_at" in data


def test_get_stream_info_detects_existing_empty_stream_with_consumer_group(
    monkeypatch,
):
    from gateway.app import main

    monkeypatch.setattr(
        main.redis_client,
        "exists",
        lambda stream: 1,
    )

    monkeypatch.setattr(
        main,
        "_get_stream_length",
        lambda stream: 0,
    )

    monkeypatch.setattr(
        main.redis_client,
        "xinfo_stream",
        lambda stream: {
            "first-entry": None,
            "last-entry": None,
            "groups": 1,
        },
    )

    result = main._get_stream_info("flowmesh:order-events")

    assert result["exists"] is True
    assert result["length"] == 0
    assert result["first_entry"] is None
    assert result["last_entry"] is None
    assert result["groups"] == 1


@patch("gateway.app.main.redis_client.xrevrange")
def test_admin_can_access_event_activity(
    mock_xrevrange,
    admin_client,
):
    mock_xrevrange.side_effect = [
        [
            (
                "2000-0",
                {
                    "event_id": "event-2",
                    "event_type": "order.created",
                    "order_id": "order-2",
                    "data": '{"quantity": 2}',
                },
            ),
            (
                "1000-0",
                {
                    "event_id": "event-1",
                    "event_type": "order.created",
                    "order_id": "order-1",
                    "data": '{"quantity": 1}',
                },
            ),
        ],
        [
            (
                "3000-0",
                {
                    "event_id": "event-3",
                    "event_type": "delivery.assigned",
                    "order_id": "order-3",
                    "data": '{"delivery_id": "delivery-3"}',
                },
            ),
        ],
    ]

    response = admin_client.get("/admin/events/activity")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 3
    assert len(data["events"]) == 3

    # Events from both streams should be sorted newest first.
    assert data["events"][0]["event_id"] == "event-3"
    assert data["events"][1]["event_id"] == "event-2"
    assert data["events"][2]["event_id"] == "event-1"

    # JSON event data should be decoded.
    assert data["events"][1]["fields"]["data"] == {"quantity": 2}

    assert data["has_more"] is False
    assert "checked_at" not in data


@patch("gateway.app.main.redis_client.xrevrange")
def test_event_activity_supports_filters(
    mock_xrevrange,
    admin_client,
):
    mock_xrevrange.return_value = [
        (
            "2000-0",
            {
                "event_id": "event-2",
                "event_type": "order.created",
                "order_id": "order-123",
                "data": "{}",
            },
        ),
        (
            "1000-0",
            {
                "event_id": "event-1",
                "event_type": "order.created",
                "order_id": "another-order",
                "data": "{}",
            },
        ),
    ]

    response = admin_client.get(
        "/admin/events/activity",
        params={
            "stream": "order",
            "event_type": "order.created",
            "order_id": "order-123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["events"]) == 1
    assert data["events"][0]["event_id"] == "event-2"
    assert data["events"][0]["order_id"] == "order-123"

    mock_xrevrange.assert_called_once()


def test_event_activity_rejects_invalid_stream(admin_client):
    response = admin_client.get(
        "/admin/events/activity",
        params={"stream": "inventory"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == ("Stream must be 'order' or 'delivery'")


@patch("gateway.app.main._get_consumer_group_info")
def test_admin_can_access_event_consumer_groups(
    mock_get_groups,
    admin_client,
):
    mock_get_groups.side_effect = [
        [
            {
                "stream": "flowmesh:order-events",
                "group": "flowmesh-workers",
                "consumers_count": 1,
                "pending_count": 2,
                "last_delivered_id": "1000-0",
                "entries_read": 10,
                "lag": 0,
                "consumers": [
                    {
                        "name": "order-worker-1",
                        "pending_count": 2,
                        "idle_ms": 100,
                    }
                ],
            }
        ],
        [],
    ]

    response = admin_client.get("/admin/events/consumer-groups")

    assert response.status_code == 200

    data = response.json()

    assert data["total_groups"] == 1
    assert data["total_pending_messages"] == 2

    group = data["consumer_groups"][0]

    assert group["group"] == "flowmesh-workers"
    assert group["pending_count"] == 2
    assert group["consumers"][0]["name"] == "order-worker-1"


@patch("gateway.app.main.redis_client.xrevrange")
@patch("gateway.app.main.redis_client.xlen")
def test_admin_can_access_dead_letter_events(
    mock_xlen,
    mock_xrevrange,
    admin_client,
):
    mock_xlen.return_value = 1

    mock_xrevrange.return_value = [
        (
            "3000-0",
            {
                "original_stream": "flowmesh:order-events",
                "original_group": "flowmesh-workers",
                "original_message_id": "1000-0",
                "event_id": "event-failed-1",
                "event_type": "order.created",
                "attempts": "5",
                "error": "Processing failed",
                "original_fields": (
                    '{"order_id": "order-123", ' '"event_type": "order.created"}'
                ),
                "dead_lettered_at": "2026-11-22T10:00:00+00:00",
            },
        )
    ]

    response = admin_client.get("/admin/events/dead-letters")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["dead_letters"]) == 1

    record = data["dead_letters"][0]

    assert record["event_id"] == "event-failed-1"
    assert record["attempts"] == "5"
    assert record["error"] == "Processing failed"

    assert record["original_fields"] == {
        "order_id": "order-123",
        "event_type": "order.created",
    }


def test_dead_letter_events_reject_invalid_original_stream(
    admin_client,
):
    response = admin_client.get(
        "/admin/events/dead-letters",
        params={"original_stream": "flowmesh:inventory-events"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid original stream"


@patch("gateway.app.main.redis_client.xlen")
def test_dead_letter_events_return_503_when_redis_is_unavailable(
    mock_xlen,
    admin_client,
):
    mock_xlen.side_effect = RedisError("Redis unavailable")

    response = admin_client.get("/admin/events/dead-letters")

    assert response.status_code == 503
    assert response.json()["detail"] == ("Event monitoring service unavailable")


def test_customer_cannot_access_order_overview(authenticated_client):
    response = authenticated_client.get("/admin/orders/overview")

    assert response.status_code == 403


@patch("gateway.app.main.grpc.insecure_channel")
@patch("gateway.app.main.delivery_pb2_grpc.DeliveryServiceStub")
@patch("gateway.app.main.order_pb2_grpc.OrderServiceStub")
def test_admin_can_access_order_overview(
    mock_order_stub_class,
    mock_delivery_stub_class,
    mock_channel_factory,
    admin_client,
):
    mock_channels = [MagicMock(), MagicMock()]
    mock_channel_factory.side_effect = mock_channels

    mock_order_stub = MagicMock()
    mock_order_stub_class.return_value = mock_order_stub
    mock_order_stub.GetOrderStatistics.return_value = MagicMock(
        total_orders=36,
        pending_orders=18,
        confirmed_orders=3,
        processing_orders=8,
        delivered_orders=7,
        completion_rate=19.44,
    )

    mock_delivery_stub = MagicMock()
    mock_delivery_stub_class.return_value = mock_delivery_stub
    mock_delivery_stub.ListDeliveries.return_value = MagicMock(
        assigned_count=24,
        picked_up_count=1,
        in_transit_count=0,
        delivered_count=8,
    )

    response = admin_client.get("/admin/orders/overview")

    assert response.status_code == 200
    assert response.json() == {
        "total_orders": 36,
        "pending_orders": 18,
        "confirmed_orders": 3,
        "processing_orders": 8,
        "in_delivery": 25,
        "delivered_orders": 7,
        "completion_rate": 19.44,
    }

    mock_order_stub.GetOrderStatistics.assert_called_once()
    mock_delivery_stub.ListDeliveries.assert_called_once()

    for channel in mock_channels:
        channel.close.assert_called_once()
