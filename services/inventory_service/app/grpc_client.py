import grpc

import inventory_pb2
import inventory_pb2_grpc


def run():
    channel = grpc.insecure_channel("localhost:50052")

    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    request = inventory_pb2.CheckStockRequest(
        product_id="product_456",
        quantity=15,
    )

    response = stub.CheckStock(request)

    print("gRPC Inventory Response:")
    print(f"Product ID: {response.product_id}")
    print(f"Available Quantity: {response.available_quantity}")
    print(f"Available: {response.available}")


if __name__ == "__main__":
    run()