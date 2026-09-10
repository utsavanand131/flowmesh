from concurrent import futures

import grpc
from sqlalchemy.exc import SQLAlchemyError

import inventory_pb2
import inventory_pb2_grpc

from database import SessionLocal
from inventory_service import InventoryManager


inventory_manager = InventoryManager()


class InventoryService(inventory_pb2_grpc.InventoryServiceServicer):
    def CheckStock(self, request, context):
        db = SessionLocal()

        try:
            result = inventory_manager.check_stock(
                db=db,
                product_id=request.product_id,
                quantity=request.quantity,
            )

            return inventory_pb2.CheckStockResponse(
                product_id=result["product_id"],
                available_quantity=result["available_quantity"],
                available=result["available"],
            )

        except SQLAlchemyError:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to check inventory")

            return inventory_pb2.CheckStockResponse()

        finally:
            db.close()


def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10)
    )

    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(
        InventoryService(),
        server,
    )

    server.add_insecure_port("[::]:50052")

    server.start()

    print(
        "FlowMesh Inventory Service gRPC server "
        "running on port 50052"
    )

    server.wait_for_termination()


if __name__ == "__main__":
    serve()