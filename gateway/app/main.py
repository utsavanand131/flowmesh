import grpc
import json

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis.exceptions import RedisError, ResponseError
from sqlalchemy import text

from services.delivery_service.app import delivery_pb2
from services.delivery_service.app import delivery_pb2_grpc
from services.order_service.app import order_pb2
from services.order_service.app import order_pb2_grpc
from services.inventory_service.app import inventory_pb2
from services.inventory_service.app import inventory_pb2_grpc
from services.order_service.app.database import engine

from lib.events import (
    ORDER_EVENTS_STREAM,
    DELIVERY_EVENTS_STREAM,
)

from lib.event_reliability import DEAD_LETTER_STREAM

from lib.metrics import (
    EVENTS_PROCESSED_TOTAL,
    EVENTS_FAILED_TOTAL,
    EVENTS_RETRIED_TOTAL,
    EVENTS_DEAD_LETTERED_TOTAL,
    EVENTS_RECOVERED_TOTAL,
    EVENTS_ACK_FAILED_TOTAL,
    EVENTS_ACK_ZERO_TOTAL,
    EVENTS_ACK_EXCEPTION_TOTAL,
    get_metric,
)

from lib.redis import redis_client

from .auth_routes import (
    router as auth_router,
    require_current_user,
    require_admin_user,
)

app = FastAPI(
    title="FlowMesh API Gateway",
    version="1.0.0",
)


# -------------------------------------------------------------------
# CORS configuration for Next.js frontend
# -------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)


# -------------------------------------------------------------------
# Event stream monitoring configuration
# -------------------------------------------------------------------

EVENT_STREAMS = {
    "order": ORDER_EVENTS_STREAM,
    "delivery": DELIVERY_EVENTS_STREAM,
    "dead_letter": DEAD_LETTER_STREAM,
}

ACTIVITY_STREAMS = {
    "order": ORDER_EVENTS_STREAM,
    "delivery": DELIVERY_EVENTS_STREAM,
}

CONSUMER_GROUPS = {
    ORDER_EVENTS_STREAM: ["flowmesh-workers"],
    DELIVERY_EVENTS_STREAM: ["flowmesh-order-workers"],
}

DEFAULT_EVENT_PAGE_SIZE = 20
MAX_EVENT_PAGE_SIZE = 100
MAX_ACTIVITY_SCAN = 500
MAX_DEAD_LETTER_SCAN = 5000


# -------------------------------------------------------------------
# Request models
# -------------------------------------------------------------------


