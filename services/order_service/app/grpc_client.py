import grpc

import order_pb2
import order_pb2_grpc


def run():
    channel = grpc.insecure_channel("localhost:50051")

    stub = order_pb2_grpc.OrderServiceStub(channel)

    request = order_pb2.CreateOrderRequest(
        user_id="user_123",
        product_id="product_456",
        quantity=2,
    )

    response = stub.CreateOrder(request)

    print("gRPC Response:")
    print(f"Order ID: {response.order_id}")
    print(f"Status: {response.status}")


if __name__ == "__main__":
    run()