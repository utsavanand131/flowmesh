from sqlalchemy import update
from sqlalchemy.orm import Session

from models import Inventory


class InventoryManager:
    def check_stock(
        self,
        db: Session,
        product_id: str,
        quantity: int,
    ):
        inventory = db.get(Inventory, product_id)

        available_quantity = (
            inventory.quantity
            if inventory is not None
            else 0
        )

        return {
            "product_id": product_id,
            "available_quantity": available_quantity,
            "available": available_quantity >= quantity,
        }

    def reserve_stock(
        self,
        db: Session,
        product_id: str,
        quantity: int,
    ):
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

            remaining_quantity = (
                inventory.quantity
                if inventory is not None
                else 0
            )

            return {
                "product_id": product_id,
                "remaining_quantity": remaining_quantity,
                "reserved": False,
            }

        db.commit()

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
    ):
        statement = (
            update(Inventory)
            .where(
                Inventory.product_id == product_id,
            )
            .values(
                quantity=Inventory.quantity + quantity,
            )
        )

        result = db.execute(statement)

        if result.rowcount == 0:
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