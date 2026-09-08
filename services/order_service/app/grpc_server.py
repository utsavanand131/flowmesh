from concurrent import futures

import grpc

import order_pb2
import order_pb2_grpc


class OrderService(order_pb2_grpc.OrderServiceServicer):
    def CreateOrder(self, request, context):
        order_id = "order_123"

        return order_pb2.CreateOrderResponse(
            order_id=order_id,
            status="PENDING",
        )


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
    