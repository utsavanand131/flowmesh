"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

type DateRange = 7 | 14 | 30;

interface OrderOverviewResponse {
  total_orders: number;
  pending_orders: number;
  confirmed_orders: number;
  processing_orders: number;
  in_delivery: number;
  delivered_orders: number;
  completion_rate: number;
}

interface PeriodOrderOverviewResponse {
  days: number;
  total_orders: number;
  pending_orders: number;
  confirmed_orders: number;
  processing_orders: number;
  delivered_orders: number;
  completion_rate: number;
}

interface DailyOrderTrend {
  date: string;
  order_count: number;
}

interface OrderTrendsResponse {
  trends: DailyOrderTrend[];
}

interface DailyDeliveryAnalytics {
  date: string;
  created_count: number;
  delivered_count: number;
  backlog_count: number;
}

interface DeliveryAnalyticsResponse {
  days: number;
  total_created: number;
  total_delivered: number;
  average_turnaround_hours: number;
  daily_analytics: DailyDeliveryAnalytics[];
}

interface DashboardErrors {
  overview?: string;
  periodOverview?: string;
  trends?: string;
  deliveryAnalytics?: string;
}

async function apiRequest<T>(path: string, signal: AbortSignal): Promise<T> {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(`${API_URL}${path}`, {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const body = await response.json();
      message = body.detail || body.message || body.error || message;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function formatDateLabel(value: string, includeYear = false): string {
  const date = new Date(`${value}T00:00:00`);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  });
}

function StatCard({
  label,
  value,
  description,
  icon,
  accent = false,
}: {
  label: string;
  value: number | string;
  description: string;
  icon: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5 transition hover:border-accent/40">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>

        <span
          className={`flex h-9 w-9 items-center justify-center rounded-lg text-lg ${
            accent
              ? "bg-accent/10 text-accent"
              : "bg-background text-muted-foreground"
          }`}
        >
          {icon}
        </span>
      </div>

      <p
        className={`mt-4 text-3xl font-semibold tracking-tight ${
          accent ? "text-accent" : "text-foreground"
        }`}
      >
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>

      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      Loading analytics...
    </div>
  );
}

function ErrorMessage({ message }: { message?: string }) {
  if (!message) return null;

  return (
    <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
      {message}
    </div>
  );
}

export default function AnalyticsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [overview, setOverview] = useState<OrderOverviewResponse | null>(null);

  const [periodOverview, setPeriodOverview] =
    useState<PeriodOrderOverviewResponse | null>(null);

  const [trends, setTrends] = useState<DailyOrderTrend[]>([]);
  const [deliveryAnalytics, setDeliveryAnalytics] =
    useState<DeliveryAnalyticsResponse | null>(null);
  const [dateRange, setDateRange] = useState<DateRange>(7);

  const [errors, setErrors] = useState<DashboardErrors>({});
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;

    const controller = new AbortController();

    async function fetchAnalytics() {
      setLoading(true);

      const results = await Promise.allSettled([
        apiRequest<OrderOverviewResponse>(
          "/admin/orders/overview",
          controller.signal,
        ),
        apiRequest<OrderTrendsResponse>(
          `/admin/orders/trends?days=${dateRange}`,
          controller.signal,
        ),
        apiRequest<PeriodOrderOverviewResponse>(
          `/admin/orders/period-overview?days=${dateRange}`,
          controller.signal,
        ),
        apiRequest<DeliveryAnalyticsResponse>(
          `/admin/deliveries/analytics?days=${dateRange}`,
          controller.signal,
        ),
      ]);

      if (controller.signal.aborted) return;

      const nextErrors: DashboardErrors = {};

      if (results[0].status === "fulfilled") {
        setOverview(results[0].value);
      } else {
        nextErrors.overview =
          results[0].reason instanceof Error
            ? results[0].reason.message
            : "Unable to load order overview.";
      }

      if (results[1].status === "fulfilled") {
        setTrends(results[1].value.trends ?? []);
      } else {
        nextErrors.trends =
          results[1].reason instanceof Error
            ? results[1].reason.message
            : "Unable to load daily order trends.";
      }

      if (results[2].status === "fulfilled") {
        setPeriodOverview(results[2].value);
      } else {
        nextErrors.periodOverview =
          results[2].reason instanceof Error
            ? results[2].reason.message
            : "Unable to load period order overview.";
      }

      if (results[3].status === "fulfilled") {
        setDeliveryAnalytics(results[3].value);
      } else {
        nextErrors.deliveryAnalytics =
          results[3].reason instanceof Error
            ? results[3].reason.message
            : "Unable to load delivery analytics.";
      }

      setErrors(nextErrors);
      setLoading(false);
    }

    void fetchAnalytics();

    return () => controller.abort();
  }, [isAdmin, dateRange, refreshKey]);

  function handleRefresh() {
    setRefreshKey((current) => current + 1);
  }

  const busiestDay = trends.reduce<DailyOrderTrend | null>(
    (busiest, current) =>
      !busiest || current.order_count > busiest.order_count ? current : busiest,
    null,
  );

  if (!isAdmin) {
    return (
      <ProtectedRoute>
        <div className="flex min-h-screen items-center justify-center bg-background px-5">
          <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-xl text-danger">
              !
            </div>

            <h1 className="mt-4 text-xl font-semibold text-foreground">
              Admin access required
            </h1>

            <p className="mt-2 text-sm text-muted-foreground">
              Analytics is only available to FlowMesh administrators.
            </p>

            <Link
              href="/"
              className="mt-6 inline-flex rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
            >
              Return to dashboard
            </Link>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-background text-foreground">
        {mobileSidebarOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              onClick={() => setMobileSidebarOpen(false)}
              className="absolute inset-0 bg-black/60"
            />

            <div className="relative z-10 h-full w-[280px]">
              <AppSidebar
                activeItem="Analytics"
                onNavigate={() => setMobileSidebarOpen(false)}
              />
            </div>
          </div>
        )}

        <div className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:block">
          <AppSidebar activeItem="Analytics" />
        </div>

        <main className="min-h-screen lg:pl-[260px]">
          <div className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
            {/* Page header */}
            <div className="mb-7 flex items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => setMobileSidebarOpen(true)}
                  className="rounded-lg border border-border p-2 text-foreground hover:bg-surface lg:hidden"
                  aria-label="Open navigation"
                >
                  <span className="text-lg">☰</span>
                </button>

                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    Operations / Insights
                  </p>

                  <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                    Operations Analytics
                  </h1>
                </div>
              </div>

              <button
                type="button"
                onClick={handleRefresh}
                disabled={loading}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-medium text-foreground transition hover:bg-background disabled:cursor-not-allowed disabled:opacity-60 sm:px-4"
              >
                <span className={loading ? "animate-spin" : ""}>↻</span>
                <span className="hidden sm:inline">
                  {loading ? "Refreshing..." : "Refresh"}
                </span>
              </button>
            </div>

            <div className="mb-8">
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                Track order and delivery performance, monitor completion, and
                understand operational trends across FlowMesh.
              </p>
            </div>

            {/* All-time order overview */}
            <section className="mb-9">
              <div className="mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Order overview
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Current order statistics across the system.
                </p>
              </div>

              <ErrorMessage message={errors.overview} />

              {loading && !overview ? (
                <LoadingState />
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  <StatCard
                    label="Total orders"
                    value={overview?.total_orders ?? 0}
                    description="All orders created"
                    icon="▤"
                    accent
                  />

                  <StatCard
                    label="Pending"
                    value={overview?.pending_orders ?? 0}
                    description="Awaiting confirmation"
                    icon="◷"
                  />

                  <StatCard
                    label="Confirmed"
                    value={overview?.confirmed_orders ?? 0}
                    description="Orders confirmed"
                    icon="✓"
                  />

                  <StatCard
                    label="Processing"
                    value={overview?.processing_orders ?? 0}
                    description="Orders being prepared"
                    icon="⟳"
                  />

                  <StatCard
                    label="Delivered"
                    value={overview?.delivered_orders ?? 0}
                    description="Successfully delivered"
                    icon="↗"
                  />

                  <StatCard
                    label="Completion rate"
                    value={`${(overview?.completion_rate ?? 0).toFixed(2)}%`}
                    description="Delivered orders / total orders"
                    icon="%"
                    accent
                  />
                </div>
              )}
            </section>

            {/* Period overview */}
            <section className="mb-9">
              <div className="mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Period overview
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Order statistics for the last {dateRange} days. Counts are
                  based on orders created during this period.
                </p>
              </div>

              <ErrorMessage message={errors.periodOverview} />

              {loading && !periodOverview ? (
                <LoadingState />
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  <StatCard
                    label="Orders created"
                    value={periodOverview?.total_orders ?? 0}
                    description={`Created in the last ${dateRange} days`}
                    icon="▤"
                    accent
                  />

                  <StatCard
                    label="Pending"
                    value={periodOverview?.pending_orders ?? 0}
                    description="Currently awaiting confirmation"
                    icon="◷"
                  />

                  <StatCard
                    label="Confirmed"
                    value={periodOverview?.confirmed_orders ?? 0}
                    description="Currently confirmed"
                    icon="✓"
                  />

                  <StatCard
                    label="Processing"
                    value={periodOverview?.processing_orders ?? 0}
                    description="Currently being prepared"
                    icon="⟳"
                  />

                  <StatCard
                    label="Delivered"
                    value={periodOverview?.delivered_orders ?? 0}
                    description="Successfully delivered"
                    icon="↗"
                  />

                  <StatCard
                    label="Completion rate"
                    value={`${(periodOverview?.completion_rate ?? 0).toFixed(2)}%`}
                    description="Delivered orders / orders created in period"
                    icon="%"
                    accent
                  />
                </div>
              )}
            </section>

            {/* Daily order trends */}
            <section className="mb-9">
              <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    Daily order trends
                  </h2>

                  <p className="mt-1 text-sm text-muted-foreground">
                    Number of orders created per day.
                  </p>
                </div>

                <label className="flex items-center gap-3 text-sm text-muted-foreground">
                  <span>Date range</span>

                  <select
                    value={dateRange}
                    onChange={(event) =>
                      setDateRange(Number(event.target.value) as DateRange)
                    }
                    className="rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-accent"
                  >
                    <option value={7}>Last 7 days</option>
                    <option value={14}>Last 14 days</option>
                    <option value={30}>Last 30 days</option>
                  </select>
                </label>
              </div>

              <ErrorMessage message={errors.trends} />

              <div className="rounded-xl border border-border bg-surface p-4 sm:p-6">
                {loading && trends.length === 0 ? (
                  <LoadingState />
                ) : trends.length === 0 ? (
                  <div className="flex min-h-[320px] items-center justify-center text-center">
                    <div>
                      <p className="font-medium text-foreground">
                        No order trend data available
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Daily order activity will appear here when data is
                        available.
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          Orders over time
                        </p>

                        <p className="mt-1 text-xs text-muted-foreground">
                          Showing {trends.length} daily data points
                        </p>

                        {busiestDay && busiestDay.order_count > 0 && (
                          <p className="mt-2 text-xs text-accent">
                            Busiest day:{" "}
                            <span className="font-semibold">
                              {formatDateLabel(busiestDay.date, true)}
                            </span>
                            {" · "}
                            {busiestDay.order_count} orders
                          </p>
                        )}
                      </div>

                      <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="h-2.5 w-2.5 rounded-full bg-accent" />
                        Orders
                      </span>
                    </div>

                    <div className="h-[320px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={trends}
                          margin={{
                            top: 10,
                            right: 12,
                            left: -18,
                            bottom: 5,
                          }}
                        >
                          <CartesianGrid
                            stroke="#292e34"
                            strokeDasharray="4 4"
                            vertical={false}
                          />

                          <XAxis
                            dataKey="date"
                            tickFormatter={(value) =>
                              formatDateLabel(String(value))
                            }
                            tick={{
                              fill: "#858d97",
                              fontSize: 11,
                            }}
                            axisLine={{ stroke: "#292e34" }}
                            tickLine={false}
                            minTickGap={20}
                          />

                          <YAxis
                            allowDecimals={false}
                            tick={{
                              fill: "#858d97",
                              fontSize: 11,
                            }}
                            axisLine={false}
                            tickLine={false}
                            width={45}
                          />

                          <Tooltip
                            contentStyle={{
                              backgroundColor: "#171a1e",
                              border: "1px solid #292e34",
                              borderRadius: "10px",
                              color: "#e6e8eb",
                              fontSize: "12px",
                            }}
                            labelStyle={{
                              color: "#a5acb5",
                              marginBottom: "4px",
                            }}
                            formatter={(value) => [
                              Number(value).toLocaleString(),
                              "Orders",
                            ]}
                            labelFormatter={(label) =>
                              formatDateLabel(String(label), true)
                            }
                            cursor={{
                              stroke: "#6ba6a0",
                              strokeDasharray: "4 4",
                            }}
                          />

                          <Line
                            type="monotone"
                            dataKey="order_count"
                            name="Orders"
                            stroke="#6ba6a0"
                            strokeWidth={2.5}
                            dot={{
                              r: 3,
                              fill: "#6ba6a0",
                              stroke: "#171a1e",
                              strokeWidth: 2,
                            }}
                            activeDot={{
                              r: 6,
                              fill: "#83b9b2",
                              stroke: "#171a1e",
                              strokeWidth: 2,
                            }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </>
                )}
              </div>
            </section>

            {/* Delivery analytics */}
            <section className="mb-9">
              <div className="mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Delivery analytics
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Historical delivery activity for the last {dateRange} days.
                  These insights complement the current delivery status metrics
                  on the Deliveries page.
                </p>
              </div>

              <ErrorMessage message={errors.deliveryAnalytics} />

              {loading && !deliveryAnalytics ? (
                <LoadingState />
              ) : deliveryAnalytics ? (
                <>
                  <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    <StatCard
                      label="Deliveries created"
                      value={deliveryAnalytics.total_created}
                      description={`Created in the last ${dateRange} days`}
                      icon="▤"
                      accent
                    />

                    <StatCard
                      label="Deliveries completed"
                      value={deliveryAnalytics.total_delivered}
                      description="Moved to DELIVERED during this period"
                      icon="✓"
                    />

                    <StatCard
                      label="Average turnaround"
                      value={
                        deliveryAnalytics.average_turnaround_hours > 0
                          ? `${deliveryAnalytics.average_turnaround_hours.toFixed(1)}h`
                          : "—"
                      }
                      description="Based on recorded assignment and delivery timestamps"
                      icon="◷"
                    />
                  </div>

                  <div className="rounded-xl border border-border bg-surface p-4 sm:p-6">
                    {deliveryAnalytics.daily_analytics.length === 0 ? (
                      <div className="flex min-h-[320px] items-center justify-center text-center">
                        <div>
                          <p className="font-medium text-foreground">
                            No delivery trend data available
                          </p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Daily delivery activity will appear here when data
                            is available.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="mb-5">
                          <p className="text-sm font-medium text-foreground">
                            Delivery activity and backlog
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Daily deliveries created, completed, and remaining
                            from deliveries created during this period.
                          </p>
                        </div>

                        <div className="mb-5 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
                          <span className="inline-flex items-center gap-2">
                            <span className="h-2.5 w-2.5 rounded-full bg-[#6ba6a0]" />
                            Created
                          </span>
                          <span className="inline-flex items-center gap-2">
                            <span className="h-2.5 w-2.5 rounded-full bg-[#8b9bd7]" />
                            Delivered
                          </span>
                          <span className="inline-flex items-center gap-2">
                            <span className="h-2.5 w-2.5 rounded-full bg-[#d6a85f]" />
                            Period backlog
                          </span>
                        </div>

                        <div className="h-[340px] w-full">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                              data={deliveryAnalytics.daily_analytics}
                              margin={{
                                top: 10,
                                right: 12,
                                left: -18,
                                bottom: 5,
                              }}
                            >
                              <CartesianGrid
                                stroke="#292e34"
                                strokeDasharray="4 4"
                                vertical={false}
                              />

                              <XAxis
                                dataKey="date"
                                tickFormatter={(value) =>
                                  formatDateLabel(String(value))
                                }
                                tick={{ fill: "#858d97", fontSize: 11 }}
                                axisLine={{ stroke: "#292e34" }}
                                tickLine={false}
                                minTickGap={20}
                              />

                              <YAxis
                                allowDecimals={false}
                                tick={{ fill: "#858d97", fontSize: 11 }}
                                axisLine={false}
                                tickLine={false}
                                width={45}
                              />

                              <Tooltip
                                contentStyle={{
                                  backgroundColor: "#171a1e",
                                  border: "1px solid #292e34",
                                  borderRadius: "10px",
                                  color: "#e6e8eb",
                                  fontSize: "12px",
                                }}
                                labelStyle={{
                                  color: "#a5acb5",
                                  marginBottom: "4px",
                                }}
                                formatter={(value, name) => [
                                  Number(value).toLocaleString(),
                                  String(name),
                                ]}
                                labelFormatter={(label) =>
                                  formatDateLabel(String(label), true)
                                }
                                cursor={{
                                  stroke: "#6ba6a0",
                                  strokeDasharray: "4 4",
                                }}
                              />

                              <Line
                                type="monotone"
                                dataKey="created_count"
                                name="Created"
                                stroke="#6ba6a0"
                                strokeWidth={2.5}
                                dot={{
                                  r: 3,
                                  fill: "#6ba6a0",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                                activeDot={{
                                  r: 6,
                                  fill: "#83b9b2",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                              />

                              <Line
                                type="monotone"
                                dataKey="delivered_count"
                                name="Delivered"
                                stroke="#8b9bd7"
                                strokeWidth={2.5}
                                dot={{
                                  r: 3,
                                  fill: "#8b9bd7",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                                activeDot={{
                                  r: 6,
                                  fill: "#aab6e8",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                              />

                              <Line
                                type="monotone"
                                dataKey="backlog_count"
                                name="Period backlog"
                                stroke="#d6a85f"
                                strokeWidth={2.5}
                                dot={{
                                  r: 3,
                                  fill: "#d6a85f",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                                activeDot={{
                                  r: 6,
                                  fill: "#e5bd7d",
                                  stroke: "#171a1e",
                                  strokeWidth: 2,
                                }}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>

                        <p className="mt-4 text-xs leading-5 text-muted-foreground">
                          Backlog represents deliveries created within the
                          selected period that had not yet been completed by
                          each date. Average turnaround excludes deliveries
                          without recorded assignment and delivery timestamps.
                        </p>
                      </>
                    )}
                  </div>
                </>
              ) : (
                <div className="rounded-xl border border-border bg-surface p-6 text-sm text-muted-foreground">
                  Delivery analytics are currently unavailable.
                </div>
              )}
            </section>

            <footer className="border-t border-border py-5 text-xs text-muted-foreground">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p>FlowMesh Operations Analytics</p>
                <p>Reporting period: Last {dateRange} days</p>
              </div>
            </footer>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
}
