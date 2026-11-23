import os

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Inventory, InventoryReservation

LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "10"))


class InventoryManager:
    def check_stock(
        self,
        db: Session,
        product_id: str,
        quantity: int,
    ):
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        inventory = db.get(
            Inventory,
            product_id,
        )

        available_quantity = inventory.quantity if inventory is not None else 0

        return {
            "product_id": product_id,
            "available_quantity": available_quantity,
            "available": available_quantity >= quantity,
        }

    def list_inventory(self, db: Session):
        items = db.query(Inventory).order_by(Inventory.product_id.asc()).all()

        total_quantity = sum(item.quantity for item in items)

        low_stock_items = [
            item for item in items if 0 < item.quantity <= LOW_STOCK_THRESHOLD
        ]

        out_of_stock_items = [item for item in items if item.quantity == 0]

        return {
            "items": [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                }
                for item in items
            ],
            "total_items": len(items),
            "total_quantity": total_quantity,
            "low_stock_items": len(low_stock_items),
            "out_of_stock_items": len(out_of_stock_items),
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
        }

    def reserve_stock(
        self,
        db: Session,
        product_id: str,
        quantity: int,
        reservation_id: str,
    ):
        if not reservation_id:
            raise ValueError("Reservation ID is required")

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        # Check whether this reservation already exists.
        existing = db.get(
            InventoryReservation,
            reservation_id,
        )

        if existing is not None:
            if existing.product_id != product_id or existing.quantity != quantity:
                raise ValueError("Reservation ID already exists with different details")

            inventory = db.get(
                Inventory,
                product_id,
            )

            return {
                "product_id": product_id,
                "remaining_quantity": (
                    inventory.quantity if inventory is not None else 0
                ),
                "reserved": existing.status == "RESERVED",
            }

        # Create the reservation record inside the same
        # transaction as the stock deduction.
        reservation = InventoryReservation(
            reservation_id=reservation_id,
            product_id=product_id,
            quantity=quantity,
            status="RESERVED",
        )

        try:
            db.add(reservation)

            # Flush first so concurrent requests using the
            # same reservation ID are protected by the PK.
            db.flush()

            statement = (
                update(Inventory)
                .where(
                    Inventory.product_id == product_id,
                    Inventory.quantity >= quantity,
                )
                .values(
                    quantity=Inventory.quantity - quantity,
                )
            )

            result = db.execute(statement)

            if result.rowcount == 0:
                db.rollback()

                inventory = db.get(
                    Inventory,
                    product_id,
                )

                return {
                    "product_id": product_id,
                    "remaining_quantity": (
                        inventory.quantity if inventory is not None else 0
                    ),
                    "reserved": False,
                }

            db.commit()

        except IntegrityError:
            # Another request may have created this
            # reservation ID concurrently.
            db.rollback()

            existing = db.get(
                InventoryReservation,
                reservation_id,
            )

            if existing is None:
                raise

            if existing.product_id != product_id or existing.quantity != quantity:
                raise ValueError("Reservation ID already exists with different details")

            inventory = db.get(
                Inventory,
                product_id,
            )

            return {
                "product_id": product_id,
                "remaining_quantity": (
                    inventory.quantity if inventory is not None else 0
                ),
                "reserved": existing.status == "RESERVED",
            }

        inventory = db.get(
            Inventory,
            product_id,
        )

        return {
            "product_id": product_id,
            "remaining_quantity": inventory.quantity,
            "reserved": True,
        }

    def release_stock(
        self,
        db: Session,
        product_id: str,
        quantity: int,
        reservation_id: str,
    ):
        if not reservation_id:
            raise ValueError("Reservation ID is required")

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        reservation = db.get(
            InventoryReservation,
            reservation_id,
        )

        if reservation is None:
            return {
                "product_id": product_id,
                "remaining_quantity": 0,
                "released": False,
            }

        if reservation.product_id != product_id or reservation.quantity != quantity:
            raise ValueError("Reservation details do not match")

        # A repeated release must never add stock again.
        if reservation.status == "RELEASED":
            inventory = db.get(
                Inventory,
                product_id,
            )

            return {
                "product_id": product_id,
                "remaining_quantity": (
                    inventory.quantity if inventory is not None else 0
                ),
                "released": True,
            }

        # Atomically claim the release operation.
        # Only one concurrent request can change RESERVED
        # to RELEASED.
        reservation_update = (
            update(InventoryReservation)
            .where(
                InventoryReservation.reservation_id == reservation_id,
                InventoryReservation.status == "RESERVED",
            )
            .values(
                status="RELEASED",
            )
        )

        reservation_result = db.execute(reservation_update)

        if reservation_result.rowcount == 0:
            db.rollback()

            existing = db.get(
                InventoryReservation,
                reservation_id,
            )

            if (
                existing is not None
                and existing.product_id == product_id
                and existing.quantity == quantity
                and existing.status == "RELEASED"
            ):
                inventory = db.get(
                    Inventory,
                    product_id,
                )

                return {
                    "product_id": product_id,
                    "remaining_quantity": (
                        inventory.quantity if inventory is not None else 0
                    ),
                    "released": True,
                }

            return {
                "product_id": product_id,
                "remaining_quantity": 0,
                "released": False,
            }

        # Restore stock in the same transaction as the
        # reservation status change.
        inventory_update = (
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
            )
            .values(
                quantity=Inventory.quantity + quantity,
            )
        )

        inventory_result = db.execute(inventory_update)

        if inventory_result.rowcount == 0:
            db.rollback()

            return {
                "product_id": product_id,
                "remaining_quantity": 0,
                "released": False,
            }

        db.commit()

        inventory = db.get(
            Inventory,
            product_id,
        )

        return {
            "product_id": product_id,
            "remaining_quantity": inventory.quantity,
            "released": True,
        }
