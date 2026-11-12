import json
from datetime import datetime, timezone
from typing import Any

from lib.logger import get_logger
from lib.metrics import (
    EVENTS_FAILED_TOTAL,
    EVENTS_RETRIED_TOTAL,
    EVENTS_DEAD_LETTERED_TOTAL,
    increment_metric,
)

logger = get_logger(__name__)

MAX_DELIVERY_ATTEMPTS = 5
DEAD_LETTER_STREAM = "flowmesh:dead-letter-events"


def get_delivery_attempts(
    redis_client,
    stream: str,
    group: str,
    message_id: str,
) -> int:
    pending_entries = redis_client.xpending_range(
        name=stream,
        groupname=group,
        min=message_id,
        max=message_id,
        count=1,
    )

    if not pending_entries:
        return 0

    return int(pending_entries[0]["times_delivered"])


def publish_dead_letter(
    redis_client,
    stream: str,
    group: str,
    message_id: str,
    fields: dict[str, Any],
    attempts: int,
    error: str,
) -> str:
    dead_letter_record = {
        "original_stream": stream,
        "original_group": group,
        "original_message_id": message_id,
        "event_id": str(fields.get("event_id", "")),
        "event_type": str(fields.get("event_type", "")),
        "attempts": str(attempts),
        "error": str(error),
        "original_fields": json.dumps(fields),
        "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
    }

    dead_letter_id = redis_client.xadd(
        DEAD_LETTER_STREAM,
        dead_letter_record,
    )

    redis_client.xack(stream, group, message_id)

    increment_metric(
        redis_client,
        EVENTS_DEAD_LETTERED_TOTAL,
    )

    logger.warning(
        "Message moved to dead-letter stream",
        extra={
            "original_stream": stream,
            "original_message_id": message_id,
            "dead_letter_id": dead_letter_id,
            "event_id": str(fields.get("event_id", "")),
            "attempts": attempts,
        },
    )

    return dead_letter_id


def handle_failed_message(
    redis_client,
    stream: str,
    group: str,
    message_id: str,
    fields: dict[str, Any],
    error: str,
) -> str:
    increment_metric(
        redis_client,
        EVENTS_FAILED_TOTAL,
    )

    attempts = get_delivery_attempts(
        redis_client,
        stream,
        group,
        message_id,
    )

    logger.warning(
        "Event processing failed",
        extra={
            "stream": stream,
            "message_id": message_id,
            "event_id": str(fields.get("event_id", "")),
            "attempts": attempts,
            "max_attempts": MAX_DELIVERY_ATTEMPTS,
            "error": str(error),
        },
    )

    if attempts < MAX_DELIVERY_ATTEMPTS:
        increment_metric(
            redis_client,
            EVENTS_RETRIED_TOTAL,
        )

        logger.info(
            "Message will remain pending for retry",
            extra={
                "stream": stream,
                "message_id": message_id,
                "attempts": attempts,
            },
        )

        return "retry"

    publish_dead_letter(
        redis_client=redis_client,
        stream=stream,
        group=group,
        message_id=message_id,
        fields=fields,
        attempts=attempts,
        error=error,
    )

    return "dead_lettered"