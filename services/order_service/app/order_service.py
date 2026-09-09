import uuid


class OrderManager:
    def __init__(self):
        self.orders = {}

    def create_order(
        self,
        user_id: str,
        product_id: str,
        quantity: int,
    ):
        order_id = str(uuid.uuid4())

        order = {
            "order_id": order_id,
            "user_id": user_id,
            "product_id": product_id,
            "quantity": quantity,
            "status": "PENDING",
        }

        self.orders[order_id] = order

        return order

    def get_order(self, order_id: str):
        return self.orders.get(order_id)