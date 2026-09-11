from concurrent import futures

import grpc
from sqlalchemy.exc import SQLAlchemyError

import delivery_pb2
import delivery_pb2_grpc

from database import SessionLocal
from delivery_service import DeliveryManager


delivery_manager = DeliveryManager()


class DeliveryService(
    delivery_pb2_grpc.DeliveryServiceServicer
):
    def CreateDelivery(self, request, context):
        db = SessionLocal()

        try:
            delivery = delivery_manager.create_delivery(
                db=db,
                order_id=request.order_id,
            )

            if delivery is None:
                context.set_code(
                    grpc.StatusCode.ALREADY_EXISTS
                )
                context.set_details(
                    "Delivery already exists for this order"
                )

                return delivery_pb2.CreateDeliveryResponse()

            return delivery_pb2.CreateDeliveryResponse(
                delivery_id=delivery.delivery_id,
                order_id=delivery.order_id,
                status=delivery.status,
            )

        except SQLAlchemyError:
            db.rollback()

            context.set_code(
                grpc.StatusCode.INTERNAL
            )
            context.set_details(
                "Failed to create delivery"
            )

            return delivery_pb2.CreateDeliveryResponse()

        finally:
            db.close()

    def GetDelivery(self, request, context):
        db = SessionLocal()

        try:
            delivery = delivery_manager.get_delivery(
                db=db,
                delivery_id=request.delivery_id,
            )

            if delivery is None:
                context.set_code(
                    grpc.StatusCode.NOT_FOUND
                )
                context.set_details(
                    "Delivery not found"
                )

                return delivery_pb2.GetDeliveryResponse()

            return delivery_pb2.GetDeliveryResponse(
                delivery_id=delivery.delivery_id,
                order_id=delivery.order_id,
                status=delivery.status,
            )

        except SQLAlchemyError:
            context.set_code(
                grpc.StatusCode.INTERNAL
            )
            context.set_details(
                "Failed to get delivery"
            )

            return delivery_pb2.GetDeliveryResponse()

        finally:
            db.close()


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    delivery_pb2_grpc.add_DeliveryServiceServicer_to_server(
        DeliveryService(),
        server,
    )

    server.add_insecure_port("[::]:50053")

    server.start()

    print(
        "FlowMesh Delivery Service gRPC server "
        "running on port 50053"
    )

    server.wait_for_termination()


if __name__ == "__main__":
    serve()