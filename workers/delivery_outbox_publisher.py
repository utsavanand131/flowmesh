import json
import time

from sqlalchemy.exc import SQLAlchemyError

from lib.events import publish_delivery_event
from services.delivery_service.app.database import SessionLocal
from services.delivery_service.app.models import OutboxEvent


POLL_INTERVAL = 2
BATCH_SIZE = 10


def publish_pending_events():
    db = SessionLocal()

    try:
        events = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.published.is_(False)
            )
            .order_by(
                OutboxEvent.event_id
            )
            .limit(BATCH_SIZE)
            .with_for_update(
                skip_locked=True
            )
            .all()
        )

        for event in events:
            try:
                payload = json.loads(
                    event.payload
                )

                message_id = publish_delivery_event(
                    event_type=event.event_type,
                    order_id=event.aggregate_id,
                    data=payload,
                )

                event.published = True

                db.commit()

                print(
                    "Published delivery outbox event:",
                    event.event_id,
                )

                print(
                    "Redis message ID:",
                    message_id,
                )

            except Exception as error:
                db.rollback()

                print(
                    "Failed to publish delivery outbox event:",
                    event.event_id,
                )

                print(
                    "Error:",
                    error,
                )

    except SQLAlchemyError as error:
        db.rollback()

        print(
            "Database error while reading "
            "delivery outbox events:",
            error,
        )

    finally:
        db.close()


def main():
    print(
        "FlowMesh Delivery Outbox Publisher running..."
    )

    print(
        "Polling for unpublished delivery events..."
    )

    while True:
        try:
            publish_pending_events()

        except Exception as error:
            print(
                "Delivery outbox publisher error:",
                error,
            )

        time.sleep(
            POLL_INTERVAL
        )


if __name__ == "__main__":
    main()