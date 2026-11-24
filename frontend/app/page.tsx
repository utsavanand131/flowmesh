"use client";

import { useEffect, useState, type FormEvent } from "react";
import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface OrderOverviewResponse {
  total_orders: number;
  pending_orders: number;
  in_delivery: number;
  delivered_orders: number;
}

interface RecentOrder {
  id: string;
  product: string;
  status: string;
  delivery: string;
}

interface CreateOrderResponse {
  order_id: string;
  status: string;
  delivery_id?: string;
  delivery_status?: string;
}

interface InventoryResponse {
  items: {
    product_id: string;
    quantity: number;
  }[];
  total_items: number;
  total_quantity: number;
  low_stock_items: number;
  out_of_stock_items: number;
  low_stock_threshold: number;
}

const initialOrders: RecentOrder[] = [
  {
    id: "ord_8f31a2",
    product: "product_789",
    status: "CONFIRMED",
    delivery: "ASSIGNED",
  },
  {
    id: "ord_7c92bd",
    product: "product_456",
    status: "CONFIRMED",
    delivery: "IN_TRANSIT",
  },
  {
    id: "ord_51de90",
    product: "product_123",
    status: "DELIVERED",
    delivery: "DELIVERED",
  },
  {
    id: "ord_39ab12",
    product: "product_999",
    status: "PENDING",
    delivery: "PROCESSING",
  },
];

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    DELIVERED: "bg-success/10 text-success",
    IN_TRANSIT: "bg-accent/10 text-accent",
    CONFIRMED: "bg-warning/10 text-warning",
    ASSIGNED: "bg-surface-hover text-muted-foreground",
    PROCESSING: "bg-surface-hover text-muted-foreground",
    PENDING: "bg-surface-hover text-muted-foreground",
  };

  const dotStyles: Record<string, string> = {
    DELIVERED: "bg-success",
    IN_TRANSIT: "bg-accent",
    CONFIRMED: "bg-warning",
    ASSIGNED: "bg-muted",
    PROCESSING: "bg-muted",
    PENDING: "bg-muted",
  };

  return (
    <span
      className={`inline-flex items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium ${
        styles[status] ?? "bg-surface-hover text-muted"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          dotStyles[status] ?? "bg-muted"
        }`}
      />
      {status.replaceAll("_", " ")}
    </span>
  );
}

