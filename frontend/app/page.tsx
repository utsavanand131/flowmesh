"use client";

import { useState } from "react";
import AppSidebar from "@/components/AppSidebar";

const stats = [
  {
    label: "Total orders",
    value: "24",
    detail: "Last 24 hours",
    icon: "▤",
  },
  {
    label: "Pending",
    value: "03",
    detail: "Awaiting processing",
    icon: "◷",
  },
  {
    label: "In delivery",
    value: "05",
    detail: "Active deliveries",
    icon: "↗",
  },
  {
    label: "Delivered",
    value: "16",
    detail: "Completed orders",
    icon: "✓",
  },
];

const recentOrders = [
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
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

              <button className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-[#101614] transition hover:bg-accent-hover">
                <span className="text-lg leading-none">+</span>
                Create order
              </button>
            </section>

            {/* System Metrics */}
            <section>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-semibold">System metrics</h2>
                <span className="text-xs text-muted">Last 24 hours</span>
              </div>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {stats.map((stat) => (
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

                    <p className="mt-1.5 text-xs text-muted">{stat.detail}</p>
                  </div>
                ))}
              </div>
            </section>

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
                        <p className="mt-1 text-sm font-medium">{order.id}</p>
                      </div>

                      <StatusBadge status={order.status} />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-muted">Product</p>
                        <p className="mt-1 text-sm text-muted-foreground">
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
    </main>
  );
}
