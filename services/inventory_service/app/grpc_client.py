import grpc

import inventory_pb2
import inventory_pb2_grpc


def check_stock(stub, product_id, quantity):
    request = inventory_pb2.CheckStockRequest(
        product_id=product_id,
        quantity=quantity,
    )

    response = stub.CheckStock(request)

    print("Check Stock:")
    print(f"Product ID: {response.product_id}")
    print(f"Available Quantity: {response.available_quantity}")
    print(f"Available: {response.available}")
    print()


def reserve_stock(stub, product_id, quantity):
    request = inventory_pb2.ReserveStockRequest(
        product_id=product_id,
        quantity=quantity,
    )

    try:
        response = stub.ReserveStock(request)

        print("Reserve Stock:")
        print(f"Product ID: {response.product_id}")
        print(f"Remaining Quantity: {response.remaining_quantity}")
        print(f"Reserved: {response.reserved}")

    except grpc.RpcError as error:
        print("Reserve Stock Failed:")
        print(f"Code: {error.code()}")
        print(f"Details: {error.details()}")


def run():
    channel = grpc.insecure_channel("localhost:50052")

    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    check_stock(
        stub,
        "product_456",
        3,
    )

    reserve_stock(
        stub,
        "product_456",
        3,
    )

    channel.close()


if __name__ == "__main__":
    run()