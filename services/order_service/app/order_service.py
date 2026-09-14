import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from delivery_client import get_delivery_by_order
from inventory_client import check_stock
from inventory_client import release_stock
from inventory_client import reserve_stock
from models import Order

from lib.events import publish_order_event


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
            publish_order_event(
                event_type="order.created",
                order_id=order.order_id,
                data={
                    "user_id": order.user_id,
                    "product_id": order.product_id,
                    "quantity": order.quantity,
                },
            )

        except Exception:
            print(
                "Order event publishing failed. "
                "Compensating order and inventory."
            )

            try:
                db.delete(order)
                db.commit()

            except SQLAlchemyError:
                db.rollback()

                print(
                    "CRITICAL: Failed to remove order "
                    f"{order.order_id} after event publishing failure"
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
        }

    def get_order(
        self,
        db: Session,
        order_id: str,
    ):
        order = db.get(
            Order,
            order_id,
        )

        if order is None:
            return None

        delivery = get_delivery_by_order(
            order_id=order.order_id,
        )

        return {
            "order": order,
            "delivery": delivery,
        }