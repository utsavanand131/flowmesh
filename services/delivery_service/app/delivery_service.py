import json
import uuid

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, time, timedelta, timezone

from services.delivery_service.app.models import (
    Delivery,
    DeliveryStatusHistory,
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

            # Record the initial delivery status.
            history = DeliveryStatusHistory(
                history_id=str(uuid.uuid4()),
                delivery_id=delivery.delivery_id,
                previous_status=None,
                new_status="ASSIGNED",
            )

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

            db.add(history)
            db.add(event)
            db.add(processed_event)

            # Delivery, history, outbox and processed event
            # are committed together.
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
        return db.query(Delivery).filter(Delivery.order_id == order_id).first()

    def list_deliveries(
        self,
        db: Session,
        page: int,
        page_size: int,
    ):
        # Fetch global counts across ALL deliveries.
        counts = db.query(
            func.count(Delivery.delivery_id).label("total"),
            func.count(Delivery.delivery_id)
            .filter(Delivery.status == "ASSIGNED")
            .label("assigned"),
            func.count(Delivery.delivery_id)
            .filter(Delivery.status == "PICKED_UP")
            .label("picked_up"),
            func.count(Delivery.delivery_id)
            .filter(Delivery.status == "IN_TRANSIT")
            .label("in_transit"),
            func.count(Delivery.delivery_id)
            .filter(Delivery.status == "DELIVERED")
            .label("delivered"),
        ).one()

        total = counts.total

        status_counts = {
            "assigned": counts.assigned,
            "picked_up": counts.picked_up,
            "in_transit": counts.in_transit,
            "delivered": counts.delivered,
        }

        # Fetch only the requested page, newest first.
        deliveries = (
            db.query(Delivery)
            .order_by(
                Delivery.created_at.desc(),
                Delivery.delivery_id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return deliveries, total, status_counts

    def get_delivery_analytics(
        self,
        db: Session,
        days: int = 7,
    ):
        """
        Calculate delivery analytics for the selected period.

        Backlog represents deliveries created within the selected
        period that had not yet been delivered at the end of each day.

        Turnaround is calculated only when both ASSIGNED and
        DELIVERED history timestamps are available.
        """

        if days not in {7, 14, 30}:
            raise ValueError("days must be 7, 14, or 30")

        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=days - 1)
        end_date = today + timedelta(days=1)

        start_datetime = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone.utc,
        )

        end_datetime = datetime.combine(
            end_date,
            time.min,
            tzinfo=timezone.utc,
        )

        def utc_date(value: datetime):
            if value.tzinfo is None:
                return value.date()

            return value.astimezone(timezone.utc).date()

        # Fetch deliveries created during the selected period.
        created_deliveries = (
            db.query(Delivery)
            .filter(
                Delivery.created_at >= start_datetime,
                Delivery.created_at < end_datetime,
            )
            .all()
        )

        cohort_delivery_ids = {delivery.delivery_id for delivery in created_deliveries}

        # Fetch deliveries completed during the selected period.
        delivered_history = (
            db.query(DeliveryStatusHistory)
            .filter(
                DeliveryStatusHistory.new_status == "DELIVERED",
                DeliveryStatusHistory.changed_at >= start_datetime,
                DeliveryStatusHistory.changed_at < end_datetime,
            )
            .order_by(DeliveryStatusHistory.changed_at.asc())
            .all()
        )

        # Keep one completion timestamp per delivery.
        delivered_at_by_id = {}

        for record in delivered_history:
            delivered_at_by_id.setdefault(
                record.delivery_id,
                record.changed_at,
            )

        # Fetch assignment timestamps for deliveries completed
        # during this period.
        delivered_ids = list(delivered_at_by_id.keys())

        assigned_at_by_id = {}

        if delivered_ids:
            assigned_history = (
                db.query(DeliveryStatusHistory)
                .filter(
                    DeliveryStatusHistory.delivery_id.in_(delivered_ids),
                    DeliveryStatusHistory.new_status == "ASSIGNED",
                )
                .order_by(DeliveryStatusHistory.changed_at.asc())
                .all()
            )

            for record in assigned_history:
                assigned_at_by_id.setdefault(
                    record.delivery_id,
                    record.changed_at,
                )

        # Group daily activity.
        created_by_date = {}
        delivered_by_date = {}

        for delivery in created_deliveries:
            delivery_date = utc_date(delivery.created_at)

            created_by_date[delivery_date] = created_by_date.get(delivery_date, 0) + 1

        for delivery_id, delivered_at in delivered_at_by_id.items():
            delivered_date = utc_date(delivered_at)

            delivered_by_date[delivered_date] = (
                delivered_by_date.get(delivered_date, 0) + 1
            )

        # Calculate average turnaround using only complete
        # assignment-to-delivery timestamp pairs.
        turnaround_hours = []

        for delivery_id, delivered_at in delivered_at_by_id.items():
            assigned_at = assigned_at_by_id.get(delivery_id)

            if assigned_at is None:
                continue

            turnaround = (delivered_at - assigned_at).total_seconds() / 3600

            if turnaround >= 0:
                turnaround_hours.append(turnaround)

        average_turnaround_hours = (
            sum(turnaround_hours) / len(turnaround_hours) if turnaround_hours else 0.0
        )

        # Calculate daily backlog for deliveries created within
        # this selected period.
        daily_analytics = []

        cumulative_created = 0
        cumulative_delivered = 0

        for offset in range(days):
            current_date = start_date + timedelta(days=offset)

            created_count = created_by_date.get(current_date, 0)
            delivered_count = delivered_by_date.get(current_date, 0)

            cumulative_created += created_count

            # Only count completions belonging to deliveries
            # created during the selected period.
            for delivery_id, delivered_at in delivered_at_by_id.items():
                if delivery_id not in cohort_delivery_ids:
                    continue

                if utc_date(delivered_at) == current_date:
                    cumulative_delivered += 1

            backlog_count = max(
                cumulative_created - cumulative_delivered,
                0,
            )

            daily_analytics.append(
                {
                    "date": current_date.isoformat(),
                    "created_count": created_count,
                    "delivered_count": delivered_count,
                    "backlog_count": backlog_count,
                }
            )

        return {
            "days": days,
            "total_created": len(created_deliveries),
            "total_delivered": len(delivered_at_by_id),
            "average_turnaround_hours": average_turnaround_hours,
            "daily_analytics": daily_analytics,
        }

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

        try:
            # Update the current delivery status.
            delivery.status = new_status

            # Record the successful status transition.
            history = DeliveryStatusHistory(
                history_id=str(uuid.uuid4()),
                delivery_id=delivery.delivery_id,
                previous_status=current_status,
                new_status=new_status,
            )

            db.add(history)

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

            # Status, history and outbox event are atomic.
            db.commit()

            db.refresh(delivery)

        except Exception:
            db.rollback()
            raise

        return delivery, None
