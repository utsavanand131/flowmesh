import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lib.events import publish_delivery_event
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

        except IntegrityError:
            db.rollback()
            return None

        publish_delivery_event(
            event_type="delivery.assigned",
            order_id=delivery.order_id,
            data={
                "delivery_id": delivery.delivery_id,
                "status": delivery.status,
            },
        )

        return delivery

    def get_delivery(
        self,
        db: Session,
        delivery_id: str,
    ):
        return db.get(
            Delivery,
            delivery_id,
        )

    def get_delivery_by_order(
        self,
        db: Session,
        order_id: str,
    ):
        return (
            db.query(Delivery)
            .filter(
                Delivery.order_id == order_id
            )
            .first()
        )