import uuid

from sqlalchemy.orm import Session

from models import Order


class OrderManager:
    def create_order(
        self,
        db: Session,
        user_id: str,
        product_id: str,
        quantity: int,
    ):
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

        return order

    def get_order(
        self,
        db: Session,
        order_id: str,
    ):
        return db.get(Order, order_id)