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