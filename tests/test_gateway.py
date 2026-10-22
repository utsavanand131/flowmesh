
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
    response = client.get(
        "/orders/test-order-id",
    )

    assert response.status_code == 401


def test_update_delivery_status_requires_admin(client):
    response = client.patch(
        "/deliveries/test-delivery-id/status",
        json={"status": "PICKED_UP"},
    )

    assert response.status_code == 401
