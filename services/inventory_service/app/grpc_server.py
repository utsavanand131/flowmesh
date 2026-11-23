from concurrent import futures

import grpc
from sqlalchemy.exc import SQLAlchemyError

import inventory_pb2
import inventory_pb2_grpc

from database import SessionLocal
from inventory_service import InventoryManager

inventory_manager = InventoryManager()


class InventoryService(inventory_pb2_grpc.InventoryServiceServicer):
    def ListInventory(self, request, context):
        db = SessionLocal()

        try:
            result = inventory_manager.list_inventory(db=db)

            return inventory_pb2.ListInventoryResponse(
                items=[
                    inventory_pb2.InventoryItem(
                        product_id=item["product_id"],
                        quantity=item["quantity"],
                    )
                    for item in result["items"]
                ],
                total_items=result["total_items"],
                total_quantity=result["total_quantity"],
            )

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve inventory")
            return inventory_pb2.ListInventoryResponse()

        except Exception as error:
            db.rollback()
            print("List inventory error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve inventory")
            return inventory_pb2.ListInventoryResponse()

        finally:
            db.close()

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

        except ValueError as error:
            db.rollback()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(error))
            return inventory_pb2.CheckStockResponse()

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to check inventory")
            return inventory_pb2.CheckStockResponse()

        except Exception as error:
            db.rollback()
            print("Check stock error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to check inventory")
            return inventory_pb2.CheckStockResponse()

        finally:
            db.close()

    def ReserveStock(self, request, context):
        db = SessionLocal()

        try:
            result = inventory_manager.reserve_stock(
                db=db,
                product_id=request.product_id,
                quantity=request.quantity,
                reservation_id=request.reservation_id,
            )

            if not result["reserved"]:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("Insufficient inventory")

                return inventory_pb2.ReserveStockResponse(
                    product_id=result["product_id"],
                    remaining_quantity=result["remaining_quantity"],
                    reserved=False,
                )

            return inventory_pb2.ReserveStockResponse(
                product_id=result["product_id"],
                remaining_quantity=result["remaining_quantity"],
                reserved=True,
            )

        except ValueError as error:
            db.rollback()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(error))
            return inventory_pb2.ReserveStockResponse()

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to reserve inventory")
            return inventory_pb2.ReserveStockResponse()

        except Exception as error:
            db.rollback()
            print("Reserve stock error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to reserve inventory")
            return inventory_pb2.ReserveStockResponse()

        finally:
            db.close()

    def ReleaseStock(self, request, context):
        db = SessionLocal()

        try:
            result = inventory_manager.release_stock(
                db=db,
                product_id=request.product_id,
                quantity=request.quantity,
                reservation_id=request.reservation_id,
            )

            if not result["released"]:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(
                    "Reservation not found or inventory product missing"
                )

                return inventory_pb2.ReleaseStockResponse(
                    product_id=result["product_id"],
                    remaining_quantity=result["remaining_quantity"],
                    released=False,
                )

            return inventory_pb2.ReleaseStockResponse(
                product_id=result["product_id"],
                remaining_quantity=result["remaining_quantity"],
                released=True,
            )

        except ValueError as error:
            db.rollback()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(error))
            return inventory_pb2.ReleaseStockResponse()

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to release inventory")
            return inventory_pb2.ReleaseStockResponse()

        except Exception as error:
            db.rollback()
            print("Release stock error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to release inventory")
            return inventory_pb2.ReleaseStockResponse()

        finally:
            db.close()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    inventory_pb2_grpc.add_InventoryServiceServicer_to_server(
        InventoryService(),
        server,
    )

    server.add_insecure_port("[::]:50052")
    server.start()

    print("FlowMesh Inventory Service gRPC server " "running on port 50052")

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
