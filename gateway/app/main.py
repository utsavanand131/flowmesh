import grpc
from fastapi import FastAPI
from pydantic import BaseModel

from . import order_pb2
from . import order_pb2_grpc


app = FastAPI(
    title="FlowMesh API Gateway",
    version="1.0.0",
)


class CreateOrderRequest(BaseModel):
    user_id: str
    product_id: str
    quantity: int

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

    response = stub.CreateOrder(grpc_request)

    return {
        "order_id": response.order_id,
        "status": response.status,
    }