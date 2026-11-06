
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import create_engine, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from services.delivery_service.app.database import (
    DATABASE_URL,
    Base,
)
from services.delivery_service.app.models import (
    Delivery,
    OutboxEvent,
    ProcessedEvent,
)
from services.delivery_service.app.delivery_service import (
    DeliveryManager,
)


# Force both transactions to finish their initial
# ProcessedEvent lookup before either can continue.
concurrency_barrier = Barrier(2)


class BarrierSession(Session):
    def get(self, entity, ident, **kwargs):
        result = super().get(entity, ident, **kwargs)

        if entity is ProcessedEvent and result is None:
            concurrency_barrier.wait(timeout=15)

        return result


def main():
    # Never allow this script to touch the development DB.
    test_url = make_url(DATABASE_URL).set(
        database="flowmesh_test"
    )

    if test_url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "This test requires PostgreSQL."
        )

    engine = create_engine(
        test_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
    )

    try:
        with engine.connect() as connection:
            current_database = connection.scalar(
                func.current_database()
            )

        if current_database != "flowmesh_test":
            raise RuntimeError(
                f"Wrong database: {current_database}"
            )

        print("Connected to:", current_database)

        Base.metadata.create_all(engine)

        TestSessionLocal = sessionmaker(
            bind=engine,
            class_=BarrierSession,
            autoflush=False,
            autocommit=False,
        )

        manager = DeliveryManager()

        # Unique IDs ensure this test does not collide
        # with previous test runs.
        order_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())

        def process_event():
            db = TestSessionLocal()

            try:
                return manager.create_delivery(
                    db=db,
                    order_id=order_id,
                    event_id=event_id,
                )
            finally:
                db.close()

        print("\nStarting two concurrent requests...")

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(process_event)
            future_two = executor.submit(process_event)

            result_one = future_one.result(timeout=30)
            result_two = future_two.result(timeout=30)

        print("\nBoth requests completed.")

        if result_one is None or result_two is None:
            raise AssertionError(
                "One or both requests failed."
            )

        if result_one.delivery_id != result_two.delivery_id:
            raise AssertionError(
                "Requests returned different deliveries."
            )

        with TestSessionLocal() as db:
            delivery_count = (
                db.query(Delivery)
                .filter(Delivery.order_id == order_id)
                .count()
            )

            processed_count = (
                db.query(ProcessedEvent)
                .filter(ProcessedEvent.event_id == event_id)
                .count()
            )

            outbox_count = (
                db.query(OutboxEvent)
                .filter(
                    OutboxEvent.event_type == "delivery.assigned",
                    OutboxEvent.aggregate_id == order_id,
                )
                .count()
            )

        print("\nResults:")
        print("Delivery IDs:", result_one.delivery_id, result_two.delivery_id)
        print("Deliveries:", delivery_count)
        print("Processed events:", processed_count)
        print("Outbox events:", outbox_count)

        assert delivery_count == 1
        assert processed_count == 1
        assert outbox_count == 1

        print("\nSUCCESS: Concurrent duplicate event was processed exactly once.")

        # Clean up only the records created by this test.
        with TestSessionLocal() as db:
            db.query(OutboxEvent).filter(
                OutboxEvent.event_type == "delivery.assigned",
                OutboxEvent.aggregate_id == order_id,
            ).delete(synchronize_session=False)

            db.query(ProcessedEvent).filter(
                ProcessedEvent.event_id == event_id
            ).delete(synchronize_session=False)

            db.query(Delivery).filter(
                Delivery.order_id == order_id
            ).delete(synchronize_session=False)

            db.commit()

        print("Test records cleaned up.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
