import json
import signal
import threading
import time

import redis

from sqlalchemy.exc import SQLAlchemyError

from lib.event_reliability import handle_failed_message
from lib.logger import get_logger
from lib.metrics import (
    EVENTS_ACK_FAILED_TOTAL,
    EVENTS_PROCESSED_TOTAL,
    EVENTS_RECOVERED_TOTAL,
    increment_metric,
)
from lib.redis import redis_client
from services.order_service.app.database import SessionLocal
from services.order_service.app.models import Order


logger = get_logger(__name__)

DELIVERY_EVENTS_STREAM = "flowmesh:delivery-events"

CONSUMER_GROUP = "flowmesh-order-workers"

CONSUMER_NAME = "delivery-event-worker-1"

PENDING_IDLE_THRESHOLD_MS = 60_000

CLAIM_BATCH_SIZE = 10

RECOVERY_INTERVAL_SECONDS = 30

# Shared shutdown signal for the worker.
shutdown_event = threading.Event()


def request_shutdown(signum, frame):
    """Request a graceful worker shutdown."""
    logger.info(
        "Shutdown signal received",
        extra={"signal": signum},
    )
    shutdown_event.set()


def install_signal_handlers():
    """Register handlers for normal termination signals."""
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


def ensure_consumer_group():
    """Create the Redis consumer group if it does not already exist."""
    try:
        redis_client.xgroup_create(
            name=DELIVERY_EVENTS_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )

        logger.info(
            "Created consumer group",
            extra={"consumer_group": CONSUMER_GROUP},
        )

    except Exception as error:
        if "BUSYGROUP" in str(error):
            return
        raise


def process_event(message_id, fields):
    """Process a delivery event and return whether it can be acknowledged."""

    event_type = fields.get("event_type")
    order_id = fields.get("order_id")
    event_id = fields.get("event_id")

    event_context = {
        "message_id": message_id,
        "event_id": event_id,
        "event_type": event_type,
        "order_id": order_id,
    }

    try:
        data = json.loads(fields.get("data", "{}"))

        if not isinstance(data, dict):
            raise ValueError("Event data must be a JSON object")

    except (json.JSONDecodeError, TypeError, ValueError):
        logger.exception(
            "Invalid delivery event data",
            extra=event_context,
        )
        return False

    logger.info(
        "Received delivery event",
        extra={**event_context, "data": data},
    )

    if event_type not in {
        "delivery.assigned",
        "delivery.status_updated",
    }:
        logger.warning(
            "Ignoring unsupported delivery event",
            extra=event_context,
        )
        return True

    if not order_id:
        logger.error(
            "Delivery event is missing order_id",
            extra=event_context,
        )
        return False

    db = SessionLocal()

    try:
        order = db.get(Order, order_id)

        if order is None:
            logger.warning(
                "Order not found",
                extra=event_context,
            )
            return False

        logger.info(
            "Current order status",
            extra={
                **event_context,
                "order_status": order.status,
            },
        )

        if event_type == "delivery.assigned":
            return handle_delivery_assigned(
                db=db,
                order=order,
                order_id=order_id,
            )

        if event_type == "delivery.status_updated":
            return handle_delivery_status_updated(
                db=db,
                order=order,
                order_id=order_id,
                data=data,
            )

        return True

    except SQLAlchemyError:
        db.rollback()

        logger.exception(
            "Database error while processing delivery event",
            extra=event_context,
        )
        return False

    except Exception:
        db.rollback()

        logger.exception(
            "Unexpected error processing delivery event",
            extra=event_context,
        )
        return False

    finally:
        db.close()


def handle_delivery_assigned(db, order, order_id):
    """Confirm an order when its delivery has been assigned."""

    event_context = {"order_id": order_id}

    if order.status == "PENDING":
        order.status = "CONFIRMED"

        try:
            db.commit()

            logger.info(
                "Order status updated",
                extra={
                    **event_context,
                    "previous_status": "PENDING",
                    "new_status": "CONFIRMED",
                },
            )

            return True

        except SQLAlchemyError:
            db.rollback()

            logger.exception(
                "Failed to confirm order",
                extra=event_context,
            )
            return False

    if order.status == "CONFIRMED":
        logger.info(
            "Order already confirmed; treating event as processed",
            extra=event_context,
        )
        return True

    logger.warning(
        "Order is not in PENDING state",
        extra={
            **event_context,
            "current_status": order.status,
        },
    )

    # The event cannot currently be applied.
    return False


def handle_delivery_status_updated(db, order, order_id, data):
    """Validate delivery progress without changing the order status."""

    delivery_status = data.get("status")

    event_context = {"order_id": order_id}

    if delivery_status is None:
        logger.warning(
            "Delivery status missing from event",
            extra=event_context,
        )
        return False

    logger.info(
        "Delivery status received",
        extra={
            **event_context,
            "delivery_status": delivery_status,
        },
    )

    if delivery_status in {"PICKED_UP", "IN_TRANSIT", "DELIVERED"}:
        logger.info(
            "Delivery progress is handled by order_status_worker; "
            "order status remains unchanged",
            extra={
                **event_context,
                "delivery_status": delivery_status,
                "order_status": order.status,
            },
        )
        return True

    logger.warning(
        "Unsupported delivery status",
        extra={
            **event_context,
            "delivery_status": delivery_status,
        },
    )
    return False


