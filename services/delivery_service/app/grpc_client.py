import grpc

import delivery_pb2
import delivery_pb2_grpc


def create_delivery(
    order_id: str,
):
    channel = grpc.insecure_channel(
        "localhost:50053"
    )

    stub = delivery_pb2_grpc.DeliveryServiceStub(
        channel
    )

    request = delivery_pb2.CreateDeliveryRequest(
        order_id=order_id,
    )

    try:
        response = stub.CreateDelivery(request)

        return {
            "delivery_id": response.delivery_id,
            "order_id": response.order_id,
            "status": response.status,
        }

    finally:
        channel.close()


def get_delivery(
    delivery_id: str,
):
    channel = grpc.insecure_channel(
        "localhost:50053"
    )

    stub = delivery_pb2_grpc.DeliveryServiceStub(
        channel
    )

    request = delivery_pb2.GetDeliveryRequest(
        delivery_id=delivery_id,
    )

    try:
        response = stub.GetDelivery(request)

        return {
            "delivery_id": response.delivery_id,
            "order_id": response.order_id,
            "status": response.status,
        }

    finally:
        channel.close()