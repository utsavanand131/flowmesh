"use client";

import { useState } from "react";

const stats = [
  {
    label: "TOTAL ORDERS",
    value: "24",
    detail: "LAST 24 HOURS",
  },
  {
    label: "PENDING",
    value: "03",
    detail: "AWAITING PROCESSING",
  },
  {
    label: "IN DELIVERY",
    value: "05",
    detail: "ACTIVE DELIVERIES",
  },
  {
    label: "DELIVERED",
    value: "16",
    detail: "COMPLETED ORDERS",
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
  const statusClass =
    status === "DELIVERED"
      ? "border-success/40 text-success"
      : status === "IN_TRANSIT"
        ? "border-accent/40 text-accent"
        : status === "CONFIRMED"
          ? "border-warning/40 text-warning"
          : "border-muted/40 text-muted";

  return (
    <span
      className={`inline-flex items-center gap-2 border px-2.5 py-1 text-xs tracking-wider ${statusClass}`}
    >
      <span>●</span>
      {status}
    </span>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="border-b border-border px-6 py-6">
        <div className="text-xl font-bold tracking-[0.2em] text-accent">
          FLOWMESH
        </div>

        <div className="mt-2 text-xs tracking-wider text-muted">
          DISTRIBUTED ORDER SYSTEM
        </div>
      </div>

      <nav className="flex-1 px-3 py-6">
        <div className="mb-3 px-3 text-[10px] tracking-[0.2em] text-muted">
          OPERATIONS
        </div>

        <div className="space-y-1">
          <button
            onClick={onNavigate}
            className="flex w-full items-center gap-3 border border-accent/30 bg-accent/10 px-3 py-3 text-left text-sm text-accent"
          >
            <span>▣</span>
            DASHBOARD
          </button>

          <button
            onClick={onNavigate}
            className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-muted transition hover:bg-surface-hover hover:text-foreground"
          >
            <span>□</span>
            ORDERS
          </button>

          <button
            onClick={onNavigate}
            className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-muted transition hover:bg-surface-hover hover:text-foreground"
          >
            <span>↗</span>
            DELIVERIES
          </button>
        </div>

        <div className="mb-3 mt-8 px-3 text-[10px] tracking-[0.2em] text-muted">
          SYSTEM
        </div>

        <div className="space-y-1">
          <button
            onClick={onNavigate}
            className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-muted transition hover:bg-surface-hover hover:text-foreground"
          >
            <span>◉</span>
            SERVICES
          </button>

          <button
            onClick={onNavigate}
            className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-muted transition hover:bg-surface-hover hover:text-foreground"
          >
            <span>≋</span>
            EVENT STREAM
          </button>
        </div>
      </nav>

      <div className="border-t border-border px-6 py-5">
        <div className="flex items-center gap-2 text-xs text-success">
          <span>●</span>
          SYSTEM ONLINE
        </div>

        <div className="mt-2 text-[10px] tracking-wider text-muted">
          FLOWMESH v1.0.0
        </div>
      </div>
    </>
  );
}

export default function Home() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">
        {/* Desktop Sidebar */}
        <aside className="hidden w-64 shrink-0 border-r border-border bg-surface lg:flex lg:flex-col">
          <SidebarContent />
        </aside>

        {/* Mobile Menu Overlay */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <button
              aria-label="Close navigation menu"
              className="absolute inset-0 cursor-default bg-black/70"
              onClick={() => setMobileMenuOpen(false)}
            />

            <aside className="relative flex h-full w-[85%] max-w-72 flex-col border-r border-border bg-surface">
              <button
                onClick={() => setMobileMenuOpen(false)}
                aria-label="Close menu"
                className="absolute right-4 top-5 z-10 flex h-9 w-9 items-center justify-center border border-border text-lg text-muted transition hover:border-accent hover:text-accent"
              >
                ×
              </button>

              <SidebarContent onNavigate={() => setMobileMenuOpen(false)} />
            </aside>
          </div>
        )}

        {/* Main Content */}
        <section className="min-w-0 flex-1">
          {/* Mobile Top Bar */}
          <div className="flex items-center justify-between border-b border-border bg-surface px-4 py-4 lg:hidden">
            <div>
              <div className="text-base font-bold tracking-[0.2em] text-accent">
                FLOWMESH
              </div>

              <div className="mt-1 text-[9px] tracking-wider text-muted">
                DISTRIBUTED ORDER SYSTEM
              </div>
            </div>

            <button
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open navigation menu"
              className="flex h-10 w-10 flex-col items-center justify-center gap-1.5 border border-border transition hover:border-accent"
            >
              <span className="block h-px w-5 bg-foreground" />
              <span className="block h-px w-5 bg-foreground" />
              <span className="block h-px w-5 bg-foreground" />
            </button>
          </div>

          {/* Header */}
          <header className="border-b border-border bg-surface px-4 py-5 sm:px-6 lg:px-8">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="text-[10px] tracking-[0.2em] text-muted sm:text-xs">
                  OPERATIONS CONSOLE
                </div>

                <h1 className="mt-1 text-xl font-bold tracking-tight sm:text-2xl">
                  SYSTEM DASHBOARD
                </h1>
              </div>

              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div className="border border-border px-3 py-2 text-[10px] text-muted sm:px-4 sm:text-xs">
                  API GATEWAY
                  <span className="ml-2 text-success">● ONLINE</span>
                </div>

                <div className="border border-border px-3 py-2 text-[10px] text-muted sm:px-4 sm:text-xs">
                  REDIS
                  <span className="ml-2 text-success">● ONLINE</span>
                </div>
              </div>
            </div>
          </header>

          {/* Dashboard */}
          <div className="space-y-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
            {/* Intro */}
            <div className="border border-border bg-surface p-4 sm:p-6">
              <div className="flex flex-col justify-between gap-6 md:flex-row md:items-center">
                <div>
                  <div className="text-[10px] tracking-[0.2em] text-accent sm:text-xs">
                    FLOWMESH / CONTROL
                  </div>

                  <h2 className="mt-2 text-lg font-semibold sm:text-xl">
                    Order & Delivery Operations
                  </h2>

                  <p className="mt-2 max-w-2xl text-xs leading-6 text-muted sm:text-sm">
                    Monitor orders, inventory reservations, delivery workflows,
                    and distributed service events from one operations console.
                  </p>
                </div>

                <button className="w-full border border-accent bg-accent px-5 py-3 text-sm font-semibold tracking-wider text-black transition hover:bg-accent-hover md:w-auto">
                  + CREATE ORDER
                </button>
              </div>
            </div>

            {/* Stats */}
            <section>
              <div className="mb-4 flex items-end justify-between gap-4">
                <h2 className="text-xs font-semibold tracking-[0.15em] sm:text-sm">
                  SYSTEM METRICS
                </h2>

                <span className="text-right text-[9px] tracking-wider text-muted sm:text-[10px]">
                  LAST 24 HOURS
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                {stats.map((stat) => (
                  <div
                    key={stat.label}
                    className="min-w-0 border border-border bg-surface p-4 sm:p-5"
                  >
                    <div className="truncate text-[9px] tracking-[0.14em] text-muted sm:text-[10px] sm:tracking-[0.18em]">
                      {stat.label}
                    </div>

                    <div className="mt-3 text-2xl font-bold tracking-tight sm:mt-4 sm:text-3xl">
                      {stat.value}
                    </div>

                    <div className="mt-2 hidden text-[10px] tracking-wider text-muted sm:block">
                      {stat.detail}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Recent Orders */}
            <section className="border border-border bg-surface">
              <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5 sm:py-5">
                <div>
                  <h2 className="text-xs font-semibold tracking-[0.15em] sm:text-sm">
                    RECENT ORDERS
                  </h2>

                  <p className="mt-1 text-[10px] text-muted sm:text-xs">
                    Latest activity across the order pipeline.
                  </p>
                </div>

                <button className="self-start text-[10px] tracking-wider text-accent hover:text-accent-hover sm:self-auto sm:text-xs">
                  VIEW ALL →
                </button>
              </div>

              {/* Mobile Order Cards */}
              <div className="divide-y divide-border md:hidden">
                {recentOrders.map((order) => (
                  <div key={order.id} className="space-y-4 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[9px] tracking-wider text-muted">
                          ORDER ID
                        </div>

                        <div className="mt-1 text-xs">{order.id}</div>
                      </div>

                      <StatusBadge status={order.status} />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-[9px] tracking-wider text-muted">
                          PRODUCT
                        </div>

                        <div className="mt-1 text-xs">{order.product}</div>
                      </div>

                      <div>
                        <div className="mb-1 text-[9px] tracking-wider text-muted">
                          DELIVERY
                        </div>

                        <StatusBadge status={order.delivery} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table */}
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full min-w-[700px] text-left">
                  <thead>
                    <tr className="border-b border-border text-[10px] tracking-[0.15em] text-muted">
                      <th className="px-5 py-4 font-normal">ORDER ID</th>

                      <th className="px-5 py-4 font-normal">PRODUCT</th>

                      <th className="px-5 py-4 font-normal">ORDER STATUS</th>

                      <th className="px-5 py-4 font-normal">DELIVERY</th>
                    </tr>
                  </thead>

                  <tbody>
                    {recentOrders.map((order) => (
                      <tr
                        key={order.id}
                        className="border-b border-border last:border-b-0 transition hover:bg-surface-hover"
                      >
                        <td className="px-5 py-5 text-sm">{order.id}</td>

                        <td className="px-5 py-5 text-sm text-muted">
                          {order.product}
                        </td>

                        <td className="px-5 py-5">
                          <StatusBadge status={order.status} />
                        </td>

                        <td className="px-5 py-5">
                          <StatusBadge status={order.delivery} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Architecture */}
            <section>
              <div className="mb-4">
                <h2 className="text-xs font-semibold tracking-[0.15em] sm:text-sm">
                  SERVICE TOPOLOGY
                </h2>

                <p className="mt-1 text-[10px] text-muted sm:text-xs">
                  Current FlowMesh communication architecture.
                </p>
              </div>

              <div className="grid gap-3 sm:gap-4 md:grid-cols-3">
                <div className="border border-border bg-surface p-4 sm:p-5">
                  <div className="text-[10px] tracking-[0.18em] text-accent">
                    HTTP
                  </div>

                  <div className="mt-3 font-semibold">API GATEWAY</div>

                  <div className="mt-2 text-xs leading-5 text-muted">
                    FastAPI
                    <br />
                    Port 8000
                  </div>
                </div>

                <div className="border border-border bg-surface p-4 sm:p-5">
                  <div className="text-[10px] tracking-[0.18em] text-accent">
                    gRPC
                  </div>

                  <div className="mt-3 font-semibold">MICROSERVICES</div>

                  <div className="mt-2 text-xs leading-5 text-muted">
                    Order · Inventory · Delivery
                    <br />
                    Internal communication
                  </div>
                </div>

                <div className="border border-border bg-surface p-4 sm:p-5">
                  <div className="text-[10px] tracking-[0.18em] text-accent">
                    EVENTS
                  </div>

                  <div className="mt-3 font-semibold">REDIS STREAMS</div>

                  <div className="mt-2 text-xs leading-5 text-muted">
                    Transactional outbox
                    <br />
                    Event-driven workflows
                  </div>
                </div>
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
