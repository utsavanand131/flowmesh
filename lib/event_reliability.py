
import json
from datetime import datetime, timezone
from typing import Any


MAX_DELIVERY_ATTEMPTS = 5

DEAD_LETTER_STREAM = "flowmesh:dead-letter-events"


def get_delivery_attempts(
    redis_client,
    stream: str,
    group: str,
    message_id: str,
) -> int:
    """
    Return the number of times Redis has delivered this message
    to consumers in the specified consumer group.
    """
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
    """
    Publish an exhausted message to the dead-letter stream.

    The original message is acknowledged only after the dead-letter
    record has been successfully published.
    """
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

    redis_client.xack(
        stream,
        group,
        message_id,
    )

    print(
        f"Message moved to dead-letter stream: "
        f"{message_id} -> {dead_letter_id}"
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
    """
    Decide whether a failed message should remain pending
    or be moved to the dead-letter stream.

    Returns:
        "retry"        - message remains pending
        "dead_lettered" - message was published and acknowledged
    """
    attempts = get_delivery_attempts(
        redis_client=redis_client,
        stream=stream,
        group=group,
        message_id=message_id,
    )

    print(
        f"Message {message_id} failed. "
        f"Delivery attempts: {attempts}/{MAX_DELIVERY_ATTEMPTS}"
    )

    if attempts < MAX_DELIVERY_ATTEMPTS:
        print(f"Message {message_id} will remain pending for retry.")
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