export default function Home() {
  const { user } = useAuth();

  const isAdmin = user?.role === "ADMIN";

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Create Order state
  const [createOrderOpen, setCreateOrderOpen] = useState(false);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [orderError, setOrderError] = useState("");
  const [orderSuccess, setOrderSuccess] = useState("");

  // Recent Orders state
  const [recentOrders, setRecentOrders] =
    useState<RecentOrder[]>(initialOrders);

  // Inventory state
  const [inventory, setInventory] = useState<InventoryResponse | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(true);
  const [inventoryError, setInventoryError] = useState("");

  // Live order statistics state
  const [orderOverview, setOrderOverview] =
    useState<OrderOverviewResponse | null>(null);
  const [orderOverviewLoading, setOrderOverviewLoading] = useState(true);
  const [orderOverviewError, setOrderOverviewError] = useState("");

  // Fetch live order statistics for administrators only.
  useEffect(() => {
    if (!isAdmin) {
      setOrderOverviewLoading(false);
      setOrderOverview(null);
      return;
    }

    const controller = new AbortController();

    async function fetchOrderOverview() {
      if (!API_URL) {
        setOrderOverviewError(
          "API URL is not configured. Check your frontend environment variables.",
        );
        setOrderOverviewLoading(false);
        return;
      }

      setOrderOverviewLoading(true);
      setOrderOverviewError("");

      try {
        const response = await fetch(`${API_URL}/admin/orders/overview`, {
          method: "GET",
          credentials: "include",
          headers: {
            Accept: "application/json",
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          let message = "Unable to load order statistics.";

          try {
            const data = await response.json();
            message = data.detail || data.message || message;
          } catch {
            // Keep the default error message.
          }

          throw new Error(message);
        }

        const data: OrderOverviewResponse = await response.json();
        setOrderOverview(data);
      } catch (err) {
        if (controller.signal.aborted) return;

        setOrderOverviewError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading order statistics.",
        );
      } finally {
        if (!controller.signal.aborted) {
          setOrderOverviewLoading(false);
        }
      }
    }

    fetchOrderOverview();

    return () => {
      controller.abort();
    };
  }, [isAdmin]);

  // Fetch inventory statistics for administrators only.
  useEffect(() => {
    if (!isAdmin) {
      setInventoryLoading(false);
      setInventory(null);
      return;
    }

    const controller = new AbortController();

    async function fetchInventory() {
      if (!API_URL) {
        setInventoryError(
          "API URL is not configured. Check your frontend environment variables.",
        );
        setInventoryLoading(false);
        return;
      }

      setInventoryLoading(true);
      setInventoryError("");

      try {
        const response = await fetch(`${API_URL}/inventory`, {
          method: "GET",
          credentials: "include",
          headers: {
            Accept: "application/json",
          },
          signal: controller.signal,
        });

        if (!response.ok) {
          let message = "Unable to load inventory statistics.";

          try {
            const data = await response.json();
            message = data.detail || data.message || message;
          } catch {
            // Keep the default error message.
          }

          throw new Error(message);
        }

        const data: InventoryResponse = await response.json();
        setInventory(data);
      } catch (err) {
        if (controller.signal.aborted) return;

        setInventoryError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading inventory.",
        );
      } finally {
        if (!controller.signal.aborted) {
          setInventoryLoading(false);
        }
      }
    }

    fetchInventory();

    return () => {
      controller.abort();
    };
  }, [isAdmin]);

  const handleCreateOrder = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setOrderError("");
    setOrderSuccess("");

    const trimmedProductId = productId.trim();
    const parsedQuantity = Number(quantity);

    if (!trimmedProductId) {
      setOrderError("Please enter a product ID.");
      return;
    }

    if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
      setOrderError("Quantity must be a positive whole number.");
      return;
    }

    if (!API_URL) {
      setOrderError(
        "API URL is not configured. Check your frontend environment variables.",
      );
      return;
    }

    setSubmitting(true);

    try {
      const response = await fetch(`${API_URL}/orders`, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          product_id: trimmedProductId,
          quantity: parsedQuantity,
        }),
      });

      if (!response.ok) {
        let message = "Unable to create order.";

        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {
          // Keep the default error message.
        }

        throw new Error(message);
      }

      const data: CreateOrderResponse = await response.json();

      if (!data.order_id) {
        throw new Error("The server response did not contain an order ID.");
      }

      const newOrder: RecentOrder = {
        id: data.order_id,
        product: trimmedProductId,
        status: data.status,
        delivery: data.delivery_status ?? "PROCESSING",
      };

      setRecentOrders((current) => [newOrder, ...current]);

      setOrderSuccess(`Order created successfully! Order ID: ${data.order_id}`);

      setProductId("");
      setQuantity("1");
      setCreateOrderOpen(false);
    } catch (err) {
      setOrderError(
        err instanceof Error
          ? err.message
          : "Something went wrong while creating the order.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const closeCreateOrder = () => {
    if (submitting) return;

    setCreateOrderOpen(false);
    setOrderError("");
  };

  const retryInventoryFetch = () => {
    // Reload the page to retry the inventory request.
    window.location.reload();
  };

  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-background text-foreground">
        <div className="flex min-h-screen">
          {/* Desktop Sidebar */}
          <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
            <AppSidebar activeItem="Dashboard" />
          </aside>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <div className="fixed inset-0 z-50 lg:hidden">
              <button
                aria-label="Close navigation menu"
                className="absolute inset-0 bg-black/60"
                onClick={() => setMobileMenuOpen(false)}
              />

              <aside className="relative flex h-full w-[85%] max-w-72 flex-col border-r border-border bg-surface">
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close menu"
                  className="absolute right-4 top-5 z-10 flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-surface-hover"
                >
                  ×
                </button>

                <AppSidebar
                  activeItem="Dashboard"
                  onNavigate={() => setMobileMenuOpen(false)}
                />
              </aside>
            </div>
          )}

          {/* Main Content */}
          <section className="min-w-0 flex-1">
            {/* Header */}
            <header className="sticky top-0 z-20 flex items-center justify-between border-b border-border bg-background/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setMobileMenuOpen(true)}
                  aria-label="Open navigation menu"
                  className="flex h-9 w-9 items-center justify-center rounded-md border border-border text-lg text-muted-foreground hover:bg-surface-hover lg:hidden"
                >
                  ☰
                </button>

                <div>
                  <p className="text-xs text-muted">Operations</p>
                  <h1 className="mt-0.5 text-lg font-semibold tracking-tight sm:text-xl">
                    Dashboard
                  </h1>
                </div>
              </div>
            </header>

            {/* Dashboard Content */}
            <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              {/* Welcome Section */}
              <section className="flex flex-col justify-between gap-5 border-b border-border pb-7 sm:flex-row sm:items-center">
                <div>
                  <p className="text-sm font-medium text-accent">
                    FlowMesh / Overview
                  </p>

                  <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                    Order & Delivery Operations
                  </h2>

                  <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                    Monitor orders, inventory reservations, delivery workflows,
                    and distributed service events from one operations console.
                  </p>
                </div>

                <button
                  onClick={() => {
                    setOrderError("");
                    setOrderSuccess("");
                    setCreateOrderOpen(true);
                  }}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-[#101614] transition hover:bg-accent-hover"
                >
                  <span className="text-lg leading-none">+</span>
                  Create order
                </button>
              </section>

              {/* Order Success */}
              {orderSuccess && (
                <div
                  role="status"
                  aria-live="polite"
                  className="rounded-lg border border-success/20 bg-success/10 p-4"
                >
                  <p className="text-sm font-medium text-success">
                    {orderSuccess}
                  </p>
                </div>
              )}
              {/* System Metrics - Admin Only */}
              {isAdmin && (
                <section>
                  <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-sm font-semibold">System metrics</h2>
                    <span className="text-xs text-muted">Live statistics</span>
                  </div>

                  {orderOverviewLoading && (
                    <div
                      role="status"
                      className="rounded-lg border border-border bg-surface p-6"
                    >
                      <p className="text-sm text-muted-foreground">
                        Loading order statistics...
                      </p>
                    </div>
                  )}

                  {!orderOverviewLoading && orderOverviewError && (
                    <div
                      role="alert"
                      className="rounded-lg border border-danger/20 bg-danger/10 p-4"
                    >
                      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                        <p className="text-sm text-danger">
                          {orderOverviewError}
                        </p>

                        <button
                          onClick={() => window.location.reload()}
                          className="self-start rounded-md border border-danger/30 px-3 py-2 text-xs font-medium text-danger transition hover:bg-danger/10 sm:self-auto"
                        >
                          Retry
                        </button>
                      </div>
                    </div>
                  )}

                  {!orderOverviewLoading &&
                    !orderOverviewError &&
                    orderOverview && (
                      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                        {[
                          {
                            label: "Total orders",
                            value: orderOverview.total_orders,
                            detail: "All orders",
                            icon: "▤",
                          },
                          {
                            label: "Pending",
                            value: orderOverview.pending_orders,
                            detail: "Awaiting processing",
                            icon: "◷",
                          },
                          {
                            label: "In delivery",
                            value: orderOverview.in_delivery,
                            detail: "Active deliveries",
                            icon: "↗",
                          },
                          {
                            label: "Delivered",
                            value: orderOverview.delivered_orders,
                            detail: "Completed orders",
                            icon: "✓",
                          },
                        ].map((stat) => (
                          <div
                            key={stat.label}
                            className="rounded-lg border border-border bg-surface p-4 sm:p-5"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <p className="text-xs font-medium text-muted-foreground">
                                {stat.label}
                              </p>

                              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-hover text-base text-accent">
                                {stat.icon}
                              </span>
                            </div>

                            <p className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                              {stat.value}
                            </p>

                            <p className="mt-1.5 text-xs text-muted">
                              {stat.detail}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                </section>
              )}

              {/* Inventory Statistics - Admin Only */}
              {isAdmin && (
                <section>
                  <div className="mb-4 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                    <div>
                      <h2 className="text-sm font-semibold">
                        Inventory statistics
                      </h2>

                      <p className="mt-1 text-xs text-muted">
                        Live stock levels across your inventory.
                      </p>
                    </div>

                    {inventory && (
                      <span className="text-xs text-muted">
                        Low-stock threshold: {inventory.low_stock_threshold}{" "}
                        units
                      </span>
                    )}
                  </div>

                  {inventoryLoading && (
                    <div
                      role="status"
                      className="rounded-lg border border-border bg-surface p-6"
                    >
                      <p className="text-sm text-muted-foreground">
                        Loading inventory statistics...
                      </p>
                    </div>
                  )}

                  {!inventoryLoading && inventoryError && (
                    <div
                      role="alert"
                      className="rounded-lg border border-danger/20 bg-danger/10 p-4"
                    >
                      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                        <p className="text-sm text-danger">{inventoryError}</p>

                        <button
                          onClick={retryInventoryFetch}
                          className="self-start rounded-md border border-danger/30 px-3 py-2 text-xs font-medium text-danger transition hover:bg-danger/10 sm:self-auto"
                        >
                          Retry
                        </button>
                      </div>
                    </div>
                  )}

                  {!inventoryLoading && !inventoryError && inventory && (
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                      <div className="rounded-lg border border-border bg-surface p-4 sm:p-5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-medium text-muted-foreground">
                            Total products
                          </p>

                          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-hover text-base text-accent">
                            ▦
                          </span>
                        </div>

                        <p className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                          {inventory.total_items}
                        </p>

                        <p className="mt-1.5 text-xs text-muted">
                          Products tracked
                        </p>
                      </div>

                      <div className="rounded-lg border border-border bg-surface p-4 sm:p-5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-medium text-muted-foreground">
                            Available stock
                          </p>

                          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-hover text-base text-success">
                            ✓
                          </span>
                        </div>

                        <p className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                          {inventory.total_quantity}
                        </p>

                        <p className="mt-1.5 text-xs text-muted">
                          Total available units
                        </p>
                      </div>

                      <div className="rounded-lg border border-border bg-surface p-4 sm:p-5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-medium text-muted-foreground">
                            Low stock
                          </p>

                          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-warning/10 text-base text-warning">
                            !
                          </span>
                        </div>

                        <p className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                          {inventory.low_stock_items}
                        </p>

                        <p className="mt-1.5 text-xs text-muted">
                          Below or at threshold
                        </p>
                      </div>

                      <div className="rounded-lg border border-border bg-surface p-4 sm:p-5">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-medium text-muted-foreground">
                            Out of stock
                          </p>

                          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-danger/10 text-base text-danger">
                            ×
                          </span>
                        </div>

                        <p className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">
                          {inventory.out_of_stock_items}
                        </p>

                        <p className="mt-1.5 text-xs text-muted">
                          Products with zero stock
                        </p>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* Recent Orders */}
              <section className="overflow-hidden rounded-lg border border-border bg-surface">
                <div className="flex flex-col justify-between gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:px-5">
                  <div>
                    <h2 className="text-sm font-semibold">Recent orders</h2>
                    <p className="mt-1 text-xs text-muted">
                      Latest activity across the order pipeline.
                    </p>
                  </div>

                  <a
                    href="/orders"
                    className="self-start text-xs font-medium text-accent transition hover:text-accent-hover sm:self-auto"
                  >
                    View all orders →
                  </a>
                </div>

                {/* Mobile Order Cards */}
                <div className="divide-y divide-border md:hidden">
                  {recentOrders.map((order) => (
                    <div key={order.id} className="space-y-4 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs text-muted">Order ID</p>
                          <p className="mt-1 break-all text-sm font-medium">
                            {order.id}
                          </p>
                        </div>

                        <StatusBadge status={order.status} />
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted">Product</p>
                          <p className="mt-1 break-all text-sm text-muted-foreground">
                            {order.product}
                          </p>
                        </div>

                        <div>
                          <p className="mb-1 text-xs text-muted">Delivery</p>
                          <StatusBadge status={order.delivery} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {/* Desktop Orders Table */}
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-border text-xs text-muted">
                        <th className="px-5 py-3 font-medium">Order ID</th>
                        <th className="px-5 py-3 font-medium">Product</th>
                        <th className="px-5 py-3 font-medium">Order status</th>
                        <th className="px-5 py-3 font-medium">Delivery</th>
                      </tr>
                    </thead>

                    <tbody>
                      {recentOrders.map((order) => (
                        <tr
                          key={order.id}
                          className="border-b border-border last:border-0 transition hover:bg-surface-hover"
                        >
                          <td className="px-5 py-4 text-sm font-medium">
                            {order.id}
                          </td>

                          <td className="px-5 py-4 text-sm text-muted-foreground">
                            {order.product}
                          </td>

                          <td className="px-5 py-4">
                            <StatusBadge status={order.status} />
                          </td>

                          <td className="px-5 py-4">
                            <StatusBadge status={order.delivery} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </section>
        </div>

        {/* Create Order Modal */}
        {createOrderOpen && (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 px-4 py-6"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                closeCreateOrder();
              }
            }}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-order-title"
              className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-2xl"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-medium text-accent">
                    FlowMesh / Orders
                  </p>

                  <h2
                    id="create-order-title"
                    className="mt-2 text-xl font-semibold tracking-tight"
                  >
                    Create new order
                  </h2>

                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    Enter the product ID and quantity to place a new order.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={closeCreateOrder}
                  disabled={submitting}
                  aria-label="Close create order modal"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground transition hover:bg-surface-hover disabled:opacity-50"
                >
                  ×
                </button>
              </div>

              <form onSubmit={handleCreateOrder} className="mt-6 space-y-5">
                {/* Product ID */}
                <div>
                  <label
                    htmlFor="productId"
                    className="mb-2 block text-sm font-medium"
                  >
                    Product ID
                  </label>

                  <input
                    id="productId"
                    type="text"
                    value={productId}
                    onChange={(event) => setProductId(event.target.value)}
                    placeholder="e.g. product_123"
                    required
                    disabled={submitting}
                    className="h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-accent disabled:opacity-50"
                  />
                </div>

                {/* Quantity */}
                <div>
                  <label
                    htmlFor="quantity"
                    className="mb-2 block text-sm font-medium"
                  >
                    Quantity
                  </label>

                  <input
                    id="quantity"
                    type="number"
                    min="1"
                    step="1"
                    value={quantity}
                    onChange={(event) => setQuantity(event.target.value)}
                    required
                    disabled={submitting}
                    className="h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-accent disabled:opacity-50"
                  />
                </div>

                {/* Error */}
                {orderError && (
                  <div
                    role="alert"
                    className="rounded-md border border-danger/20 bg-danger/10 p-3"
                  >
                    <p className="text-sm text-danger">{orderError}</p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col-reverse gap-3 border-t border-border pt-5 sm:flex-row sm:justify-end">
                  <button
                    type="button"
                    onClick={closeCreateOrder}
                    disabled={submitting}
                    className="rounded-md border border-border px-4 py-2.5 text-sm font-medium transition hover:bg-surface-hover disabled:opacity-50"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-[#101614] transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submitting ? "Creating order..." : "Create order"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}
