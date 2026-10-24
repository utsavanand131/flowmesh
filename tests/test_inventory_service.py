
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Ensure the Inventory Service app directory takes priority.
INVENTORY_APP_PATH = (
    Path(__file__).resolve().parent.parent
    / "services"
    / "inventory_service"
    / "app"
)

sys.path.insert(0, str(INVENTORY_APP_PATH))

# Avoid reusing modules named "models" or "database"
# that may have been imported from another service.
sys.modules.pop("inventory_service", None)
sys.modules.pop("models", None)
sys.modules.pop("database", None)

from inventory_service import InventoryManager


def make_inventory(product_id="product_123", quantity=10):
    return type(
        "InventoryRecord",
        (),
        {
            "product_id": product_id,
            "quantity": quantity,
        },
    )()


# -------------------------
# check_stock tests
# -------------------------

def test_check_stock_when_sufficient():
    db = MagicMock()
    db.get.return_value = make_inventory(quantity=10)

    result = InventoryManager().check_stock(
        db, "product_123", 5
    )

    assert result == {
        "product_id": "product_123",
        "available_quantity": 10,
        "available": True,
    }
    db.get.assert_called_once()


def test_check_stock_when_insufficient():
    db = MagicMock()
    db.get.return_value = make_inventory(quantity=3)

    result = InventoryManager().check_stock(
        db, "product_123", 5
    )

    assert result == {
        "product_id": "product_123",
        "available_quantity": 3,
        "available": False,
    }


def test_check_stock_when_product_does_not_exist():
    db = MagicMock()
    db.get.return_value = None

    result = InventoryManager().check_stock(
        db, "missing_product", 1
    )

    assert result == {
        "product_id": "missing_product",
        "available_quantity": 0,
        "available": False,
    }


# -------------------------
# reserve_stock tests
# -------------------------

@patch("inventory_service.update")
def test_reserve_stock_success(mock_update):
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    db.get.return_value = make_inventory(quantity=5)

    result = InventoryManager().reserve_stock(
        db, "product_123", 5
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 5,
        "reserved": True,
    }

    db.execute.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@patch("inventory_service.update")
def test_reserve_stock_when_insufficient(mock_update):
    db = MagicMock()
    db.execute.return_value.rowcount = 0
    db.get.return_value = make_inventory(quantity=3)

    result = InventoryManager().reserve_stock(
        db, "product_123", 5
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 3,
        "reserved": False,
    }

    db.execute.assert_called_once()
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


@patch("inventory_service.update")
def test_reserve_stock_when_product_does_not_exist(mock_update):
    db = MagicMock()
    db.execute.return_value.rowcount = 0
    db.get.return_value = None

    result = InventoryManager().reserve_stock(
        db, "missing_product", 1
    )

    assert result == {
        "product_id": "missing_product",
        "remaining_quantity": 0,
        "reserved": False,
    }

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


# -------------------------
# release_stock tests
# -------------------------

@patch("inventory_service.update")
def test_release_stock_success(mock_update):
    db = MagicMock()
    db.execute.return_value.rowcount = 1
    db.get.return_value = make_inventory(quantity=15)

    result = InventoryManager().release_stock(
        db, "product_123", 5
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 15,
        "released": True,
    }

    db.execute.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@patch("inventory_service.update")
def test_release_stock_when_product_does_not_exist(mock_update):
    db = MagicMock()
    db.execute.return_value.rowcount = 0

    result = InventoryManager().release_stock(
        db, "missing_product", 5
    )

    assert result == {
        "product_id": "missing_product",
        "remaining_quantity": 0,
        "released": False,
    }

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
