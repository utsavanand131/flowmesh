
from lib.logger import get_logger

logger = get_logger(__name__)

METRIC_PREFIX = "flowmesh:metrics:"

EVENTS_PROCESSED_TOTAL = "events_processed_total"
EVENTS_FAILED_TOTAL = "events_failed_total"
EVENTS_RETRIED_TOTAL = "events_retried_total"
EVENTS_DEAD_LETTERED_TOTAL = "events_dead_lettered_total"
EVENTS_RECOVERED_TOTAL = "events_recovered_total"
EVENTS_ACK_FAILED_TOTAL = "events_ack_failed_total"

EVENTS_ACK_ZERO_TOTAL = "events_ack_zero_total"
EVENTS_ACK_EXCEPTION_TOTAL = "events_ack_exception_total"


def increment_metric(
    redis_client,
    metric_name: str,
    amount: int = 1,
) -> bool:
    """
    Increment a shared Redis metric counter.

    Returns True if the counter was updated successfully.
    Returns False if metric recording fails.

    Metric failures must never interrupt event processing.
    """
    if not isinstance(amount, int) or amount <= 0:
        logger.warning(
            "Invalid metric increment amount",
            extra={"metric_name": metric_name, "amount": amount},
        )
        return False

    key = f"{METRIC_PREFIX}{metric_name}"

    try:
        redis_client.incr(key, amount)
        return True

    except Exception:
        logger.exception(
            "Failed to increment metric",
            extra={
                "metric_name": metric_name,
                "redis_key": key,
            },
        )
        return False


def get_metric(redis_client, metric_name: str) -> int:
    """
    Read a metric counter from Redis.

    Returns zero if the counter does not exist.
    """
    key = f"{METRIC_PREFIX}{metric_name}"

    value = redis_client.get(key)

    if value is None:
        return 0

    return int(value)
