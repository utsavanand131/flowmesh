"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface Order {
  order_id: string;
  user_id: string;
  product_id: string;
  quantity: number;
  status: string;
  delivery?: {
    delivery_id?: string;
    status?: string;
  } | null;
}

const DELIVERY_STAGES = [
  {
    status: "ASSIGNED",
    title: "Delivery Assigned",
    description: "A delivery has been assigned to your order.",
  },
  {
    status: "PICKED_UP",
    title: "Order Picked Up",
    description: "Your order has been picked up for delivery.",
  },
  {
    status: "IN_TRANSIT",
    title: "In Transit",
    description: "Your order is on its way to its destination.",
  },
  {
    status: "DELIVERED",
    title: "Delivered",
    description: "Your order has been successfully delivered.",
  },
];

function formatStatus(status?: string) {
  if (!status) return "N/A";

  return status
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getCurrentStage(status?: string) {
  return DELIVERY_STAGES.findIndex(
    (stage) => stage.status === status?.toUpperCase(),
  );
}

function StatusBadge({ status }: { status?: string }) {
  const normalizedStatus = status?.toUpperCase() ?? "";

  let styles = "border-border bg-surface-muted text-muted-foreground";

  if (normalizedStatus === "DELIVERED") {
    styles = "border-success/20 bg-success/10 text-success";
  } else if (
    ["ASSIGNED", "PICKED_UP", "IN_TRANSIT"].includes(normalizedStatus)
  ) {
    styles = "border-warning/20 bg-warning/10 text-warning";
  }

  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-md border px-3 py-1.5 text-xs font-medium ${styles}`}
    >
      {formatStatus(status)}
    </span>
  );
}

export default function DeliveryTrackingPage() {
  const params = useParams<{ orderId: string }>();
  const orderId = params.orderId;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function fetchOrder() {
      if (!API_URL) {
        setError(
          "API URL is not configured. Check your frontend environment variables.",
        );
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");

      try {
        const response = await fetch(
          `${API_URL}/orders/${encodeURIComponent(orderId)}`,
          {
            method: "GET",
            credentials: "include",
            headers: {
              Accept: "application/json",
            },
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          let message = "Unable to retrieve order details.";

          try {
            const data = await response.json();
            message = data.detail || data.message || message;
          } catch {
            // Keep the default error message.
          }

          throw new Error(message);
        }

        const data: Order = await response.json();
        setOrder(data);
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;

        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    fetchOrder();

    return () => controller.abort();
  }, [orderId]);

  const deliveryStatus = order?.delivery?.status?.toUpperCase();
  const currentStage = getCurrentStage(deliveryStatus);
  const hasDelivery = Boolean(order?.delivery?.delivery_id);

  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-background text-foreground">
        <div className="flex min-h-screen">
          {/* Desktop Sidebar */}
          <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
            <AppSidebar activeItem="Orders" />
          </aside>

          {/* Main Content */}
          <section className="min-w-0 flex-1">
            {/* Header */}
            <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
              <div>
                <p className="text-xs text-muted">Orders / Tracking</p>
                <h1 className="mt-0.5 text-lg font-semibold tracking-tight sm:text-xl">
                  Delivery Tracking
                </h1>
              </div>
            </header>

            <div className="mx-auto max-w-5xl space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              {/* Page Introduction */}
              <section className="border-b border-border pb-7">
                <p className="text-sm font-medium text-accent">
                  FlowMesh / Order Tracking
                </p>

                <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                  Track Your Delivery
                </h2>

                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Follow your order as it moves through the delivery process.
                </p>

                <Link
                  href="/orders"
                  className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-accent transition hover:underline"
                >
                  ← Back to Orders
                </Link>
              </section>

              {/* Loading */}
              {loading && (
                <section className="space-y-4 rounded-lg border border-border bg-surface p-6">
                  <div className="h-5 w-40 animate-pulse rounded bg-surface-muted" />
                  <div className="h-4 w-64 animate-pulse rounded bg-surface-muted" />
                  <div className="h-32 animate-pulse rounded-md bg-surface-muted" />
                </section>
              )}

              {/* Error */}
              {!loading && error && (
                <section className="rounded-lg border border-danger/20 bg-danger/10 p-6">
                  <h3 className="text-sm font-semibold text-danger">
                    Could Not Load Order
                  </h3>

                  <p className="mt-2 text-sm text-muted-foreground">{error}</p>

                  <Link
                    href="/orders"
                    className="mt-4 inline-flex text-sm font-medium text-accent hover:underline"
                  >
                    Return to Orders
                  </Link>
                </section>
              )}

              {/* Order Details */}
              {!loading && !error && order && (
                <>
                  <section className="rounded-lg border border-border bg-surface p-5 sm:p-6">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                      <div>
                        <p className="text-sm text-muted-foreground">
                          Order ID
                        </p>

                        <p className="mt-2 break-all font-mono text-sm font-medium text-accent">
                          {order.order_id}
                        </p>
                      </div>

                      <StatusBadge status={order.delivery?.status} />
                    </div>

                    <div className="mt-6 grid gap-5 border-t border-border pt-5 sm:grid-cols-2">
                      <div>
                        <p className="text-xs text-muted-foreground">
                          Product ID
                        </p>
                        <p className="mt-1 font-mono text-sm">
                          {order.product_id}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground">
                          Quantity
                        </p>
                        <p className="mt-1 text-sm font-medium tabular-nums">
                          {order.quantity}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground">
                          Order Status
                        </p>
                        <p className="mt-1 text-sm font-medium">
                          {formatStatus(order.status)}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground">
                          Delivery ID
                        </p>
                        <p className="mt-1 break-all font-mono text-sm">
                          {order.delivery?.delivery_id ?? "Not assigned yet"}
                        </p>
                      </div>
                    </div>
                  </section>

                  {/* Delivery Progress */}
                  <section className="overflow-hidden rounded-lg border border-border bg-surface">
                    <div className="border-b border-border px-5 py-5 sm:px-6">
                      <h3 className="text-base font-semibold">
                        Delivery Progress
                      </h3>

                      <p className="mt-1 text-sm text-muted-foreground">
                        Follow each stage of your delivery.
                      </p>
                    </div>

                    {!hasDelivery && (
                      <div className="p-6 sm:p-8">
                        <div className="rounded-lg border border-warning/20 bg-warning/10 p-5">
                          <p className="text-sm font-semibold text-warning">
                            Delivery Assignment Pending
                          </p>

                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            Your order has been created successfully, but a
                            delivery has not been assigned yet. Tracking
                            information will become available once the
                            assignment is completed.
                          </p>
                        </div>
                      </div>
                    )}

                    {hasDelivery && (
                      <div className="p-6 sm:p-8">
                        {currentStage === -1 ? (
                          <div className="rounded-lg border border-warning/20 bg-warning/10 p-5">
                            <p className="text-sm font-semibold text-warning">
                              Delivery Status: {formatStatus(deliveryStatus)}
                            </p>

                            <p className="mt-2 text-sm text-muted-foreground">
                              The current delivery status does not match the
                              standard tracking stages.
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-0">
                            {DELIVERY_STAGES.map((stage, index) => {
                              const completed = index <= currentStage;
                              const active = index === currentStage;
                              const last = index === DELIVERY_STAGES.length - 1;

                              return (
                                <div
                                  key={stage.status}
                                  className="relative flex gap-4"
                                >
                                  {/* Timeline Indicator */}
                                  <div className="flex w-8 shrink-0 flex-col items-center">
                                    <div
                                      className={`z-10 flex h-8 w-8 items-center justify-center rounded-full border text-sm font-semibold ${
                                        completed
                                          ? "border-success bg-success text-white"
                                          : "border-border bg-surface-muted text-muted-foreground"
                                      }`}
                                    >
                                      {completed ? "✓" : index + 1}
                                    </div>

                                    {!last && (
                                      <div
                                        className={`my-1 min-h-12 w-0.5 flex-1 ${
                                          index < currentStage
                                            ? "bg-success"
                                            : "bg-border"
                                        }`}
                                      />
                                    )}
                                  </div>

                                  {/* Stage Information */}
                                  <div className="min-w-0 pb-8">
                                    <p
                                      className={`text-sm font-semibold ${
                                        active
                                          ? "text-success"
                                          : completed
                                            ? "text-foreground"
                                            : "text-muted-foreground"
                                      }`}
                                    >
                                      {stage.title}
                                    </p>

                                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                                      {stage.description}
                                    </p>

                                    {active && (
                                      <span className="mt-2 inline-flex rounded-md border border-success/20 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                                        Current Status
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </section>

                  <p className="text-center text-xs leading-5 text-muted-foreground">
                    Delivery progress reflects the latest status reported by
                    FlowMesh.
                  </p>
                </>
              )}
            </div>
          </section>
        </div>
      </main>
    </ProtectedRoute>
  );
}
