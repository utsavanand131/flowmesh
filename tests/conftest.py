
import sys
from pathlib import Path

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


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
