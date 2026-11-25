"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface InventoryItem {
  product_id: string;
  quantity: number;
}

interface InventoryResponse {
  items: InventoryItem[];
  total_items: number;
  total_quantity: number;
  low_stock_items: number;
  out_of_stock_items: number;
  low_stock_threshold: number;
}

type InventoryFilter = "ALL" | "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK";

function getStockStatus(quantity: number, threshold: number) {
  if (quantity === 0) {
    return "OUT OF STOCK";
  }

  if (quantity <= threshold) {
    return "LOW STOCK";
  }

  return "IN STOCK";
}

function StockBadge({
  quantity,
  threshold,
}: {
  quantity: number;
  threshold: number;
}) {
  const status = getStockStatus(quantity, threshold);

  const styles =
    status === "OUT OF STOCK"
      ? "border-danger/20 bg-danger/10 text-danger"
      : status === "LOW STOCK"
        ? "border-warning/20 bg-warning/10 text-warning"
        : "border-success/20 bg-success/10 text-success";

  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-md border px-2.5 py-1 text-xs font-medium ${styles}`}
    >
      {status}
    </span>
  );
}

export default function InventoryPage() {
  const { user } = useAuth();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [summary, setSummary] = useState({
    totalItems: 0,
    totalQuantity: 0,
    lowStockItems: 0,
    outOfStockItems: 0,
    lowStockThreshold: 10,
  });

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<InventoryFilter>("ALL");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const isAdmin = user?.role === "ADMIN";

  const fetchInventory = useCallback(async (signal: AbortSignal) => {
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
      const response = await fetch(`${API_URL}/inventory`, {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json",
        },
        signal,
      });

      if (!response.ok) {
        let message = "Unable to load inventory.";

        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch {
          // Keep the default error message.
        }

        throw new Error(message);
      }

      const data: InventoryResponse = await response.json();

      setInventory(data.items ?? []);

      setSummary({
        totalItems: data.total_items ?? 0,
        totalQuantity: data.total_quantity ?? 0,
        lowStockItems: data.low_stock_items ?? 0,
        outOfStockItems: data.out_of_stock_items ?? 0,
        lowStockThreshold: data.low_stock_threshold ?? 10,
      });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }

      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      if (!signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const controller = new AbortController();

    fetchInventory(controller.signal);

    return () => controller.abort();
  }, [fetchInventory, refreshKey, isAdmin]);

  const filteredInventory = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return inventory.filter((item) => {
      const matchesSearch = item.product_id
        .toLowerCase()
        .includes(normalizedSearch);

      const status = getStockStatus(item.quantity, summary.lowStockThreshold);

      const matchesFilter =
        filter === "ALL" ||
        (filter === "IN_STOCK" && status === "IN STOCK") ||
        (filter === "LOW_STOCK" && status === "LOW STOCK") ||
        (filter === "OUT_OF_STOCK" && status === "OUT OF STOCK");

      return matchesSearch && matchesFilter;
    });
  }, [inventory, search, filter, summary.lowStockThreshold]);

  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-background text-foreground">
        <div className="flex min-h-screen">
          {/* Desktop Sidebar */}
          <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
            <AppSidebar activeItem="Inventory" />
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
                  activeItem="Inventory"
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
                  Inventory
                </h1>
              </div>
            </header>

            <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              {/* Access Check */}
              {!isAdmin ? (
                <section className="rounded-lg border border-danger/20 bg-danger/10 p-6">
                  <h2 className="font-semibold text-danger">Access denied</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    You need administrator access to manage inventory.
                  </p>
                </section>
              ) : (
                <>
                  {/* Page Introduction */}
                  <section className="flex flex-col justify-between gap-4 border-b border-border pb-7 sm:flex-row sm:items-end">
                    <div>
                      <p className="text-sm font-medium text-accent">
                        FlowMesh / Operations
                      </p>

                      <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                        Inventory Management
                      </h2>

                      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                        Monitor product availability, identify low-stock items,
                        and manage inventory levels across the system.
                      </p>
                    </div>

                    <button
                      onClick={() => setRefreshKey((current) => current + 1)}
                      disabled={loading}
                      className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border bg-surface px-4 text-sm font-medium text-foreground transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loading ? "Loading..." : "↻ Refresh"}
                    </button>
                  </section>

                  {/* Inventory Summary */}
                  <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-lg border border-border bg-surface p-5">
                      <p className="text-sm text-muted-foreground">
                        Total Products
                      </p>
                      <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
                        {loading ? "—" : summary.totalItems}
                      </p>
                    </div>

                    <div className="rounded-lg border border-border bg-surface p-5">
                      <p className="text-sm text-muted-foreground">
                        Total Units
                      </p>
                      <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
                        {loading ? "—" : summary.totalQuantity}
                      </p>
                    </div>

                    <div className="rounded-lg border border-warning/20 bg-surface p-5">
                      <p className="text-sm text-muted-foreground">
                        Low Stock Items
                      </p>
                      <p className="mt-2 text-3xl font-semibold tracking-tight text-warning tabular-nums">
                        {loading ? "—" : summary.lowStockItems}
                      </p>
                    </div>

                    <div className="rounded-lg border border-danger/20 bg-surface p-5">
                      <p className="text-sm text-muted-foreground">
                        Out of Stock
                      </p>
                      <p className="mt-2 text-3xl font-semibold tracking-tight text-danger tabular-nums">
                        {loading ? "—" : summary.outOfStockItems}
                      </p>
                    </div>
                  </section>

                  {/* Inventory Table */}
                  <section className="overflow-hidden rounded-lg border border-border bg-surface">
                    <div className="flex flex-col gap-4 border-b border-border px-5 py-4">
                      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <h3 className="text-sm font-semibold">
                            Inventory Workspace
                          </h3>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Live stock data from the FlowMesh Inventory Service
                          </p>
                        </div>

                        <span className="text-xs text-muted-foreground">
                          {loading
                            ? "Fetching inventory..."
                            : `${filteredInventory.length} of ${inventory.length} products`}
                        </span>
                      </div>

                      {/* Search and Filters */}
                      <div className="flex flex-col gap-3 sm:flex-row">
                        <input
                          type="search"
                          value={search}
                          onChange={(event) => setSearch(event.target.value)}
                          placeholder="Search by product ID..."
                          className="h-10 min-w-0 flex-1 rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-accent"
                        />

                        <select
                          value={filter}
                          onChange={(event) =>
                            setFilter(event.target.value as InventoryFilter)
                          }
                          className="h-10 rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-accent"
                        >
                          <option value="ALL">All products</option>
                          <option value="IN_STOCK">In stock</option>
                          <option value="LOW_STOCK">Low stock</option>
                          <option value="OUT_OF_STOCK">Out of stock</option>
                        </select>
                      </div>
                    </div>

                    {/* Error */}
                    {error && (
                      <div className="m-5 rounded-md border border-danger/20 bg-danger/10 p-4">
                        <p className="text-sm font-medium text-danger">
                          Could not load inventory
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          {error}
                        </p>
                        <button
                          onClick={() =>
                            setRefreshKey((current) => current + 1)
                          }
                          className="mt-3 text-sm font-medium text-accent hover:underline"
                        >
                          Try again
                        </button>
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
                    {!error && !loading && inventory.length === 0 && (
                      <div className="px-5 py-16 text-center">
                        <p className="text-sm font-medium">
                          No inventory items found
                        </p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          Products will appear here when they are added to
                          inventory.
                        </p>
                      </div>
                    )}

                    {/* No Search Results */}
                    {!error &&
                      !loading &&
                      inventory.length > 0 &&
                      filteredInventory.length === 0 && (
                        <div className="px-5 py-16 text-center">
                          <p className="text-sm font-medium">
                            No matching products
                          </p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Try changing your search or stock filter.
                          </p>
                        </div>
                      )}

                    {/* Table */}
                    {!error && !loading && filteredInventory.length > 0 && (
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[650px] text-left text-sm">
                          <thead className="border-b border-border bg-surface-muted/50">
                            <tr className="text-xs text-muted-foreground">
                              <th className="px-5 py-3 font-medium">
                                Product ID
                              </th>
                              <th className="px-5 py-3 font-medium">
                                Available Quantity
                              </th>
                              <th className="px-5 py-3 font-medium">
                                Stock Status
                              </th>
                            </tr>
                          </thead>

                          <tbody className="divide-y divide-border">
                            {filteredInventory.map((item) => (
                              <tr
                                key={item.product_id}
                                className="transition hover:bg-surface-hover/50"
                              >
                                <td className="px-5 py-4 font-mono text-xs text-accent">
                                  {item.product_id}
                                </td>

                                <td className="px-5 py-4 tabular-nums">
                                  {item.quantity}
                                </td>

                                <td className="px-5 py-4">
                                  <StockBadge
                                    quantity={item.quantity}
                                    threshold={summary.lowStockThreshold}
                                  />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                </>
              )}
            </div>
          </section>
        </div>
      </main>
    </ProtectedRoute>
  );
}
