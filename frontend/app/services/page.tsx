"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface ServicesHealthResponse {
  status: "healthy" | "degraded";
  services: Record<string, "healthy" | "unhealthy">;
  checked_at: string;
}

interface ServiceDefinition {
  key: string;
  name: string;
  description: string;
  type: string;
  port: string;
}

const serviceDefinitions: ServiceDefinition[] = [
  {
    key: "api_gateway",
    name: "API Gateway",
    description: "Main entry point for client requests and API routing.",
    type: "HTTP",
    port: ":8000",
  },
  {
    key: "order_service",
    name: "Order Service",
    description: "Handles order creation and order management.",
    type: "gRPC",
    port: ":50051",
  },
  {
    key: "inventory_service",
    name: "Inventory Service",
    description: "Manages product inventory and stock availability.",
    type: "gRPC",
    port: ":50052",
  },
  {
    key: "delivery_service",
    name: "Delivery Service",
    description: "Manages delivery assignments and delivery status.",
    type: "gRPC",
    port: ":50053",
  },
  {
    key: "postgresql",
    name: "PostgreSQL",
    description: "Persistent storage for orders and application data.",
    type: "Database",
    port: ":5432",
  },
  {
    key: "redis",
    name: "Redis",
    description: "Supports event streams, worker metrics, and messaging.",
    type: "Infrastructure",
    port: ":6379",
  },
];

function StatusBadge({ status }: { status?: string }) {
  const normalizedStatus = status?.toLowerCase();

  const styles =
    normalizedStatus === "healthy"
      ? "border-success/20 bg-success/10 text-success"
      : normalizedStatus === "unhealthy"
        ? "border-danger/20 bg-danger/10 text-danger"
        : "border-border bg-surface-muted text-muted-foreground";

  const label =
    normalizedStatus === "healthy"
      ? "Healthy"
      : normalizedStatus === "unhealthy"
        ? "Unhealthy"
        : "Unknown";

  return (
    <span
      className={`inline-flex items-center gap-2 whitespace-nowrap rounded-md border px-2.5 py-1 text-xs font-medium ${styles}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          normalizedStatus === "healthy"
            ? "bg-success"
            : normalizedStatus === "unhealthy"
              ? "bg-danger"
              : "bg-muted"
        }`}
      />
      {label}
    </span>
  );
}

