
import json
import signal
import threading
import time

import redis

from lib.event_reliability import handle_failed_message
from lib.events import ORDER_EVENTS_STREAM
from lib.logger import get_logger
from lib.metrics import (
    EVENTS_ACK_FAILED_TOTAL,
    EVENTS_PROCESSED_TOTAL,
    EVENTS_RECOVERED_TOTAL,
    increment_metric,
)
from lib.redis import redis_client
from workers.delivery_client import create_delivery


logger = get_logger(__name__)

CONSUMER_GROUP = "flowmesh-workers"
CONSUMER_NAME = "order-event-worker-1"

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
            name=ORDER_EVENTS_STREAM,
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


def process_event(message_id, fields=None):
    """Process an order event and return whether it can be acknowledged."""
    if fields is None:
        fields = message_id

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
            "Invalid event data",
            extra=event_context,
        )
        return False

    logger.info(
        "Received order event",
        extra={**event_context, "data": data},
    )

    if event_type == "order.created":
        if not order_id:
            logger.warning(
                "Skipping order.created event without an order_id",
                extra=event_context,
            )
            return True

        if not event_id:
            logger.error(
                "Order event is missing event_id",
                extra=event_context,
            )
            return False

        result = create_delivery(
            order_id=order_id,
            event_id=event_id,
        )

        if isinstance(result, dict) and result.get("already_exists"):
            logger.info(
                "Delivery already exists",
                extra=event_context,
            )
            return True

        if result is None:
            logger.warning(
                "Could not create delivery",
                extra=event_context,
            )
            return False

        logger.info(
            "Delivery processed successfully",
            extra=event_context,
        )
        return True

    logger.warning(
        "Ignoring unsupported event type",
        extra=event_context,
    )
    return True


def acknowledge_event(message_id):
    """Acknowledge a successfully processed Redis message."""
    redis_client.xack(
        ORDER_EVENTS_STREAM,
        CONSUMER_GROUP,
        message_id,
    )


def handle_processing_failure(message_id, fields, error):
    """Apply the shared retry and dead-letter policy to a failed event."""
    try:
        result = handle_failed_message(
            redis_client=redis_client,
            stream=ORDER_EVENTS_STREAM,
            group=CONSUMER_GROUP,
            message_id=message_id,
            fields=fields,
            error=str(error),
        )

        if result == "dead_lettered":
            logger.warning(
                "Event moved to dead-letter stream",
                extra={
                    "message_id": message_id,
                    "event_id": fields.get("event_id"),
                    "order_id": fields.get("order_id"),
                },
            )

    except redis.exceptions.RedisError:
        logger.exception(
            "Could not apply retry policy",
            extra={
                "message_id": message_id,
                "event_id": fields.get("event_id"),
                "order_id": fields.get("order_id"),
            },
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

        if processed:
            try:
                acknowledge_event(message_id)
            except Exception:
                increment_metric(
                    redis_client,
                    EVENTS_ACK_FAILED_TOTAL,
                )
                raise

            increment_metric(
                redis_client,
                EVENTS_PROCESSED_TOTAL,
            )

            logger.info(
                "Acknowledged event",
                extra=event_context,
            )
            return

        handle_processing_failure(
            message_id,
            fields,
            "Event processing returned False",
        )

    except Exception as error:
        logger.exception(
            "Error processing event",
            extra=event_context,
        )

        handle_processing_failure(
            message_id,
            fields,
            error,
        )


def recover_pending_messages():
    """Claim and retry messages left pending by previous consumers."""
    logger.info("Checking for pending order events")

    next_id = "0-0"

    while True:
        try:
            response = redis_client.xautoclaim(
                name=ORDER_EVENTS_STREAM,
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                min_idle_time=PENDING_IDLE_THRESHOLD_MS,
                start_id=next_id,
                count=CLAIM_BATCH_SIZE,
            )

            next_id, messages, _deleted_ids = response

        except redis.exceptions.RedisError:
            logger.exception("Redis error while recovering pending events")
            return

        except (TypeError, ValueError):
            logger.exception("Unexpected XAUTOCLAIM response")
            return

        for message_id, fields in messages:
            increment_metric(
                redis_client,
                EVENTS_RECOVERED_TOTAL,
            )
            process_message(message_id, fields)

        if next_id == "0-0":
            break


def main():
    """Consume events and shut down gracefully when requested."""
    install_signal_handlers()

    # Do not clear shutdown_event here.
    # A previously requested shutdown must be respected.
    if shutdown_event.is_set():
        logger.info("Shutdown already requested. Worker will not start.")
        return

    ensure_consumer_group()

    if not shutdown_event.is_set():
        recover_pending_messages()

    last_recovery_time = time.monotonic()

    logger.info(
        "Order event worker is running",
        extra={
            "consumer_group": CONSUMER_GROUP,
            "consumer_name": CONSUMER_NAME,
            "stream": ORDER_EVENTS_STREAM,
        },
    )
    logger.info("Press Ctrl+C to shut down gracefully")

    try:
        while not shutdown_event.is_set():
            try:
                response = redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={ORDER_EVENTS_STREAM: ">"},
                    count=10,
                    block=5000,
                )

                # Finish every message already fetched, even if a shutdown
                # signal arrives while this batch is being processed.
                for _stream_name, messages in response:
                    for message_id, fields in messages:
                        process_message(message_id, fields)

                if shutdown_event.is_set():
                    break

                now = time.monotonic()

                if now - last_recovery_time >= RECOVERY_INTERVAL_SECONDS:
                    recover_pending_messages()
                    last_recovery_time = now

            except redis.exceptions.TimeoutError:
                logger.warning("Redis read timed out; retrying")

            except redis.exceptions.RedisError:
                logger.exception("Redis error in order event worker")

                if not shutdown_event.is_set():
                    time.sleep(2)

            except Exception:
                logger.exception("Unexpected order event worker error")

                if not shutdown_event.is_set():
                    time.sleep(2)

    finally:
        logger.info("Order event worker shut down gracefully")


if __name__ == "__main__":
    main()
