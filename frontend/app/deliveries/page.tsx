"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const PAGE_SIZE = 10;

interface Delivery {
  delivery_id: string;
  order_id: string;
  status: string;
}

interface DeliveriesResponse {
  deliveries: Delivery[];
  total: number;
  page: number;
  page_size: number;
}

type UpdateableStatus = "PICKED_UP" | "IN_TRANSIT" | "DELIVERED";

interface ActionMessage {
  type: "success" | "error";
  message: string;
}

function formatStatus(status?: string) {
  if (!status) return "N/A";

  return status
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getNextStatuses(status?: string): UpdateableStatus[] {
  switch (status?.toUpperCase()) {
    case "ASSIGNED":
      return ["PICKED_UP"];

    case "PICKED_UP":
      return ["IN_TRANSIT"];

    case "IN_TRANSIT":
      return ["DELIVERED"];

    default:
      return [];
  }
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
  } else if (["CANCELLED", "FAILED", "REJECTED"].includes(normalizedStatus)) {
    styles = "border-danger/20 bg-danger/10 text-danger";
  }

  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-md border px-2.5 py-1 text-xs font-medium ${styles}`}
    >
      {formatStatus(status)}
    </span>
  );
}

export default function DeliveriesPage() {
  const { user } = useAuth();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const [selectedStatuses, setSelectedStatuses] = useState<
    Record<string, string>
  >({});

  const [updatingDeliveryId, setUpdatingDeliveryId] = useState<string | null>(
    null,
  );

  const [actionMessage, setActionMessage] = useState<ActionMessage | null>(
    null,
  );

  const isAdmin = user?.role === "ADMIN";

  const fetchDeliveries = useCallback(
    async (signal: AbortSignal) => {
      if (!API_URL) {
        setError(
          "API URL is not configured. Check your frontend environment variables.",
        );
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      setActionMessage(null);

      try {
        const response = await fetch(
          `${API_URL}/deliveries?page=${page}&page_size=${PAGE_SIZE}`,
          {
            method: "GET",
            credentials: "include",
            headers: {
              Accept: "application/json",
            },
            signal,
          },
        );

        if (!response.ok) {
          let message = "Unable to load deliveries.";

          try {
            const data = await response.json();

            if (response.status === 403) {
              message = "Admin access required.";
            } else {
              message = data.detail || data.message || message;
            }
          } catch {
            // Keep the default error message.
          }

          throw new Error(message);
        }

        const data: DeliveriesResponse = await response.json();

        const records = data.deliveries ?? [];

        setDeliveries(records);
        setTotal(data.total ?? 0);

        setSelectedStatuses(
          Object.fromEntries(
            records.map((delivery) => [delivery.delivery_id, delivery.status]),
          ),
        );
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;

        setError(err instanceof Error ? err.message : "Something went wrong.");
      } finally {
        if (!signal.aborted) {
          setLoading(false);
        }
      }
    },
    [page],
  );

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();

    fetchDeliveries(controller.signal);

    return () => controller.abort();
  }, [fetchDeliveries, refreshKey, isAdmin]);

  const handleStatusUpdate = async (delivery: Delivery) => {
    if (!API_URL) {
      setActionMessage({
        type: "error",
        message: "API URL is not configured.",
      });
      return;
    }

    const newStatus = selectedStatuses[delivery.delivery_id];

    if (!newStatus || newStatus === delivery.status) {
      return;
    }

    const allowedStatuses = getNextStatuses(delivery.status);

    if (!allowedStatuses.includes(newStatus as UpdateableStatus)) {
      setActionMessage({
        type: "error",
        message: "Invalid status transition. Select the next valid status.",
      });
      return;
    }

    setUpdatingDeliveryId(delivery.delivery_id);
    setActionMessage(null);

    try {
      const response = await fetch(
        `${API_URL}/deliveries/${encodeURIComponent(
          delivery.delivery_id,
        )}/status`,
        {
          method: "PATCH",
          credentials: "include",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status: newStatus,
          }),
        },
      );

      if (!response.ok) {
        let message = "Unable to update delivery status.";

        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {
          // Keep the default error message.
        }

        throw new Error(message);
      }

      setDeliveries((current) =>
        current.map((item) =>
          item.delivery_id === delivery.delivery_id
            ? { ...item, status: newStatus }
            : item,
        ),
      );

      setSelectedStatuses((current) => ({
        ...current,
        [delivery.delivery_id]: newStatus,
      }));

      setActionMessage({
        type: "success",
        message: `Delivery status updated to ${formatStatus(newStatus)}.`,
      });
    } catch (err) {
      setActionMessage({
        type: "error",
        message:
          err instanceof Error
            ? err.message
            : "Something went wrong while updating the delivery.",
      });
    } finally {
      setUpdatingDeliveryId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const assignedCount = deliveries.filter(
    (delivery) => delivery.status === "ASSIGNED",
  ).length;

  const pickedUpCount = deliveries.filter(
    (delivery) => delivery.status === "PICKED_UP",
  ).length;

  const inTransitCount = deliveries.filter(
    (delivery) => delivery.status === "IN_TRANSIT",
  ).length;

  const deliveredCount = deliveries.filter(
    (delivery) => delivery.status === "DELIVERED",
  ).length;

  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-background text-foreground">
        {!isAdmin ? (
          <div className="flex min-h-screen items-center justify-center px-4">
            <div className="max-w-md rounded-lg border border-border bg-surface p-8 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-xl text-danger">
                !
              </div>

              <h1 className="mt-4 text-xl font-semibold">Access restricted</h1>

              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Delivery management is available to FlowMesh administrators
                only.
              </p>

              <Link
                href="/"
                className="mt-6 inline-flex items-center justify-center rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-background transition hover:bg-accent-hover"
              >
                Return to Dashboard
              </Link>
            </div>
          </div>
        ) : (
          <div className="flex min-h-screen">
            {/* Desktop Sidebar */}
            <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
              <AppSidebar activeItem="Deliveries" />
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
                    activeItem="Deliveries"
                    onNavigate={() => setMobileMenuOpen(false)}
                  />
                </aside>
              </div>
            )}

            {/* Main Content */}
            <section className="min-w-0 flex-1">
              {/* Header */}
              <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-background/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
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
                    Deliveries
                  </h1>
                </div>
              </header>

              {/* Delivery Content */}
              <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
                {/* Page Introduction */}
                <section className="flex flex-col justify-between gap-4 border-b border-border pb-7 sm:flex-row sm:items-end">
                  <div>
                    <p className="text-sm font-medium text-accent">
                      FlowMesh / Operations
                    </p>

                    <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                      Delivery Management
                    </h2>

                    <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                      Monitor delivery assignments, track fulfillment progress,
                      and manage delivery statuses across FlowMesh.
                    </p>
                  </div>

                  <button
                    onClick={() => setRefreshKey((current) => current + 1)}
                    disabled={loading || updatingDeliveryId !== null}
                    className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border bg-surface px-4 text-sm font-medium text-foreground transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span>{loading ? "Loading..." : "↻ Refresh"}</span>
                  </button>
                </section>

                {/* Delivery Summary */}
                <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                  <div className="rounded-lg border border-border bg-surface p-5">
                    <p className="text-sm text-muted-foreground">
                      Total Deliveries
                    </p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
                      {loading ? "—" : total}
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface p-5">
                    <p className="text-sm text-muted-foreground">Assigned</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums text-warning">
                      {loading ? "—" : assignedCount}
                    </p>
                    <p className="mt-1 text-xs text-muted">On this page</p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface p-5">
                    <p className="text-sm text-muted-foreground">Picked Up</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
                      {loading ? "—" : pickedUpCount}
                    </p>
                    <p className="mt-1 text-xs text-muted">On this page</p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface p-5">
                    <p className="text-sm text-muted-foreground">In Transit</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums text-accent">
                      {loading ? "—" : inTransitCount}
                    </p>
                    <p className="mt-1 text-xs text-muted">On this page</p>
                  </div>

                  <div className="rounded-lg border border-border bg-surface p-5">
                    <p className="text-sm text-muted-foreground">Delivered</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums text-success">
                      {loading ? "—" : deliveredCount}
                    </p>
                    <p className="mt-1 text-xs text-muted">On this page</p>
                  </div>
                </section>

                {/* Deliveries Table */}
                <section className="overflow-hidden rounded-lg border border-border bg-surface">
                  <div className="flex flex-col gap-1 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-sm font-semibold">
                        Deliveries Workspace
                      </h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Live delivery data from the FlowMesh API
                      </p>
                    </div>

                    <span className="text-xs text-muted-foreground">
                      {loading
                        ? "Fetching deliveries..."
                        : `${total} total records`}
                    </span>
                  </div>

                  {/* Error */}
                  {error && (
                    <div className="m-5 rounded-md border border-danger/20 bg-danger/10 p-4">
                      <p className="text-sm font-medium text-danger">
                        Could not load deliveries
                      </p>

                      <p className="mt-1 text-sm text-muted-foreground">
                        {error}
                      </p>

                      <button
                        onClick={() => setRefreshKey((current) => current + 1)}
                        className="mt-3 text-sm font-medium text-accent hover:underline"
                      >
                        Try again
                      </button>
                    </div>
                  )}

                  {/* Update Feedback */}
                  {actionMessage && (
                    <div
                      role="status"
                      aria-live="polite"
                      className={`mx-5 mt-5 rounded-md border p-4 ${
                        actionMessage.type === "success"
                          ? "border-success/20 bg-success/10 text-success"
                          : "border-danger/20 bg-danger/10 text-danger"
                      }`}
                    >
                      <p className="text-sm font-medium">
                        {actionMessage.message}
                      </p>
                    </div>
                  )}

                  {/* Loading */}
                  {!error && loading && (
                    <div className="space-y-3 p-5">
                      {[1, 2, 3, 4].map((item) => (
                        <div
                          key={item}
                          className="h-12 animate-pulse rounded-md bg-surface-muted"
                        />
                      ))}
                    </div>
                  )}

                  {/* Empty State */}
                  {!error && !loading && deliveries.length === 0 && (
                    <div className="px-5 py-16 text-center">
                      <p className="text-sm font-medium">No deliveries found</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Deliveries will appear here when they are created.
                      </p>
                    </div>
                  )}

                  {/* Delivery Records */}
                  {!error && !loading && deliveries.length > 0 && (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[1000px] text-left text-sm">
                          <thead className="border-b border-border bg-surface-muted/50">
                            <tr className="text-xs text-muted-foreground">
                              <th className="px-5 py-3 font-medium">
                                Delivery ID
                              </th>
                              <th className="px-5 py-3 font-medium">
                                Order ID
                              </th>
                              <th className="px-5 py-3 font-medium">
                                Delivery Status
                              </th>
                              <th className="px-5 py-3 font-medium">
                                Update Status
                              </th>
                              <th className="px-5 py-3 text-right font-medium">
                                Action
                              </th>
                            </tr>
                          </thead>

                          <tbody className="divide-y divide-border">
                            {deliveries.map((delivery) => {
                              const nextStatuses = getNextStatuses(
                                delivery.status,
                              );

                              const selectedStatus =
                                selectedStatuses[delivery.delivery_id] ??
                                delivery.status;

                              const isUpdating =
                                updatingDeliveryId === delivery.delivery_id;

                              const hasChanged =
                                selectedStatus !== delivery.status;

                              return (
                                <tr
                                  key={delivery.delivery_id}
                                  className="transition hover:bg-surface-hover/50"
                                >
                                  <td className="px-5 py-4 font-mono text-xs text-accent">
                                    {delivery.delivery_id}
                                  </td>

                                  <td className="px-5 py-4 font-mono text-xs text-muted-foreground">
                                    {delivery.order_id}
                                  </td>

                                  <td className="px-5 py-4">
                                    <StatusBadge status={delivery.status} />
                                  </td>

                                  <td className="px-5 py-4">
                                    <select
                                      value={selectedStatus}
                                      disabled={
                                        nextStatuses.length === 0 || isUpdating
                                      }
                                      onChange={(event) => {
                                        setSelectedStatuses((current) => ({
                                          ...current,
                                          [delivery.delivery_id]:
                                            event.target.value,
                                        }));
                                        setActionMessage(null);
                                      }}
                                      className="h-9 min-w-36 rounded-md border border-border bg-background px-3 text-xs text-foreground outline-none transition focus:border-accent disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      <option value={delivery.status}>
                                        {formatStatus(delivery.status)}
                                      </option>

                                      {nextStatuses.map((status) => (
                                        <option key={status} value={status}>
                                          {formatStatus(status)}
                                        </option>
                                      ))}
                                    </select>
                                  </td>

                                  <td className="px-5 py-4 text-right">
                                    <button
                                      onClick={() =>
                                        handleStatusUpdate(delivery)
                                      }
                                      disabled={
                                        !hasChanged ||
                                        isUpdating ||
                                        updatingDeliveryId !== null
                                      }
                                      className="inline-flex min-w-24 items-center justify-center rounded-md bg-accent px-3 py-2 text-xs font-medium text-background transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                      {isUpdating ? "Updating..." : "Update"}
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>

                      {/* Pagination */}
                      <div className="flex flex-col gap-3 border-t border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-xs text-muted-foreground">
                          Showing {(page - 1) * PAGE_SIZE + 1}–
                          {Math.min(page * PAGE_SIZE, total)} of {total}{" "}
                          deliveries
                        </p>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setPage((current) => current - 1)}
                            disabled={page <= 1 || updatingDeliveryId !== null}
                            className="rounded-md border border-border px-3 py-2 text-xs font-medium transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Previous
                          </button>

                          <span className="px-2 text-xs tabular-nums text-muted-foreground">
                            Page {page} of {totalPages}
                          </span>

                          <button
                            onClick={() => setPage((current) => current + 1)}
                            disabled={
                              page >= totalPages || updatingDeliveryId !== null
                            }
                            className="rounded-md border border-border px-3 py-2 text-xs font-medium transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </section>

                {/* Monitoring Information */}
                <section className="rounded-lg border border-border bg-surface p-5">
                  <h3 className="text-sm font-semibold">
                    Delivery Information
                  </h3>

                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    Delivery records are retrieved from the FlowMesh Delivery
                    Service through the API Gateway. Administrators can update
                    delivery statuses as fulfillment progresses.
                  </p>

                  <p className="mt-3 text-xs text-muted">
                    Status counts represent the records currently displayed on
                    this page. Use pagination to view additional deliveries.
                  </p>
                </section>
              </div>
            </section>
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}
