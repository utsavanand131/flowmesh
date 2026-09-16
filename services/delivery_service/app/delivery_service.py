import json
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Delivery, OutboxEvent


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

            db.flush()

            event = OutboxEvent(
                event_id=str(uuid.uuid4()),
                event_type="delivery.assigned",
                aggregate_id=delivery.order_id,
                payload=json.dumps(
                    {
                        "delivery_id": delivery.delivery_id,
                        "status": delivery.status,
                    }
                ),
                published=False,
            )

            db.add(event)

            db.commit()

            db.refresh(delivery)

        except IntegrityError:
            db.rollback()

            return None

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