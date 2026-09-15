import json
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from delivery_client import get_delivery_by_order
from inventory_client import check_stock
from inventory_client import release_stock
from inventory_client import reserve_stock
from models import Order, OutboxEvent


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

            event = OutboxEvent(
                event_id=str(uuid.uuid4()),
                event_type="order.created",
                aggregate_id=order.order_id,
                payload=json.dumps(
                    {
                        "user_id": user_id,
                        "product_id": product_id,
                        "quantity": quantity,
                    }
                ),
                published=False,
            )

            db.add(event)

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