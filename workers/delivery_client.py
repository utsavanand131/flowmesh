import grpc

from services.delivery_service.app import delivery_pb2
from services.delivery_service.app import delivery_pb2_grpc


DELIVERY_SERVICE_ADDRESS = "localhost:50053"


def create_delivery(order_id: str):
    channel = grpc.insecure_channel(
        DELIVERY_SERVICE_ADDRESS
    )

    stub = delivery_pb2_grpc.DeliveryServiceStub(
        channel
    )

    request = delivery_pb2.CreateDeliveryRequest(
        order_id=order_id,
    )

    try:
        response = stub.CreateDelivery(
            request
        )

        return {
            "delivery_id": response.delivery_id,
            "status": response.status,
        }

    finally:
        channel.close()