from concurrent import futures

import grpc

import order_pb2
import order_pb2_grpc

from database import SessionLocal
from order_service import OrderManager


order_manager = OrderManager()


class OrderService(order_pb2_grpc.OrderServiceServicer):
    def CreateOrder(self, request, context):
        db = SessionLocal()

        try:
            order = order_manager.create_order(
                db=db,
                user_id=request.user_id,
                product_id=request.product_id,
                quantity=request.quantity,
            )

            return order_pb2.CreateOrderResponse(
                order_id=order.order_id,
                status=order.status,
            )

        finally:
            db.close()

    def GetOrder(self, request, context):
        db = SessionLocal()

        try:
            order = order_manager.get_order(
                db=db,
                order_id=request.order_id,
            )

            if order is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Order not found")

                return order_pb2.GetOrderResponse()

            return order_pb2.GetOrderResponse(
                order_id=order.order_id,
                user_id=order.user_id,
                product_id=order.product_id,
                quantity=order.quantity,
                status=order.status,
            )

        finally:
            db.close()


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    order_pb2_grpc.add_OrderServiceServicer_to_server(
        OrderService(),
        server,
    )

    server.add_insecure_port("[::]:50051")

    server.start()

    print("FlowMesh Order Service gRPC server running on port 50051")

    server.wait_for_termination()


if __name__ == "__main__":
    serve()