function formatCheckedAt(value: string | null) {
  if (!value) return "Not checked yet";

  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

export default function ServicesPage() {
  const { user } = useAuth();

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [services, setServices] = useState<Record<string, string>>({});
  const [overallStatus, setOverallStatus] = useState("");
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const isAdmin = user?.role === "ADMIN";

  const fetchServicesHealth = useCallback(async (signal: AbortSignal) => {
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
      const response = await fetch(`${API_URL}/admin/services/health`, {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json",
        },
        signal,
      });

      if (!response.ok) {
        let message = "Unable to retrieve service health.";

        try {
          const data = await response.json();

          if (response.status === 403) {
            message =
              "You need an administrator account to access service monitoring.";
          } else {
            message = data.detail || data.message || message;
          }
        } catch {
          // Keep the default error message.
        }

        throw new Error(message);
      }

      const data: ServicesHealthResponse = await response.json();

      setServices(data.services ?? {});
      setOverallStatus(data.status ?? "degraded");
      setCheckedAt(data.checked_at ?? null);
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
    if (!isAdmin) return;

    const controller = new AbortController();

    fetchServicesHealth(controller.signal);

    return () => controller.abort();
  }, [fetchServicesHealth, refreshKey, isAdmin]);

  const healthyCount = Object.values(services).filter(
    (status) => status === "healthy",
  ).length;

  const unhealthyCount = Object.values(services).filter(
    (status) => status === "unhealthy",
  ).length;

  const overallLabel =
    overallStatus === "healthy"
      ? "All systems operational"
      : overallStatus === "degraded"
        ? "System experiencing issues"
        : "Awaiting health check";

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
                Service monitoring is available to FlowMesh administrators only.
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
              <AppSidebar activeItem="Services" />
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
                    activeItem="Services"
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
                  <p className="text-xs text-muted">System</p>
                  <h1 className="mt-0.5 text-lg font-semibold tracking-tight sm:text-xl">
                    Services
                  </h1>
                </div>
              </header>

              {/* Services Content */}
              <div className="mx-auto max-w-[1600px] space-y-8 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
                {/* Page Introduction */}
                <section className="flex flex-col justify-between gap-4 border-b border-border pb-7 sm:flex-row sm:items-end">
                  <div>
                    <p className="text-sm font-medium text-accent">
                      FlowMesh / System
                    </p>

                    <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
                      Service Monitoring
                    </h2>

                    <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                      Monitor the availability of FlowMesh services and
                      infrastructure dependencies from one place.
                    </p>
                  </div>

                  <button
                    onClick={() => setRefreshKey((current) => current + 1)}
                    disabled={loading}
                    className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md border border-border bg-surface px-4 text-sm font-medium text-foreground transition hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span>{loading ? "Checking..." : "↻ Refresh"}</span>
                  </button>
                </section>

                {/* Overall System Status */}
                <section className="rounded-lg border border-border bg-surface p-5 sm:p-6">
                  <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">
                        Overall System Health
                      </p>

                      <div className="mt-2 flex flex-wrap items-center gap-3">
                        <span
                          className={`h-3 w-3 rounded-full ${
                            overallStatus === "healthy"
                              ? "bg-success"
                              : overallStatus === "degraded"
                                ? "bg-warning"
                                : "bg-muted"
                          }`}
                        />

                        <h3 className="text-xl font-semibold tracking-tight">
                          {loading && !overallStatus
                            ? "Checking services..."
                            : overallLabel}
                        </h3>
                      </div>

                      <p className="mt-2 text-xs text-muted-foreground">
                        Last checked: {formatCheckedAt(checkedAt)}
                      </p>
                    </div>

                    <div className="grid grid-cols-3 gap-5 sm:gap-8">
                      <div>
                        <p className="text-xs text-muted-foreground">Total</p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums">
                          {loading && !Object.keys(services).length
                            ? "—"
                            : serviceDefinitions.length}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground">Healthy</p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums text-success">
                          {loading && !Object.keys(services).length
                            ? "—"
                            : healthyCount}
                        </p>
                      </div>

                      <div>
                        <p className="text-xs text-muted-foreground">
                          Unhealthy
                        </p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums text-danger">
                          {loading && !Object.keys(services).length
                            ? "—"
                            : unhealthyCount}
                        </p>
                      </div>
                    </div>
                  </div>
                </section>

                {/* Error Message */}
                {error && (
                  <div className="rounded-lg border border-danger/20 bg-danger/10 p-4">
                    <p className="text-sm font-medium text-danger">
                      Unable to retrieve service health
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

                {/* Service Cards */}
                <section>
                  <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-base font-semibold">
                        Infrastructure Components
                      </h3>

                      <p className="mt-1 text-xs text-muted-foreground">
                        Individual connectivity and availability checks
                      </p>
                    </div>

                    <span className="text-xs text-muted-foreground">
                      {loading ? "Updating statuses..." : "Live check results"}
                    </span>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {serviceDefinitions.map((service) => {
                      const status = services[service.key];

                      return (
                        <article
                          key={service.key}
                          className="rounded-lg border border-border bg-surface p-5 transition hover:border-accent/30"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h4 className="text-sm font-semibold">
                                {service.name}
                              </h4>

                              <p className="mt-1 text-xs text-muted-foreground">
                                {service.type} · {service.port}
                              </p>
                            </div>

                            <StatusBadge status={status} />
                          </div>

                          <p className="mt-5 min-h-10 text-sm leading-5 text-muted-foreground">
                            {service.description}
                          </p>

                          <div className="mt-4 flex items-center justify-between border-t border-border pt-3">
                            <span className="text-xs text-muted">
                              Component status
                            </span>

                            <span className="text-xs font-medium text-foreground">
                              {status
                                ? status === "healthy"
                                  ? "Operational"
                                  : "Unavailable"
                                : "Not checked"}
                            </span>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>

                {/* Monitoring Information */}
                <section className="rounded-lg border border-border bg-surface p-5">
                  <h3 className="text-sm font-semibold">
                    Monitoring Information
                  </h3>

                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    Health checks are performed by the FlowMesh API Gateway.
                    gRPC services are checked for channel connectivity,
                    PostgreSQL is checked with a database query, and Redis is
                    checked using its PING command.
                  </p>

                  <p className="mt-3 text-xs text-muted">
                    Statuses update whenever you refresh this page.
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
