import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Ensure the Inventory Service app directory takes priority.
INVENTORY_APP_PATH = (
    Path(__file__).resolve().parent.parent / "services" / "inventory_service" / "app"
)

sys.path.insert(0, str(INVENTORY_APP_PATH))

# Avoid reusing modules imported from another service.
sys.modules.pop("inventory_service", None)
sys.modules.pop("models", None)
sys.modules.pop("database", None)

from inventory_service import InventoryManager


def make_inventory(product_id="product_123", quantity=10):
    return SimpleNamespace(
        product_id=product_id,
        quantity=quantity,
    )


def make_reservation(
    reservation_id="reservation_123",
    product_id="product_123",
    quantity=5,
    status="RESERVED",
):
    return SimpleNamespace(
        reservation_id=reservation_id,
        product_id=product_id,
        quantity=quantity,
        status=status,
    )


# -------------------------
# check_stock tests
# -------------------------


def test_check_stock_when_sufficient():
    db = MagicMock()
    db.get.return_value = make_inventory(quantity=10)

    result = InventoryManager().check_stock(db, "product_123", 5)

    assert result == {
        "product_id": "product_123",
        "available_quantity": 10,
        "available": True,
    }


def test_check_stock_when_insufficient():
    db = MagicMock()
    db.get.return_value = make_inventory(quantity=3)

    result = InventoryManager().check_stock(db, "product_123", 5)

    assert result == {
        "product_id": "product_123",
        "available_quantity": 3,
        "available": False,
    }


def test_check_stock_when_product_does_not_exist():
    db = MagicMock()
    db.get.return_value = None

    result = InventoryManager().check_stock(db, "missing_product", 1)

    assert result == {
        "product_id": "missing_product",
        "available_quantity": 0,
        "available": False,
    }


def test_check_stock_rejects_invalid_quantity():
    db = MagicMock()

    with pytest.raises(ValueError):
        InventoryManager().check_stock(db, "product_123", 0)


# -------------------------
# reserve_stock tests
# -------------------------


@patch("inventory_service.update")
def test_reserve_stock_success(mock_update):
    db = MagicMock()
    db.get.side_effect = [
        None,
        make_inventory(quantity=5),
    ]
    db.execute.return_value.rowcount = 1

    result = InventoryManager().reserve_stock(
        db,
        "product_123",
        5,
        "reservation_123",
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 5,
        "reserved": True,
    }

    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.execute.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@patch("inventory_service.update")
def test_reserve_stock_when_insufficient(mock_update):
    db = MagicMock()
    db.get.side_effect = [
        None,
        make_inventory(quantity=3),
    ]
    db.execute.return_value.rowcount = 0

    result = InventoryManager().reserve_stock(
        db,
        "product_123",
        5,
        "reservation_123",
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 3,
        "reserved": False,
    }

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


@patch("inventory_service.update")
def test_reserve_stock_when_product_does_not_exist(mock_update):
    db = MagicMock()
    db.get.side_effect = [
        None,
        None,
    ]
    db.execute.return_value.rowcount = 0

    result = InventoryManager().reserve_stock(
        db,
        "missing_product",
        1,
        "reservation_123",
    )

    assert result == {
        "product_id": "missing_product",
        "remaining_quantity": 0,
        "reserved": False,
    }

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_reserve_stock_is_idempotent():
    db = MagicMock()
    db.get.side_effect = [
        make_reservation(),
        make_inventory(quantity=5),
    ]

    result = InventoryManager().reserve_stock(
        db,
        "product_123",
        5,
        "reservation_123",
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 5,
        "reserved": True,
    }

    # An existing reservation must not deduct stock again.
    db.execute.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_reserve_stock_rejects_invalid_quantity():
    db = MagicMock()

    with pytest.raises(ValueError):
        InventoryManager().reserve_stock(
            db,
            "product_123",
            0,
            "reservation_123",
        )


