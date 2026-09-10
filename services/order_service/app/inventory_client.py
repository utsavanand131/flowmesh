import grpc

import inventory_pb2
import inventory_pb2_grpc


def check_stock(
    product_id: str,
    quantity: int,
):
    channel = grpc.insecure_channel("localhost:50052")

    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    request = inventory_pb2.CheckStockRequest(
        product_id=product_id,
        quantity=quantity,
    )

    response = stub.CheckStock(request)

    channel.close()

    return {
        "product_id": response.product_id,
        "available_quantity": response.available_quantity,
        "available": response.available,
    }