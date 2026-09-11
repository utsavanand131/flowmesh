import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Delivery


class DeliveryManager:
    def create_delivery(
        self,
        db: Session,
        order_id: str,
    ):
        delivery = Delivery(
            delivery_id=str(uuid.uuid4()),
            order_id=order_id,
            status="ASSIGNED",
        )

        try:
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            return delivery

        except IntegrityError:
            db.rollback()

            return None

    def get_delivery(
        self,
        db: Session,
        delivery_id: str,
    ):
        return db.get(
            Delivery,
            delivery_id,
        )