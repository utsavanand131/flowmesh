import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from delivery_client import create_delivery
from inventory_client import check_stock
from inventory_client import release_stock
from inventory_client import reserve_stock
from models import Order


class OrderManager:
    def create_order(
        self,
        db: Session,
        user_id: str,
        product_id: str,
        quantity: int,
    ):
        inventory = check_stock(
            product_id=product_id,
            quantity=quantity,
        )

        if not inventory["available"]:
            return None

        reservation = reserve_stock(
            product_id=product_id,
            quantity=quantity,
        )

        if not reservation["reserved"]:
            return None

        try:
            order = Order(
                order_id=str(uuid.uuid4()),
                user_id=user_id,
                product_id=product_id,
                quantity=quantity,
                status="PENDING",
            )

            db.add(order)
            db.commit()
            db.refresh(order)

        except SQLAlchemyError:
            db.rollback()

            try:
                release_stock(
                    product_id=product_id,
                    quantity=quantity,
                )

            except Exception:
                print(
                    "CRITICAL: Failed to release inventory "
                    f"for product {product_id}, "
                    f"quantity {quantity}"
                )

            raise

        try:
            delivery = create_delivery(
                order_id=order.order_id,
            )

        except Exception:
            print(
                "Delivery creation failed. "
                "Compensating order and inventory."
            )

            try:
                db.delete(order)
                db.commit()

            except SQLAlchemyError:
                db.rollback()

                print(
                    "CRITICAL: Failed to remove order "
                    f"{order.order_id} after delivery failure"
                )

            try:
                release_stock(
                    product_id=product_id,
                    quantity=quantity,
                )

            except Exception:
                print(
                    "CRITICAL: Failed to release inventory "
                    f"for product {product_id}, "
                    f"quantity {quantity}"
                )

            raise

        return {
            "order": order,
            "delivery": delivery,
        }