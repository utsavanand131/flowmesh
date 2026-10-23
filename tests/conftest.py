
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODULE_PATHS = [
    PROJECT_ROOT / "gateway" / "app",
    PROJECT_ROOT / "services" / "order_service" / "app",
    PROJECT_ROOT / "services" / "inventory_service" / "app",
    PROJECT_ROOT / "services" / "delivery_service" / "app",
]

for module_path in MODULE_PATHS:
    path = str(module_path)
    if path not in sys.path:
        sys.path.insert(0, path)

from gateway.app.main import app
from gateway.app.auth_routes import (
    require_current_user,
    require_admin_user,
)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client():
    test_user = SimpleNamespace(
        id="test-user-id",
        email="test@example.com",
        name="Test User",
        role="CUSTOMER",
    )

    app.dependency_overrides[require_current_user] = (
        lambda: test_user
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_client():
    test_admin = SimpleNamespace(
        id="test-admin-id",
        email="admin@example.com",
        name="Test Admin",
        role="ADMIN",
    )

    app.dependency_overrides[require_current_user] = (
        lambda: test_admin
    )
    app.dependency_overrides[require_admin_user] = (
        lambda: test_admin
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