def acknowledge_event(message_id):
    """Acknowledge a successfully processed Redis message."""

    acknowledged = redis_client.xack(
        DELIVERY_EVENTS_STREAM,
        CONSUMER_GROUP,
        message_id,
    )

    if acknowledged:
        logger.info(
            "Delivery event acknowledged",
            extra={"message_id": message_id},
        )
    else:
        logger.warning(
            "Delivery event was not acknowledged",
            extra={"message_id": message_id},
        )

    return bool(acknowledged)


def handle_processing_failure(message_id, fields, error):
    """Apply the shared retry and dead-letter policy to a failed event."""

    event_context = {
        "message_id": message_id,
        "event_id": fields.get("event_id"),
        "order_id": fields.get("order_id"),
    }

    try:
        result = handle_failed_message(
            redis_client=redis_client,
            stream=DELIVERY_EVENTS_STREAM,
            group=CONSUMER_GROUP,
            message_id=message_id,
            fields=fields,
            error=str(error),
        )

        if result == "retry":
            logger.warning(
                "Delivery event scheduled for retry",
                extra=event_context,
            )

        elif result == "dead_lettered":
            logger.warning(
                "Delivery event moved to dead-letter stream",
                extra=event_context,
            )

    except redis.exceptions.RedisError:
        logger.exception(
            "Could not apply retry policy to delivery event",
            extra=event_context,
        )


def process_message(message_id, fields):
    """Process one message and apply ACK, retry, or dead-letter behavior."""

    event_context = {
        "message_id": message_id,
        "event_id": fields.get("event_id"),
        "order_id": fields.get("order_id"),
    }

    try:
        processed = process_event(message_id, fields)

    except Exception as error:
        logger.exception(
            "Error processing delivery event",
            extra=event_context,
        )

        handle_processing_failure(
            message_id,
            fields,
            error,
        )
        return

    if not processed:
        handle_processing_failure(
            message_id,
            fields,
            "Event processing returned False",
        )
        return

    try:
        acknowledged = acknowledge_event(message_id)

    except redis.exceptions.RedisError:
        # Processing succeeded, but ACK failed.
        # Leave the message pending for recovery.
        increment_metric(
            redis_client,
            EVENTS_ACK_FAILED_TOTAL,
        )

        logger.exception(
            "Could not acknowledge delivery event",
            extra=event_context,
        )
        return

    if acknowledged:
        increment_metric(
            redis_client,
            EVENTS_PROCESSED_TOTAL,
        )
    else:
        increment_metric(
            redis_client,
            EVENTS_ACK_FAILED_TOTAL,
        )


def recover_pending_messages():
    """Claim and retry eligible messages left pending by a consumer."""

    logger.info("Checking for pending delivery events")

    next_id = "0-0"

    while not shutdown_event.is_set():
        try:
            response = redis_client.xautoclaim(
                name=DELIVERY_EVENTS_STREAM,
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                min_idle_time=PENDING_IDLE_THRESHOLD_MS,
                start_id=next_id,
                count=CLAIM_BATCH_SIZE,
            )

            next_id, messages, _deleted_ids = response

        except redis.exceptions.RedisError:
            logger.exception(
                "Redis error while recovering delivery events"
            )
            return

        except (TypeError, ValueError):
            logger.exception("Unexpected XAUTOCLAIM response")
            return

        # Finish processing all messages already claimed.
        for message_id, fields in messages:
            increment_metric(
                redis_client,
                EVENTS_RECOVERED_TOTAL,
            )

            process_message(message_id, fields)

        # Stop scanning for additional batches when shutdown is requested.
        if shutdown_event.is_set():
            break

        if next_id == "0-0":
            break


def main():
    """Consume events and shut down gracefully when requested."""

    install_signal_handlers()

    # Respect a shutdown request that was already received.
    if shutdown_event.is_set():
        logger.info("Shutdown already requested. Worker will not start.")
        return

    ensure_consumer_group()

    if shutdown_event.is_set():
        logger.info(
            "Shutdown requested. Skipping pending-message recovery."
        )
        return

    recover_pending_messages()

    if shutdown_event.is_set():
        logger.info(
            "Shutdown requested. Skipping new message consumption."
        )
        logger.info("Delivery Event Worker shut down gracefully")
        return

    last_recovery_time = time.monotonic()

    logger.info(
        "Delivery Event Worker running",
        extra={
            "stream": DELIVERY_EVENTS_STREAM,
            "consumer_group": CONSUMER_GROUP,
            "consumer_name": CONSUMER_NAME,
        },
    )

    logger.info("Press Ctrl+C to shut down gracefully")

    try:
        while not shutdown_event.is_set():
            try:
                messages = redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={DELIVERY_EVENTS_STREAM: ">"},
                    count=10,
                    block=5000,
                )

                # Finish the batch already fetched before exiting.
                for _stream_name, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        process_message(message_id, fields)

                if shutdown_event.is_set():
                    break

                now = time.monotonic()

                if now - last_recovery_time >= RECOVERY_INTERVAL_SECONDS:
                    recover_pending_messages()
                    last_recovery_time = now

            except redis.exceptions.TimeoutError:
                continue

            except redis.exceptions.RedisError:
                logger.exception("Redis worker error")

                if not shutdown_event.is_set():
                    time.sleep(2)

            except Exception:
                logger.exception("Unexpected worker error")

                if not shutdown_event.is_set():
                    time.sleep(2)

            if not shutdown_event.is_set():
                time.sleep(0.1)

    finally:
        logger.info("Delivery Event Worker shut down gracefully")


if __name__ == "__main__":
    main()