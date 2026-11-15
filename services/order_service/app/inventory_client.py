import grpc

import inventory_pb2
import inventory_pb2_grpc

INVENTORY_SERVICE_ADDRESS = "localhost:50052"
GRPC_TIMEOUT = 5.0


def check_stock(product_id: str, quantity: int):
    channel = grpc.insecure_channel(INVENTORY_SERVICE_ADDRESS)
    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    request = inventory_pb2.CheckStockRequest(
        product_id=product_id,
        quantity=quantity,
    )

    try:
        response = stub.CheckStock(
            request,
            timeout=GRPC_TIMEOUT,
        )

        return {
            "product_id": response.product_id,
            "available_quantity": response.available_quantity,
            "available": response.available,
        }
    finally:
        channel.close()


def reserve_stock(
    product_id: str,
    quantity: int,
    reservation_id: str,
):
    channel = grpc.insecure_channel(INVENTORY_SERVICE_ADDRESS)
    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    request = inventory_pb2.ReserveStockRequest(
        product_id=product_id,
        quantity=quantity,
        reservation_id=reservation_id,
    )

    try:
        response = stub.ReserveStock(
            request,
            timeout=GRPC_TIMEOUT,
        )

        return {
            "product_id": response.product_id,
            "remaining_quantity": response.remaining_quantity,
            "reserved": response.reserved,
        }
    finally:
        channel.close()


def release_stock(
    product_id: str,
    quantity: int,
    reservation_id: str,
):
    channel = grpc.insecure_channel(INVENTORY_SERVICE_ADDRESS)
    stub = inventory_pb2_grpc.InventoryServiceStub(channel)

    request = inventory_pb2.ReleaseStockRequest(
        product_id=product_id,
        quantity=quantity,
        reservation_id=reservation_id,
    )

    try:
        response = stub.ReleaseStock(
            request,
            timeout=GRPC_TIMEOUT,
        )

        return {
            "product_id": response.product_id,
            "remaining_quantity": response.remaining_quantity,
            "released": response.released,
        }
    finally:
        channel.close()