class CreateOrderRequest(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class UpdateDeliveryStatusRequest(BaseModel):
    status: str


# -------------------------------------------------------------------
# Event monitoring helpers
# -------------------------------------------------------------------


def _redis_unavailable():
    raise HTTPException(
        status_code=503,
        detail="Event monitoring service unavailable",
    )


def _get_stream_length(stream: str) -> int:
    return int(redis_client.xlen(stream))


def _get_stream_info(stream: str) -> dict[str, Any]:
    """
    Return Redis stream metadata.

    Stream existence is checked independently from its length,
    because a stream may have consumer groups even when empty.
    """

    exists = bool(redis_client.exists(stream))

    if not exists:
        return {
            "exists": False,
            "length": 0,
            "first_entry": None,
            "last_entry": None,
            "groups": 0,
        }

    length = _get_stream_length(stream)
    info = redis_client.xinfo_stream(stream)

    first_entry = info.get("first-entry")
    last_entry = info.get("last-entry")

    return {
        "exists": True,
        "length": length,
        "first_entry": (
            {
                "message_id": first_entry[0],
                "fields": first_entry[1],
            }
            if first_entry
            else None
        ),
        "last_entry": (
            {
                "message_id": last_entry[0],
                "fields": last_entry[1],
            }
            if last_entry
            else None
        ),
        "groups": info.get("groups", 0),
    }


def _get_consumer_group_info(stream: str) -> list[dict[str, Any]]:
    """
    Return consumer groups and consumer information for a stream.
    """

    try:
        groups = redis_client.xinfo_groups(stream)
    except ResponseError:
        return []

    result = []

    for group in groups:
        group_name = group.get("name")

        try:
            consumers = redis_client.xinfo_consumers(
                stream,
                group_name,
            )
        except ResponseError:
            consumers = []

        result.append(
            {
                "stream": stream,
                "group": group_name,
                "consumers_count": group.get("consumers", 0),
                "pending_count": group.get("pending", 0),
                "last_delivered_id": group.get("last-delivered-id"),
                "entries_read": group.get("entries-read"),
                "lag": group.get("lag"),
                "consumers": [
                    {
                        "name": consumer.get("name"),
                        "pending_count": consumer.get(
                            "pending",
                            0,
                        ),
                        "idle_ms": consumer.get("idle"),
                    }
                    for consumer in consumers
                ],
            }
        )

    return result


def _decode_event_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """
    Decode the JSON event data field while preserving invalid data.
    """

    decoded = dict(fields)

    raw_data = decoded.get("data")

    if raw_data is not None:
        try:
            decoded["data"] = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            decoded["data"] = raw_data

    return decoded


def _message_timestamp(message_id: str) -> int:
    """
    Extract the millisecond timestamp from a Redis stream ID.
    """

    try:
        return int(message_id.split("-", 1)[0])
    except (ValueError, AttributeError):
        return 0


def _get_recent_activity(
    stream_name: str,
    stream: str,
    scan_limit: int,
    event_type: str | None = None,
    order_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Read recent stream entries and apply optional filters.
    """

    entries = redis_client.xrevrange(
        stream,
        count=scan_limit,
    )

    results = []

    for message_id, fields in entries:
        if event_type and fields.get("event_type") != event_type:
            continue

        if order_id and fields.get("order_id") != order_id:
            continue

        results.append(
            {
                "stream_key": stream,
                "stream": stream_name,
                "message_id": message_id,
                "event_id": fields.get("event_id"),
                "event_type": fields.get("event_type"),
                "order_id": fields.get("order_id"),
                "timestamp_ms": _message_timestamp(message_id),
                "fields": _decode_event_fields(fields),
            }
        )

    return results


def _get_dead_letter_record(
    message_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """
    Decode a dead-letter record, including its original fields.
    """

    record = dict(fields)

    original_fields = record.get("original_fields")

    if original_fields:
        try:
            record["original_fields"] = json.loads(original_fields)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "dead_letter_message_id": message_id,
        **record,
    }


# -------------------------------------------------------------------
# Basic health check
# -------------------------------------------------------------------


@app.get("/health")
def health_check():
    return {
        "service": "api-gateway",
        "status": "healthy",
    }


# -------------------------------------------------------------------
# Admin service health monitoring
# -------------------------------------------------------------------


@app.get("/admin/services/health")
def get_services_health(
    current_user=Depends(require_admin_user),
):
    services = {}

    # API Gateway
    services["api_gateway"] = "healthy"

    # gRPC service health checks
    def check_grpc_service(name: str, port: int):
        channel = grpc.insecure_channel(f"localhost:{port}")

        try:
            grpc.channel_ready_future(channel).result(timeout=2)

            services[name] = "healthy"

        except grpc.FutureTimeoutError:
            services[name] = "unhealthy"

        finally:
            channel.close()

    check_grpc_service("order_service", 50051)
    check_grpc_service("inventory_service", 50052)
    check_grpc_service("delivery_service", 50053)

    # PostgreSQL health check
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        services["postgresql"] = "healthy"

    except Exception:
        services["postgresql"] = "unhealthy"

    # Redis health check
    try:
        redis_client.ping()
        services["redis"] = "healthy"

    except RedisError:
        services["redis"] = "unhealthy"

    overall_status = (
        "healthy"
        if all(status == "healthy" for status in services.values())
        else "degraded"
    )

    return {
        "status": overall_status,
        "services": services,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# -------------------------------------------------------------------
# Worker metrics
# -------------------------------------------------------------------


@app.get("/metrics")
def get_worker_metrics(
    current_user=Depends(require_admin_user),
):
    """Return cumulative FlowMesh worker metrics stored in Redis."""

    try:
        return {
            "events_processed_total": get_metric(
                redis_client,
                EVENTS_PROCESSED_TOTAL,
            ),
            "events_failed_total": get_metric(
                redis_client,
                EVENTS_FAILED_TOTAL,
            ),
            "events_retried_total": get_metric(
                redis_client,
                EVENTS_RETRIED_TOTAL,
            ),
            "events_dead_lettered_total": get_metric(
                redis_client,
                EVENTS_DEAD_LETTERED_TOTAL,
            ),
            "events_recovered_total": get_metric(
                redis_client,
                EVENTS_RECOVERED_TOTAL,
            ),
            "events_ack_failed_total": get_metric(
                redis_client,
                EVENTS_ACK_FAILED_TOTAL,
            ),
            "events_ack_zero_total": get_metric(
                redis_client,
                EVENTS_ACK_ZERO_TOTAL,
            ),
            "events_ack_exception_total": get_metric(
                redis_client,
                EVENTS_ACK_EXCEPTION_TOTAL,
            ),
        }

    except RedisError:
        raise HTTPException(
            status_code=503,
            detail="Metrics service unavailable",
        )


# -------------------------------------------------------------------
# Admin event monitoring - overview
# -------------------------------------------------------------------


@app.get("/admin/events/overview")
def get_event_overview(
    current_user=Depends(require_admin_user),
):
    """
    Return cumulative event metrics and current Redis stream state.
    """

    try:
        metrics = {
            "events_processed_total": get_metric(
                redis_client,
                EVENTS_PROCESSED_TOTAL,
            ),
            "events_failed_total": get_metric(
                redis_client,
                EVENTS_FAILED_TOTAL,
            ),
            "events_retried_total": get_metric(
                redis_client,
                EVENTS_RETRIED_TOTAL,
            ),
            "events_dead_lettered_total": get_metric(
                redis_client,
                EVENTS_DEAD_LETTERED_TOTAL,
            ),
            "events_recovered_total": get_metric(
                redis_client,
                EVENTS_RECOVERED_TOTAL,
            ),
            "events_ack_failed_total": get_metric(
                redis_client,
                EVENTS_ACK_FAILED_TOTAL,
            ),
            "events_ack_zero_total": get_metric(
                redis_client,
                EVENTS_ACK_ZERO_TOTAL,
            ),
            "events_ack_exception_total": get_metric(
                redis_client,
                EVENTS_ACK_EXCEPTION_TOTAL,
            ),
        }

        streams = {}
        total_stream_entries = 0
        total_pending = 0

        for name, stream in EVENT_STREAMS.items():
            stream_length = _get_stream_length(stream)

            streams[name] = {
                "stream_key": stream,
                "length": stream_length,
            }

            total_stream_entries += stream_length

            for group in _get_consumer_group_info(stream):
                total_pending += group["pending_count"]

        return {
            "metrics": metrics,
            "streams": streams,
            "current_state": {
                "total_stream_entries": total_stream_entries,
                "total_pending_messages": total_pending,
            },
            "metric_note": (
                "Metrics are cumulative counters. "
                "Failed and retried totals represent attempts, "
                "not the number of currently pending events."
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except RedisError:
        _redis_unavailable()


# -------------------------------------------------------------------
# Admin event monitoring - stream information
# -------------------------------------------------------------------


@app.get("/admin/events/streams")
def get_event_streams(
    current_user=Depends(require_admin_user),
):
    """
    Return stream lengths, first/last entries and group counts.
    """

    try:
        streams = {}

        for name, stream in EVENT_STREAMS.items():
            info = _get_stream_info(stream)

            streams[name] = {
                "stream_key": stream,
                **info,
            }

        return {
            "streams": streams,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except RedisError:
        _redis_unavailable()


# -------------------------------------------------------------------
# Admin event monitoring - recent activity
# -------------------------------------------------------------------


@app.get("/admin/events/activity")
def get_event_activity(
    stream: str | None = Query(
        default=None,
        description="Optional stream: order or delivery",
    ),
    event_type: str | None = Query(default=None),
    order_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_EVENT_PAGE_SIZE,
        ge=1,
        le=MAX_EVENT_PAGE_SIZE,
    ),
    current_user=Depends(require_admin_user),
):
    """
    Return recent order and delivery events.

    The endpoint scans a bounded number of recent entries per stream.
    """

    if stream is not None and stream not in ACTIVITY_STREAMS:
        raise HTTPException(
            status_code=400,
            detail="Stream must be 'order' or 'delivery'",
        )

    try:
        selected_streams = (
            {stream: ACTIVITY_STREAMS[stream]} if stream else ACTIVITY_STREAMS
        )

        activity = []

        for stream_name, stream_key in selected_streams.items():
            activity.extend(
                _get_recent_activity(
                    stream_name=stream_name,
                    stream=stream_key,
                    scan_limit=MAX_ACTIVITY_SCAN,
                    event_type=event_type,
                    order_id=order_id,
                )
            )

        activity.sort(
            key=lambda item: item["timestamp_ms"],
            reverse=True,
        )

        total = len(activity)
        start = (page - 1) * page_size
        end = start + page_size

        paginated_activity = activity[start:end]

        return {
            "events": paginated_activity,
            "total": total,
            "page": page,
            "page_size": page_size,
            "scanned_limit_per_stream": MAX_ACTIVITY_SCAN,
            "has_more": end < total,
            "note": (
                "Activity is limited to the most recent "
                "scanned entries. Total is the number of "
                "matching entries in that scan, not the "
                "lifetime number of events."
            ),
        }

    except RedisError:
        _redis_unavailable()


# -------------------------------------------------------------------
# Admin event monitoring - consumer groups
# -------------------------------------------------------------------


@app.get("/admin/events/consumer-groups")
def get_event_consumer_groups(
    current_user=Depends(require_admin_user),
):
    """
    Return consumer groups, consumer details and pending counts.
    """

    try:
        result = []

        for stream in (
            ORDER_EVENTS_STREAM,
            DELIVERY_EVENTS_STREAM,
        ):
            groups = _get_consumer_group_info(stream)
            result.extend(groups)

        total_pending = sum(group["pending_count"] for group in result)

        return {
            "consumer_groups": result,
            "total_groups": len(result),
            "total_pending_messages": total_pending,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except RedisError:
        _redis_unavailable()


# -------------------------------------------------------------------
# Admin event monitoring - dead-letter events
# -------------------------------------------------------------------


@app.get("/admin/events/dead-letters")
def get_dead_letter_events(
    original_stream: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=DEFAULT_EVENT_PAGE_SIZE,
        ge=1,
        le=MAX_EVENT_PAGE_SIZE,
    ),
    current_user=Depends(require_admin_user),
):
    """
    Return recent dead-letter records with original event details.

    Filtering is applied before pagination. Scanning is bounded
    to MAX_DEAD_LETTER_SCAN entries.
    """

    if original_stream is not None and original_stream not in {
        ORDER_EVENTS_STREAM,
        DELIVERY_EVENTS_STREAM,
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid original stream",
        )

    try:
        stream_total = _get_stream_length(DEAD_LETTER_STREAM)

        scan_count = min(
            stream_total,
            MAX_DEAD_LETTER_SCAN,
        )

        if scan_count == 0:
            entries = []
        else:
            entries = redis_client.xrevrange(
                DEAD_LETTER_STREAM,
                count=scan_count,
            )

        # Apply filters to the scanned records before pagination.
        matching_records = []

        for message_id, fields in entries:
            if original_stream and fields.get("original_stream") != original_stream:
                continue

            if event_type and fields.get("event_type") != event_type:
                continue

            matching_records.append(
                _get_dead_letter_record(
                    message_id,
                    fields,
                )
            )

        total_matching_scanned = len(matching_records)

        start = (page - 1) * page_size
        end = start + page_size

        paginated_records = matching_records[start:end]

        # More matching records exist in the scanned entries,
        # or additional stream entries were outside the scan limit.
        has_more = end < total_matching_scanned or scan_count < stream_total

        return {
            "dead_letters": paginated_records,
            "total": stream_total,
            "matching_scanned": total_matching_scanned,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
            "scan_limit": MAX_DEAD_LETTER_SCAN,
            "scan_truncated": scan_count < stream_total,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    except RedisError:
        _redis_unavailable()


# -------------------------------------------------------------------
# Create order
# -------------------------------------------------------------------


@app.post("/orders")
def create_order(
    request: CreateOrderRequest,
    current_user=Depends(require_current_user),
):
    channel = grpc.insecure_channel("localhost:50051")
    stub = order_pb2_grpc.OrderServiceStub(channel)

    grpc_request = order_pb2.CreateOrderRequest(
        user_id=current_user.id,
        product_id=request.product_id,
        quantity=request.quantity,
    )

    try:
        response = stub.CreateOrder(grpc_request)

    except grpc.RpcError as error:
        print(
            "Order Service gRPC error:",
            error.code(),
            error.details(),
        )

        if error.code() == grpc.StatusCode.FAILED_PRECONDITION:
            raise HTTPException(
                status_code=409,
                detail="Insufficient inventory",
            )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Order service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Order service unavailable",
        )

    finally:
        channel.close()

    delivery = None

    if response.delivery_id:
        delivery = {
            "delivery_id": response.delivery_id,
            "status": response.delivery_status,
        }

    return {
        "order_id": response.order_id,
        "status": response.status,
        "delivery": delivery,
    }


# -------------------------------------------------------------------
# List orders
# -------------------------------------------------------------------


@app.get("/orders")
def list_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_current_user),
):
    channel = grpc.insecure_channel("localhost:50051")
    stub = order_pb2_grpc.OrderServiceStub(channel)

    # Admins can retrieve all orders.
    # Customers can retrieve only their own orders.
    user_id = "" if current_user.role == "ADMIN" else current_user.id

    grpc_request = order_pb2.ListOrdersRequest(
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    try:
        response = stub.ListOrders(grpc_request)

    except grpc.RpcError as error:
        print(
            "Order Service gRPC error:",
            error.code(),
            error.details(),
        )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Order service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve orders",
        )

    finally:
        channel.close()

    orders = []

    for order in response.orders:
        delivery = None

        if order.delivery_id:
            delivery = {
                "delivery_id": order.delivery_id,
                "status": order.delivery_status,
            }

        orders.append(
            {
                "order_id": order.order_id,
                "user_id": order.user_id,
                "product_id": order.product_id,
                "quantity": order.quantity,
                "status": order.status,
                "delivery": delivery,
            }
        )

    return {
        "orders": orders,
        "total": response.total,
        "page": response.page,
        "page_size": response.page_size,
    }


# -------------------------------------------------------------------
# Get order
# -------------------------------------------------------------------


@app.get("/orders/{order_id}")
def get_order(
    order_id: str,
    current_user=Depends(require_current_user),
):
    channel = grpc.insecure_channel("localhost:50051")
    stub = order_pb2_grpc.OrderServiceStub(channel)

    grpc_request = order_pb2.GetOrderRequest(order_id=order_id)

    try:
        response = stub.GetOrder(grpc_request)

    except grpc.RpcError as error:
        if error.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Order service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve order",
        )

    finally:
        channel.close()

    # Customers can only retrieve their own orders.
    # Admins can retrieve any order.
    if current_user.role != "ADMIN" and response.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    delivery = None

    if response.delivery_id:
        delivery = {
            "delivery_id": response.delivery_id,
            "status": response.delivery_status,
        }

    return {
        "order_id": response.order_id,
        "user_id": response.user_id,
        "product_id": response.product_id,
        "quantity": response.quantity,
        "status": response.status,
        "delivery": delivery,
    }


# -------------------------------------------------------------------
# List deliveries
# -------------------------------------------------------------------


@app.get("/deliveries")
def list_deliveries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user=Depends(require_admin_user),
):
    channel = grpc.insecure_channel("localhost:50053")
    stub = delivery_pb2_grpc.DeliveryServiceStub(channel)

    grpc_request = delivery_pb2.ListDeliveriesRequest(
        page=page,
        page_size=page_size,
    )

    try:
        response = stub.ListDeliveries(grpc_request)

    except grpc.RpcError as error:
        print(
            "Delivery Service gRPC error:",
            error.code(),
            error.details(),
        )

        if error.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise HTTPException(
                status_code=400,
                detail=error.details(),
            )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Delivery service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve deliveries",
        )

    finally:
        channel.close()

    deliveries = [
        {
            "delivery_id": delivery.delivery_id,
            "order_id": delivery.order_id,
            "status": delivery.status,
        }
        for delivery in response.deliveries
    ]

    return {
        "deliveries": deliveries,
        "total": response.total,
        "page": response.page,
        "page_size": response.page_size,
        # Global status counts across all deliveries
        "status_counts": {
            "assigned": response.assigned_count,
            "picked_up": response.picked_up_count,
            "in_transit": response.in_transit_count,
            "delivered": response.delivered_count,
        },
    }


# -------------------------------------------------------------------
# List inventory
# -------------------------------------------------------------------


@app.get("/inventory")
def list_inventory(
    current_user=Depends(require_admin_user),
):
    channel = grpc.insecure_channel("localhost:50052")
    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    try:
        response = stub.ListInventory(inventory_pb2.ListInventoryRequest())

    except grpc.RpcError as error:
        print(
            "Inventory Service gRPC error:",
            error.code(),
            error.details(),
        )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Inventory service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve inventory",
        )

    finally:
        channel.close()

    return {
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
            }
            for item in response.items
        ],
        "total_items": response.total_items,
        "total_quantity": response.total_quantity,
    }


# -------------------------------------------------------------------
# Update delivery status
# -------------------------------------------------------------------


@app.patch("/deliveries/{delivery_id}/status")
def update_delivery_status(
    delivery_id: str,
    request: UpdateDeliveryStatusRequest,
    current_user=Depends(require_admin_user),
):
    allowed_statuses = {
        "PICKED_UP",
        "IN_TRANSIT",
        "DELIVERED",
    }

    if request.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid delivery status. "
                "Allowed values: PICKED_UP, IN_TRANSIT, DELIVERED"
            ),
        )

    channel = grpc.insecure_channel("localhost:50053")
    stub = delivery_pb2_grpc.DeliveryServiceStub(channel)

    grpc_request = delivery_pb2.UpdateDeliveryStatusRequest(
        delivery_id=delivery_id,
        status=request.status,
    )

    try:
        response = stub.UpdateDeliveryStatus(grpc_request)

    except grpc.RpcError as error:
        print(
            "Delivery Service gRPC error:",
            error.code(),
            error.details(),
        )

        if error.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail="Delivery not found",
            )

        if error.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise HTTPException(
                status_code=400,
                detail=error.details(),
            )

        if error.code() == grpc.StatusCode.FAILED_PRECONDITION:
            raise HTTPException(
                status_code=409,
                detail=error.details(),
            )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Delivery service unavailable",
            )

        raise HTTPException(
            status_code=500,
            detail="Failed to update delivery status",
        )

    finally:
        channel.close()

    return {
        "delivery_id": response.delivery_id,
        "order_id": response.order_id,
        "status": response.status,
    }
