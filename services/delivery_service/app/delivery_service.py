
import json
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.delivery_service.app.models import (
    Delivery,
    OutboxEvent,
    ProcessedEvent,
)


DELIVERY_STATUSES = {
    "ASSIGNED",
    "PICKED_UP",
    "IN_TRANSIT",
    "DELIVERED",
}


class DeliveryManager:
    def create_delivery(
        self,
        db: Session,
        order_id: str,
        event_id: str,
    ):
        if not event_id:
            raise ValueError("event_id is required")

        # Check whether this event has already been processed.
        processed_event = db.get(
            ProcessedEvent,
            event_id,
        )

        if processed_event is not None:
            return self.get_delivery_by_order(
                db,
                order_id,
            )

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

            processed_event = ProcessedEvent(
                event_id=event_id,
                event_type="order.created",
                aggregate_id=order_id,
            )

            db.add(event)
            db.add(processed_event)

            db.commit()

            db.refresh(delivery)

        except IntegrityError:
            db.rollback()

            # A concurrent request may have processed
            # the same event while this request was running.
            processed_event = db.get(
                ProcessedEvent,
                event_id,
            )

            if processed_event is not None:
                return self.get_delivery_by_order(
                    db,
                    order_id,
                )

            return None

        except Exception:
            db.rollback()
            raise

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

    def update_delivery_status(
        self,
        db: Session,
        delivery_id: str,
        new_status: str,
    ):
        if new_status not in DELIVERY_STATUSES:
            return None, "INVALID_STATUS"

        delivery = db.get(
            Delivery,
            delivery_id,
        )

        if delivery is None:
            return None, "NOT_FOUND"

        current_status = delivery.status

        allowed_transitions = {
            "ASSIGNED": {"PICKED_UP"},
            "PICKED_UP": {"IN_TRANSIT"},
            "IN_TRANSIT": {"DELIVERED"},
            "DELIVERED": set(),
        }

        if new_status not in allowed_transitions[current_status]:
            return None, "INVALID_TRANSITION"

        delivery.status = new_status

        try:
            db.flush()

            event = OutboxEvent(
                event_id=str(uuid.uuid4()),
                event_type="delivery.status_updated",
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

        except Exception:
            db.rollback()
            raise

        return delivery, None
