const API_BASE_URL = "http://localhost:8000";

export interface Order {
  order_id: string;
  user_id: string;
  product_id: string;
  quantity: number;
  status: string;
  delivery: {
    delivery_id: string;
    status: string;
  } | null;
}

export interface CreateOrderInput {
  user_id: string;
  product_id: string;
  quantity: number;
}

export interface UpdateDeliveryStatusInput {
  status: "PICKED_UP" | "IN_TRANSIT" | "DELIVERED";
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: "Request failed",
    }));

    throw new Error(error.detail || "Request failed");
  }

  return response.json();
}

export async function createOrder(input: CreateOrderInput): Promise<{
  order_id: string;
  status: string;
  delivery: {
    status: string;
  };
}> {
  const response = await fetch(`${API_BASE_URL}/orders`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });

  return handleResponse(response);
}

export async function getOrder(orderId: string): Promise<Order> {
  const response = await fetch(`${API_BASE_URL}/orders/${orderId}`);

  return handleResponse(response);
}

export async function updateDeliveryStatus(
  deliveryId: string,
  input: UpdateDeliveryStatusInput,
) {
  const response = await fetch(
    `${API_BASE_URL}/deliveries/${deliveryId}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
    },
  );

  return handleResponse(response);
}
