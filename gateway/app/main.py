import grpc

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import delivery_pb2
from . import delivery_pb2_grpc
from . import order_pb2
from . import order_pb2_grpc


app = FastAPI(
    title="FlowMesh API Gateway",
    version="1.0.0",
)


class CreateOrderRequest(BaseModel):
    user_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class UpdateDeliveryStatusRequest(BaseModel):
    status: str


@app.get("/health")
def health_check():
    return {
        "service": "api-gateway",
        "status": "healthy",
    }


@app.post("/orders")
def create_order(
    request: CreateOrderRequest,
):
    channel = grpc.insecure_channel(
        "localhost:50051"
    )

    stub = order_pb2_grpc.OrderServiceStub(
        channel
    )

    grpc_request = order_pb2.CreateOrderRequest(
        user_id=request.user_id,
        product_id=request.product_id,
        quantity=request.quantity,
    )

    try:
        response = stub.CreateOrder(
            grpc_request
        )

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

    return {
        "order_id": response.order_id,
        "status": response.status,
        "delivery": {
            "status": "PROCESSING",
        },
    }


@app.get("/orders/{order_id}")
def get_order(
    order_id: str,
):
    channel = grpc.insecure_channel(
        "localhost:50051"
    )

    stub = order_pb2_grpc.OrderServiceStub(
        channel
    )

    grpc_request = order_pb2.GetOrderRequest(
        order_id=order_id,
    )

    try:
        response = stub.GetOrder(
            grpc_request
        )

    except grpc.RpcError as error:
        print(
            "Order Service gRPC error:",
            error.code(),
            error.details(),
        )

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


@app.patch("/deliveries/{delivery_id}/status")
def update_delivery_status(
    delivery_id: str,
    request: UpdateDeliveryStatusRequest,
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

    channel = grpc.insecure_channel(
        "localhost:50053"
    )

    stub = delivery_pb2_grpc.DeliveryServiceStub(
        channel
    )

    grpc_request = (
        delivery_pb2.UpdateDeliveryStatusRequest(
            delivery_id=delivery_id,
            status=request.status,
        )
    )

    try:
        response = stub.UpdateDeliveryStatus(
            grpc_request
        )

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