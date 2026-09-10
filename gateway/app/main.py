import grpc
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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


@app.get("/health")
def health_check():
    return {
        "service": "api-gateway",
        "status": "healthy",
    }


@app.post("/orders")
def create_order(request: CreateOrderRequest):
    channel = grpc.insecure_channel("localhost:50051")

    stub = order_pb2_grpc.OrderServiceStub(channel)

    grpc_request = order_pb2.CreateOrderRequest(
        user_id=request.user_id,
        product_id=request.product_id,
        quantity=request.quantity,
    )

    try:
        response = stub.CreateOrder(grpc_request)

    except grpc.RpcError as error:
        if error.code() == grpc.StatusCode.FAILED_PRECONDITION:
            raise HTTPException(
                status_code=409,
                detail="Insufficient inventory",
            )

        if error.code() == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Inventory service unavailable",
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
    }


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    channel = grpc.insecure_channel("localhost:50051")

    stub = order_pb2_grpc.OrderServiceStub(channel)

    grpc_request = order_pb2.GetOrderRequest(
        order_id=order_id,
    )

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

    return {
        "order_id": response.order_id,
        "user_id": response.user_id,
        "product_id": response.product_id,
        "quantity": response.quantity,
        "status": response.status,
    }