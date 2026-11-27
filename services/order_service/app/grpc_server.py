from concurrent import futures

import grpc
from sqlalchemy.exc import SQLAlchemyError

from . import order_pb2
from . import order_pb2_grpc
from services.order_service.app.database import SessionLocal
from services.order_service.app.order_service import OrderManager

order_manager = OrderManager()


class OrderService(order_pb2_grpc.OrderServiceServicer):
    def CreateOrder(self, request, context):
        db = SessionLocal()

        try:
            result = order_manager.create_order(
                db=db,
                user_id=request.user_id,
                product_id=request.product_id,
                quantity=request.quantity,
            )

            if result is None:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("Insufficient inventory")
                return order_pb2.CreateOrderResponse()

            order = result["order"]

            response = order_pb2.CreateOrderResponse(
                order_id=order.order_id,
                status=order.status,
            )

            delivery = order_manager.get_order(
                db=db,
                order_id=order.order_id,
            )["delivery"]

            if delivery is not None:
                response.delivery_id = delivery["delivery_id"]
                response.delivery_status = delivery["status"]

            return response

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to create order")
            return order_pb2.CreateOrderResponse()

        except Exception as error:
            print("Order creation error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to create order")
            return order_pb2.CreateOrderResponse()

        finally:
            db.close()

    def GetOrder(self, request, context):
        db = SessionLocal()

        try:
            result = order_manager.get_order(
                db=db,
                order_id=request.order_id,
            )

            if result is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Order not found")
                return order_pb2.GetOrderResponse()

            order = result["order"]
            delivery = result["delivery"]

            response = order_pb2.GetOrderResponse(
                order_id=order.order_id,
                user_id=order.user_id,
                product_id=order.product_id,
                quantity=order.quantity,
                status=order.status,
            )

            if delivery is not None:
                response.delivery_id = delivery["delivery_id"]
                response.delivery_status = delivery["status"]

            return response

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve order")
            return order_pb2.GetOrderResponse()

        except grpc.RpcError:
            raise

        except Exception as error:
            print("Get order error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve order")
            return order_pb2.GetOrderResponse()

        finally:
            db.close()

    def ListOrders(self, request, context):
        db = SessionLocal()

        try:
            result = order_manager.list_orders(
                db=db,
                user_id=request.user_id or None,
                page=request.page or 1,
                page_size=request.page_size or 20,
            )

            response = order_pb2.ListOrdersResponse(
                total=result["total"],
                page=result["page"],
                page_size=result["page_size"],
            )

            for item in result["orders"]:
                order = item["order"]
                delivery = item["delivery"]

                order_item = response.orders.add(
                    order_id=order.order_id,
                    user_id=order.user_id,
                    product_id=order.product_id,
                    quantity=order.quantity,
                    status=order.status,
                )

                if delivery is not None:
                    order_item.delivery_id = delivery["delivery_id"]
                    order_item.delivery_status = delivery["status"]

            return response

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve orders")
            return order_pb2.ListOrdersResponse()

        except Exception as error:
            print("List orders error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve orders")
            return order_pb2.ListOrdersResponse()

        finally:
            db.close()

    def GetOrderStatistics(self, request, context):
        db = SessionLocal()

        try:
            result = order_manager.get_order_statistics(
                db=db,
            )

            return order_pb2.GetOrderStatisticsResponse(
                total_orders=result["total_orders"],
                pending_orders=result["pending_orders"],
                delivered_orders=result["delivered_orders"],
                confirmed_orders=result["confirmed_orders"],
                processing_orders=result["processing_orders"],
                completion_rate=result["completion_rate"],
            )

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve order statistics")
            return order_pb2.GetOrderStatisticsResponse()

        except Exception as error:
            print("Order statistics error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve order statistics")
            return order_pb2.GetOrderStatisticsResponse()

        finally:
            db.close()

    def GetPeriodOrderStatistics(self, request, context):
        db = SessionLocal()

        try:
            days = request.days or 7

            if days < 1:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Days must be at least 1")
                return order_pb2.GetPeriodOrderStatisticsResponse()

            result = order_manager.get_period_order_statistics(
                db=db,
                days=days,
            )

            return order_pb2.GetPeriodOrderStatisticsResponse(
                total_orders=result["total_orders"],
                pending_orders=result["pending_orders"],
                delivered_orders=result["delivered_orders"],
                confirmed_orders=result["confirmed_orders"],
                processing_orders=result["processing_orders"],
                completion_rate=result["completion_rate"],
            )

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve period order statistics")
            return order_pb2.GetPeriodOrderStatisticsResponse()

        except Exception as error:
            print("Period order statistics error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve period order statistics")
            return order_pb2.GetPeriodOrderStatisticsResponse()

        finally:
            db.close()

    def GetDailyOrderTrends(self, request, context):
        db = SessionLocal()

        try:
            days = request.days or 7

            if days < 1:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Days must be at least 1")
                return order_pb2.GetDailyOrderTrendsResponse()

            trends = order_manager.get_daily_order_trends(
                db=db,
                days=days,
            )

            response = order_pb2.GetDailyOrderTrendsResponse()

            for trend in trends:
                response.trends.add(
                    date=trend["date"],
                    order_count=trend["order_count"],
                )

            return response

        except SQLAlchemyError:
            db.rollback()
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve daily order trends")
            return order_pb2.GetDailyOrderTrendsResponse()

        except Exception as error:
            print("Daily order trends error:", error)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to retrieve daily order trends")
            return order_pb2.GetDailyOrderTrendsResponse()

        finally:
            db.close()


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

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
