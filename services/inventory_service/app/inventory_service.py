class InventoryManager:
    def __init__(self):
        self.inventory = {
            "product_456": 10,
            "product_789": 5,
            "product_999": 0,
        }

    def check_stock(self, product_id: str, quantity: int):
        available_quantity = self.inventory.get(product_id, 0)

        return {
            "product_id": product_id,
            "available_quantity": available_quantity,
            "available": available_quantity >= quantity,
        }