def test_reserve_stock_rejects_empty_reservation_id():
    db = MagicMock()

    with pytest.raises(ValueError):
        InventoryManager().reserve_stock(
            db,
            "product_123",
            5,
            "",
        )


def test_reserve_stock_rejects_mismatched_existing_reservation():
    db = MagicMock()
    db.get.return_value = make_reservation(product_id="different_product")

    with pytest.raises(ValueError):
        InventoryManager().reserve_stock(
            db,
            "product_123",
            5,
            "reservation_123",
        )


# -------------------------
# release_stock tests
# -------------------------


@patch("inventory_service.update")
def test_release_stock_success(mock_update):
    db = MagicMock()
    db.get.side_effect = [
        make_reservation(),
        make_inventory(quantity=15),
    ]
    db.execute.return_value.rowcount = 1

    result = InventoryManager().release_stock(
        db,
        "product_123",
        5,
        "reservation_123",
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 15,
        "released": True,
    }

    assert db.execute.call_count == 2
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@patch("inventory_service.update")
def test_release_stock_is_idempotent(mock_update):
    db = MagicMock()
    db.get.side_effect = [
        make_reservation(status="RELEASED"),
        make_inventory(quantity=10),
    ]

    result = InventoryManager().release_stock(
        db,
        "product_123",
        5,
        "reservation_123",
    )

    assert result == {
        "product_id": "product_123",
        "remaining_quantity": 10,
        "released": True,
    }

    # Releasing an already released reservation must not
    # increase inventory a second time.
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_release_stock_when_reservation_does_not_exist():
    db = MagicMock()
    db.get.return_value = None

    result = InventoryManager().release_stock(
        db,
        "product_123",
        5,
        "missing_reservation",
    )

    assert result["released"] is False
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_release_stock_rejects_invalid_quantity():
    db = MagicMock()

    with pytest.raises(ValueError):
        InventoryManager().release_stock(
            db,
            "product_123",
            0,
            "reservation_123",
        )


def test_release_stock_rejects_empty_reservation_id():
    db = MagicMock()

    with pytest.raises(ValueError):
        InventoryManager().release_stock(
            db,
            "product_123",
            5,
            "",
        )


def test_release_stock_rejects_mismatched_reservation():
    db = MagicMock()
    db.get.return_value = make_reservation(product_id="different_product")

    with pytest.raises(ValueError):
        InventoryManager().release_stock(
            db,
            "product_123",
            5,
            "reservation_123",
        )


# list_inventory tests


def test_list_inventory_returns_inventory_and_statistics():
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [
        make_inventory("product_123", 20),
        make_inventory("product_456", 6),
        make_inventory("product_789", 0),
        make_inventory("product_999", 10),
        make_inventory("product_111", 3),
    ]

    result = InventoryManager().list_inventory(db)

    assert result == {
        "items": [
            {"product_id": "product_123", "quantity": 20},
            {"product_id": "product_456", "quantity": 6},
            {"product_id": "product_789", "quantity": 0},
            {"product_id": "product_999", "quantity": 10},
            {"product_id": "product_111", "quantity": 3},
        ],
        "total_items": 5,
        "total_quantity": 39,
        "low_stock_items": 3,
        "out_of_stock_items": 1,
        "low_stock_threshold": 10,
    }


def test_list_inventory_returns_zero_statistics_when_empty():
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []

    result = InventoryManager().list_inventory(db)

    assert result == {
        "items": [],
        "total_items": 0,
        "total_quantity": 0,
        "low_stock_items": 0,
        "out_of_stock_items": 0,
        "low_stock_threshold": 10,
    }


def test_list_inventory_excludes_out_of_stock_from_low_stock():
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = [
        make_inventory("product_123", 0),
        make_inventory("product_456", 10),
        make_inventory("product_789", 11),
    ]

    result = InventoryManager().list_inventory(db)

    assert result["low_stock_items"] == 1
    assert result["out_of_stock_items"] == 1
