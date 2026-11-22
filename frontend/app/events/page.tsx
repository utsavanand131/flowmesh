"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import AppSidebar from "@/components/AppSidebar";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const PAGE_SIZE = 10;

type StreamName = "order" | "delivery" | "dead_letter";

interface MetricData {
  events_processed_total: number;
  events_failed_total: number;
  events_retried_total: number;
  events_dead_lettered_total: number;
  events_recovered_total: number;
  events_ack_failed_total: number;
  events_ack_zero_total: number;
  events_ack_exception_total: number;
}

interface StreamSummary {
  stream_key: string;
  length: number;
  exists?: boolean;
  first_entry?: {
    message_id: string;
    fields: Record<string, unknown>;
  } | null;
  last_entry?: {
    message_id: string;
    fields: Record<string, unknown>;
  } | null;
  groups?: number;
}

interface OverviewResponse {
  metrics: MetricData;
  streams: {
    order: StreamSummary;
    delivery: StreamSummary;
    dead_letter: StreamSummary;
  };
  current_state: {
    total_stream_entries: number;
    total_pending_messages: number;
  };
  metric_note?: string;
  checked_at?: string;
}

interface StreamsResponse {
  streams: {
    order: StreamSummary;
    delivery: StreamSummary;
    dead_letter: StreamSummary;
  };
  checked_at?: string;
}

interface ActivityEvent {
  stream_key: string;
  stream: string;
  message_id: string;
  event_id?: string;
  event_type?: string;
  order_id?: string;
  timestamp_ms?: number;
  fields?: Record<string, unknown>;
}

interface ActivityResponse {
  events: ActivityEvent[];
  total: number;
  page: number;
  page_size: number;
  scanned_limit_per_stream?: number;
  has_more: boolean;
  note?: string;
}

interface ConsumerInfo {
  name: string;
  pending_count: number;
  idle_ms: number;
}

interface ConsumerGroup {
  stream: string;
  group: string;
  consumers_count: number;
  pending_count: number;
  last_delivered_id: string;
  entries_read?: number | null;
  lag?: number | null;
  consumers: ConsumerInfo[];
}

interface ConsumerGroupsResponse {
  consumer_groups: ConsumerGroup[];
  total_groups: number;
  total_pending_messages: number;
  checked_at?: string;
}

interface DeadLetter {
  dead_letter_message_id: string;
  original_stream?: string;
  original_group?: string;
  original_message_id?: string;
  event_id?: string;
  event_type?: string;
  attempts?: string | number;
  error?: string;
  original_fields?: Record<string, unknown>;
  dead_lettered_at?: string;
}

interface DeadLettersResponse {
  dead_letters: DeadLetter[];
  total: number;
  matching_scanned: number;
  page: number;
  page_size: number;
  has_more: boolean;
  scan_limit: number;
  scan_truncated: boolean;
  checked_at?: string;
}

interface DashboardError {
  overview?: string;
  streams?: string;
  activity?: string;
  groups?: string;
  deadLetters?: string;
}

async function apiRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
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

function formatDate(value?: string | number | null): string {
  if (value === undefined || value === null || value === "") {
    return "—";
  }

  const date = typeof value === "number" ? new Date(value) : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return String(value);
  }

  return date.toLocaleString();
}

function formatTimestampMs(value?: number): string {
  if (!value) return "—";
  return formatDate(value);
}

function formatDuration(value?: number): string {
  if (value === undefined || value === null) return "—";

  if (value < 1000) return `${value} ms`;

  const seconds = Math.floor(value / 1000);

  if (seconds < 60) return `${seconds}s`;

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  if (minutes < 60) {
    return remainingSeconds
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function shortId(value?: string, length = 18): string {
  if (!value) return "—";
  if (value.length <= length) return value;
  return `${value.slice(0, length)}…`;
}

function getStreamLabel(stream?: string): string {
  if (!stream) return "Unknown";

  if (stream === "order" || stream.includes("order-events")) {
    return "Order";
  }

  if (stream === "delivery" || stream.includes("delivery-events")) {
    return "Delivery";
  }

  if (stream === "dead_letter" || stream.includes("dead-letter")) {
    return "Dead Letter";
  }

  return stream;
}

function getEventBadgeClass(eventType?: string): string {
  if (!eventType) {
    return "border-border bg-surface text-muted-foreground";
  }

  if (eventType.includes("failed") || eventType.includes("error")) {
    return "border-danger/30 bg-danger/10 text-danger";
  }

  if (eventType.includes("delivered") || eventType.includes("completed")) {
    return "border-success/30 bg-success/10 text-success";
  }

  return "border-accent/30 bg-accent/10 text-accent";
}

function StatCard({
  label,
  value,
  description,
}: {
  label: string;
  value: number | string;
  description?: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
        {value.toLocaleString()}
      </p>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      )}
    </div>
  );
}

function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border px-5 py-10 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
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

function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-sm text-muted-foreground">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      Loading event data…
    </div>
  );
}

function Pagination({
  page,
  hasMore,
  onPrevious,
  onNext,
}: {
  page: number;
  hasMore: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="mt-5 flex items-center justify-between border-t border-border pt-4">
      <p className="text-sm text-muted-foreground">Page {page}</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onPrevious}
          disabled={page <= 1}
          className="rounded-lg border border-border px-3 py-2 text-sm text-foreground transition hover:bg-background disabled:cursor-not-allowed disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!hasMore}
          className="rounded-lg border border-border px-3 py-2 text-sm text-foreground transition hover:bg-background disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}

export default function EventsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [streams, setStreams] = useState<StreamsResponse | null>(null);
  const [consumerGroups, setConsumerGroups] =
    useState<ConsumerGroupsResponse | null>(null);
  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [deadLetters, setDeadLetters] = useState<DeadLettersResponse | null>(
    null,
  );

  const [errors, setErrors] = useState<DashboardError>({});
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingActivity, setLoadingActivity] = useState(true);
  const [loadingDeadLetters, setLoadingDeadLetters] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const [activityPage, setActivityPage] = useState(1);
  const [activityStreamDraft, setActivityStreamDraft] = useState("all");
  const [activityTypeDraft, setActivityTypeDraft] = useState("");
  const [activityOrderDraft, setActivityOrderDraft] = useState("");
  const [activityFilters, setActivityFilters] = useState({
    stream: "all",
    eventType: "",
    orderId: "",
  });

  const [deadLetterPage, setDeadLetterPage] = useState(1);
  const [deadLetterStreamDraft, setDeadLetterStreamDraft] = useState("all");
  const [deadLetterTypeDraft, setDeadLetterTypeDraft] = useState("");
  const [deadLetterFilters, setDeadLetterFilters] = useState({
    stream: "all",
    eventType: "",
  });

  const [expandedDeadLetter, setExpandedDeadLetter] = useState<string | null>(
    null,
  );

  const fetchSummary = useCallback(async (signal: AbortSignal) => {
    setLoadingSummary(true);

    const results = await Promise.allSettled([
      apiRequest<OverviewResponse>("/admin/events/overview", signal),
      apiRequest<StreamsResponse>("/admin/events/streams", signal),
      apiRequest<ConsumerGroupsResponse>(
        "/admin/events/consumer-groups",
        signal,
      ),
    ]);

    if (signal.aborted) return;

    const nextErrors: DashboardError = {};

    if (results[0].status === "fulfilled") {
      setOverview(results[0].value);
    } else {
      nextErrors.overview =
        results[0].reason?.message || "Unable to load overview.";
    }

    if (results[1].status === "fulfilled") {
      setStreams(results[1].value);
    } else {
      nextErrors.streams =
        results[1].reason?.message || "Unable to load streams.";
    }

    if (results[2].status === "fulfilled") {
      setConsumerGroups(results[2].value);
    } else {
      nextErrors.groups =
        results[2].reason?.message || "Unable to load consumer groups.";
    }

    setErrors((previous) => ({
      ...previous,
      overview: nextErrors.overview,
      streams: nextErrors.streams,
      groups: nextErrors.groups,
    }));

    setLoadingSummary(false);
    setRefreshing(false);
  }, []);

  const fetchActivity = useCallback(
    async (signal: AbortSignal) => {
      setLoadingActivity(true);

      const params = new URLSearchParams({
        page: String(activityPage),
        page_size: String(PAGE_SIZE),
      });

      if (activityFilters.stream !== "all") {
        params.set("stream", activityFilters.stream);
      }

      if (activityFilters.eventType.trim()) {
        params.set("event_type", activityFilters.eventType.trim());
      }

      if (activityFilters.orderId.trim()) {
        params.set("order_id", activityFilters.orderId.trim());
      }

      try {
        const result = await apiRequest<ActivityResponse>(
          `/admin/events/activity?${params.toString()}`,
          signal,
        );

        if (signal.aborted) return;

        setActivity(result);
        setErrors((previous) => ({ ...previous, activity: undefined }));
      } catch (error) {
        if (signal.aborted) return;

        setErrors((previous) => ({
          ...previous,
          activity:
            error instanceof Error ? error.message : "Unable to load activity.",
        }));
      } finally {
        if (!signal.aborted) setLoadingActivity(false);
      }
    },
    [activityFilters, activityPage],
  );

  const fetchDeadLetters = useCallback(
    async (signal: AbortSignal) => {
      setLoadingDeadLetters(true);

      const params = new URLSearchParams({
        page: String(deadLetterPage),
        page_size: String(PAGE_SIZE),
      });

      if (deadLetterFilters.stream !== "all") {
        params.set("original_stream", deadLetterFilters.stream);
      }

      if (deadLetterFilters.eventType.trim()) {
        params.set("event_type", deadLetterFilters.eventType.trim());
      }

      try {
        const result = await apiRequest<DeadLettersResponse>(
          `/admin/events/dead-letters?${params.toString()}`,
          signal,
        );

        if (signal.aborted) return;

        setDeadLetters(result);
        setErrors((previous) => ({ ...previous, deadLetters: undefined }));
      } catch (error) {
        if (signal.aborted) return;

        setErrors((previous) => ({
          ...previous,
          deadLetters:
            error instanceof Error
              ? error.message
              : "Unable to load dead letters.",
        }));
      } finally {
        if (!signal.aborted) setLoadingDeadLetters(false);
      }
    },
    [deadLetterFilters, deadLetterPage],
  );

  useEffect(() => {
    if (!isAdmin) return;

    const controller = new AbortController();
    void fetchSummary(controller.signal);

    return () => controller.abort();
  }, [fetchSummary, isAdmin, refreshKey]);

  useEffect(() => {
    if (!isAdmin) return;

    const controller = new AbortController();
    void fetchActivity(controller.signal);

    return () => controller.abort();
  }, [fetchActivity, isAdmin, refreshKey]);

  useEffect(() => {
    if (!isAdmin) return;

    const controller = new AbortController();
    void fetchDeadLetters(controller.signal);

    return () => controller.abort();
  }, [fetchDeadLetters, isAdmin, refreshKey]);

  function handleRefresh() {
    setRefreshing(true);
    setRefreshKey((current) => current + 1);
  }

  function handleActivityFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setActivityPage(1);
    setActivityFilters({
      stream: activityStreamDraft,
      eventType: activityTypeDraft,
      orderId: activityOrderDraft,
    });
  }

  function handleDeadLetterFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setDeadLetterPage(1);
    setExpandedDeadLetter(null);
    setDeadLetterFilters({
      stream: deadLetterStreamDraft,
      eventType: deadLetterTypeDraft,
    });
  }

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
              Event Streams is only available to FlowMesh administrators.
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

  const metrics = overview?.metrics;

  const streamCards = [
    {
      key: "order",
      title: "Order Events",
      description: "Order lifecycle events",
      data: streams?.streams.order || overview?.streams.order,
    },
    {
      key: "delivery",
      title: "Delivery Events",
      description: "Delivery lifecycle events",
      data: streams?.streams.delivery || overview?.streams.delivery,
    },
    {
      key: "dead_letter",
      title: "Dead Letter Events",
      description: "Events moved to the dead-letter stream",
      data: streams?.streams.dead_letter || overview?.streams.dead_letter,
    },
  ];

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
                activeItem="Event Streams"
                onNavigate={() => setMobileSidebarOpen(false)}
              />
            </div>
          </div>
        )}

        <div className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:block">
          <AppSidebar activeItem="Event Streams" />
        </div>

        <main className="min-h-screen lg:pl-[260px]">
          <div className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
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
                    System / Monitoring
                  </p>
                  <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                    Event Streams
                  </h1>
                </div>
              </div>

              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshing}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-medium text-foreground transition hover:bg-background disabled:cursor-not-allowed disabled:opacity-60 sm:px-4"
              >
                <span className={refreshing ? "animate-spin" : ""}>↻</span>
                <span className="hidden sm:inline">
                  {refreshing ? "Refreshing…" : "Refresh"}
                </span>
              </button>
            </div>

            <div className="mb-7">
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
                Monitor event activity, Redis stream entries, worker consumer
                groups, and events that have been moved to the dead-letter
                stream.
              </p>
            </div>

            {/* Overview metrics */}
            <section className="mb-8">
              <SectionHeader
                title="Worker metrics"
                description="Cumulative counters reported by the event workers."
              />

              <ErrorMessage message={errors.overview} />

              {loadingSummary && !overview ? (
                <LoadingState />
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <StatCard
                    label="Events processed"
                    value={metrics?.events_processed_total ?? 0}
                    description="Successful processing count"
                  />
                  <StatCard
                    label="Failed attempts"
                    value={metrics?.events_failed_total ?? 0}
                    description="Processing failures recorded"
                  />
                  <StatCard
                    label="Retries"
                    value={metrics?.events_retried_total ?? 0}
                    description="Retry attempts recorded"
                  />
                  <StatCard
                    label="Recovered"
                    value={metrics?.events_recovered_total ?? 0}
                    description="Pending events recovered"
                  />
                  <StatCard
                    label="Dead-lettered"
                    value={metrics?.events_dead_lettered_total ?? 0}
                    description="Events moved to dead-letter stream"
                  />
                  <StatCard
                    label="Ack failures"
                    value={metrics?.events_ack_failed_total ?? 0}
                    description="Acknowledgement failures"
                  />
                  <StatCard
                    label="Zero acknowledgements"
                    value={metrics?.events_ack_zero_total ?? 0}
                    description="Acknowledgements returning zero"
                  />
                  <StatCard
                    label="Ack exceptions"
                    value={metrics?.events_ack_exception_total ?? 0}
                    description="Acknowledgement exceptions"
                  />
                </div>
              )}

              {overview?.metric_note && (
                <p className="mt-3 rounded-lg border border-border bg-surface px-4 py-3 text-xs leading-5 text-muted-foreground">
                  {overview.metric_note}
                </p>
              )}
            </section>

            {/* Stream summaries */}
            <section className="mb-8">
              <SectionHeader
                title="Redis streams"
                description="Current stream lengths and metadata."
              />

              <ErrorMessage message={errors.streams} />

              {loadingSummary && !streams && !overview ? (
                <LoadingState />
              ) : (
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                  {streamCards.map((stream) => (
                    <div
                      key={stream.key}
                      className="rounded-xl border border-border bg-surface p-5"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="font-semibold text-foreground">
                            {stream.title}
                          </h3>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {stream.description}
                          </p>
                        </div>
                        <span className="rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground">
                          {stream.data?.exists === false
                            ? "Not created"
                            : "Stream"}
                        </span>
                      </div>

                      <p className="mt-5 text-3xl font-semibold tracking-tight text-foreground">
                        {(stream.data?.length ?? 0).toLocaleString()}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Total entries in stream
                      </p>

                      <div className="mt-5 space-y-3 border-t border-border pt-4 text-xs">
                        <div className="flex justify-between gap-3">
                          <span className="text-muted-foreground">
                            Stream key
                          </span>
                          <span className="max-w-[65%] break-all text-right font-mono text-foreground">
                            {stream.data?.stream_key || "—"}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span className="text-muted-foreground">
                            Consumer groups
                          </span>
                          <span className="font-medium text-foreground">
                            {stream.data?.groups ?? 0}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span className="text-muted-foreground">
                            First entry
                          </span>
                          <span className="font-mono text-foreground">
                            {shortId(stream.data?.first_entry?.message_id, 20)}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span className="text-muted-foreground">
                            Latest entry
                          </span>
                          <span className="font-mono text-foreground">
                            {shortId(stream.data?.last_entry?.message_id, 20)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-3 rounded-lg border border-border bg-surface px-4 py-3 text-xs leading-5 text-muted-foreground">
                Stream length counts entries retained in Redis, including
                entries that workers may already have acknowledged. It should
                not be interpreted as the number of unprocessed events.
              </div>
            </section>

            {/* Current state */}
            <section className="mb-8">
              <SectionHeader
                title="Current stream state"
                description="Snapshot totals from the Redis stream overview and consumer groups."
              />

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <StatCard
                  label="Total stream entries"
                  value={overview?.current_state.total_stream_entries ?? 0}
                  description="Entries across the monitored streams"
                />
                <StatCard
                  label="Pending messages"
                  value={
                    consumerGroups?.total_pending_messages ??
                    overview?.current_state.total_pending_messages ??
                    0
                  }
                  description="Messages currently pending acknowledgement"
                />
              </div>
            </section>

            {/* Consumer groups */}
            <section className="mb-8">
              <SectionHeader
                title="Consumer groups"
                description="Worker groups, consumer counts, and pending message counts."
              />

              <ErrorMessage message={errors.groups} />

              {loadingSummary && !consumerGroups ? (
                <LoadingState />
              ) : consumerGroups?.consumer_groups.length ? (
                <div className="overflow-hidden rounded-xl border border-border bg-surface">
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[850px] text-left text-sm">
                      <thead className="border-b border-border bg-background/70 text-xs uppercase tracking-wide text-muted-foreground">
                        <tr>
                          <th className="px-5 py-4 font-medium">Stream</th>
                          <th className="px-5 py-4 font-medium">Group</th>
                          <th className="px-5 py-4 font-medium">Consumers</th>
                          <th className="px-5 py-4 font-medium">Pending</th>
                          <th className="px-5 py-4 font-medium">
                            Last delivered ID
                          </th>
                          <th className="px-5 py-4 font-medium">Lag</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {consumerGroups.consumer_groups.map((group) => (
                          <tr
                            key={`${group.stream}-${group.group}`}
                            className="align-top"
                          >
                            <td className="px-5 py-4 text-foreground">
                              {getStreamLabel(group.stream)}
                              <p className="mt-1 max-w-[190px] break-all font-mono text-[11px] text-muted-foreground">
                                {group.stream}
                              </p>
                            </td>
                            <td className="px-5 py-4 font-mono text-xs text-foreground">
                              {group.group}
                            </td>
                            <td className="px-5 py-4 text-foreground">
                              {group.consumers_count}
                            </td>
                            <td className="px-5 py-4">
                              <span
                                className={
                                  group.pending_count > 0
                                    ? "rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-xs text-warning"
                                    : "rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-xs text-success"
                                }
                              >
                                {group.pending_count}
                              </span>
                            </td>
                            <td className="px-5 py-4 font-mono text-xs text-muted-foreground">
                              {shortId(group.last_delivered_id, 24)}
                            </td>
                            <td className="px-5 py-4 text-foreground">
                              {group.lag ?? "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="border-t border-border px-5 py-4">
                    <h3 className="mb-3 text-sm font-medium text-foreground">
                      Consumers
                    </h3>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {consumerGroups.consumer_groups.flatMap((group) =>
                        group.consumers.map((consumer) => (
                          <div
                            key={`${group.group}-${consumer.name}`}
                            className="rounded-lg border border-border bg-background p-4"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="break-all font-mono text-xs text-foreground">
                                  {consumer.name}
                                </p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {group.group}
                                </p>
                              </div>
                              <span className="shrink-0 rounded-full border border-border px-2 py-1 text-[11px] text-muted-foreground">
                                {consumer.pending_count} pending
                              </span>
                            </div>
                            <p className="mt-3 text-xs text-muted-foreground">
                              Idle for {formatDuration(consumer.idle_ms)}
                            </p>
                          </div>
                        )),
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <EmptyState message="No consumer groups were returned for the monitored streams." />
              )}
            </section>

            {/* Event activity */}
            <section className="mb-8">
              <SectionHeader
                title="Recent event activity"
                description="Browse recent order and delivery events from the monitored streams."
              />

              <form
                onSubmit={handleActivityFilterSubmit}
                className="mb-4 grid grid-cols-1 gap-3 rounded-xl border border-border bg-surface p-4 sm:grid-cols-2 xl:grid-cols-4"
              >
                <label className="text-xs text-muted-foreground">
                  Stream
                  <select
                    value={activityStreamDraft}
                    onChange={(event) =>
                      setActivityStreamDraft(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                  >
                    <option value="all">All streams</option>
                    <option value="order">Order</option>
                    <option value="delivery">Delivery</option>
                  </select>
                </label>

                <label className="text-xs text-muted-foreground">
                  Event type
                  <input
                    value={activityTypeDraft}
                    onChange={(event) =>
                      setActivityTypeDraft(event.target.value)
                    }
                    placeholder="e.g. order.created"
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
                  />
                </label>

                <label className="text-xs text-muted-foreground">
                  Order ID
                  <input
                    value={activityOrderDraft}
                    onChange={(event) =>
                      setActivityOrderDraft(event.target.value)
                    }
                    placeholder="Filter by order ID"
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
                  />
                </label>

                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                  >
                    Apply filters
                  </button>
                </div>
              </form>

              <ErrorMessage message={errors.activity} />

              <div className="overflow-hidden rounded-xl border border-border bg-surface">
                {loadingActivity ? (
                  <LoadingState />
                ) : activity?.events.length ? (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[900px] text-left text-sm">
                        <thead className="border-b border-border bg-background/70 text-xs uppercase tracking-wide text-muted-foreground">
                          <tr>
                            <th className="px-5 py-4 font-medium">Event</th>
                            <th className="px-5 py-4 font-medium">Stream</th>
                            <th className="px-5 py-4 font-medium">Order ID</th>
                            <th className="px-5 py-4 font-medium">
                              Message ID
                            </th>
                            <th className="px-5 py-4 font-medium">Timestamp</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {activity.events.map((event) => (
                            <tr
                              key={`${event.stream_key}-${event.message_id}`}
                              className="align-top"
                            >
                              <td className="px-5 py-4">
                                <span
                                  className={`inline-flex rounded-full border px-2.5 py-1 text-xs ${getEventBadgeClass(event.event_type)}`}
                                >
                                  {event.event_type || "Unknown event"}
                                </span>
                                {event.event_id && (
                                  <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                                    {shortId(event.event_id, 24)}
                                  </p>
                                )}
                              </td>
                              <td className="px-5 py-4 text-foreground">
                                {getStreamLabel(event.stream)}
                              </td>
                              <td className="px-5 py-4 font-mono text-xs text-muted-foreground">
                                {shortId(event.order_id, 24)}
                              </td>
                              <td className="px-5 py-4 font-mono text-xs text-muted-foreground">
                                {shortId(event.message_id, 24)}
                              </td>
                              <td className="px-5 py-4 whitespace-nowrap text-xs text-muted-foreground">
                                {formatTimestampMs(event.timestamp_ms)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="px-5 pb-2 pt-3 text-xs text-muted-foreground">
                      {activity.total.toLocaleString()} matching entries in the
                      scanned window.
                      {activity.note ? ` ${activity.note}` : ""}
                    </div>

                    <div className="px-5 pb-4">
                      <Pagination
                        page={activityPage}
                        hasMore={activity.has_more}
                        onPrevious={() =>
                          setActivityPage((current) => Math.max(1, current - 1))
                        }
                        onNext={() => setActivityPage((current) => current + 1)}
                      />
                    </div>
                  </>
                ) : (
                  <div className="p-5">
                    <EmptyState message="No events match the selected filters." />
                    {activity && (
                      <p className="mt-3 text-xs text-muted-foreground">
                        {activity.note}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </section>

            {/* Dead-letter events */}
            <section className="mb-8">
              <SectionHeader
                title="Dead-letter events"
                description="Inspect events that were moved to the dead-letter stream after processing failures."
              />

              <form
                onSubmit={handleDeadLetterFilterSubmit}
                className="mb-4 grid grid-cols-1 gap-3 rounded-xl border border-border bg-surface p-4 sm:grid-cols-3"
              >
                <label className="text-xs text-muted-foreground">
                  Original stream
                  <select
                    value={deadLetterStreamDraft}
                    onChange={(event) =>
                      setDeadLetterStreamDraft(event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-accent"
                  >
                    <option value="all">All original streams</option>
                    <option value="flowmesh:order-events">Order events</option>
                    <option value="flowmesh:delivery-events">
                      Delivery events
                    </option>
                  </select>
                </label>

                <label className="text-xs text-muted-foreground">
                  Event type
                  <input
                    value={deadLetterTypeDraft}
                    onChange={(event) =>
                      setDeadLetterTypeDraft(event.target.value)
                    }
                    placeholder="Filter by event type"
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-accent"
                  />
                </label>

                <div className="flex items-end">
                  <button
                    type="submit"
                    className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                  >
                    Apply filters
                  </button>
                </div>
              </form>

              <ErrorMessage message={errors.deadLetters} />

              <div className="overflow-hidden rounded-xl border border-border bg-surface">
                {loadingDeadLetters ? (
                  <LoadingState />
                ) : deadLetters?.dead_letters.length ? (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[950px] text-left text-sm">
                        <thead className="border-b border-border bg-background/70 text-xs uppercase tracking-wide text-muted-foreground">
                          <tr>
                            <th className="px-5 py-4 font-medium">Event</th>
                            <th className="px-5 py-4 font-medium">
                              Original stream
                            </th>
                            <th className="px-5 py-4 font-medium">Attempts</th>
                            <th className="px-5 py-4 font-medium">Error</th>
                            <th className="px-5 py-4 font-medium">
                              Dead-lettered at
                            </th>
                            <th className="px-5 py-4 font-medium">Details</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {deadLetters.dead_letters.map((item) => {
                            const isExpanded =
                              expandedDeadLetter ===
                              item.dead_letter_message_id;

                            return (
                              <tr
                                key={item.dead_letter_message_id}
                                className="align-top"
                              >
                                <td className="px-5 py-4">
                                  <p className="font-medium text-foreground">
                                    {item.event_type || "Unknown event"}
                                  </p>
                                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                                    {shortId(item.event_id, 24)}
                                  </p>
                                </td>
                                <td className="px-5 py-4">
                                  <p className="text-foreground">
                                    {getStreamLabel(item.original_stream)}
                                  </p>
                                  <p className="mt-1 max-w-[180px] break-all font-mono text-[11px] text-muted-foreground">
                                    {item.original_stream || "—"}
                                  </p>
                                </td>
                                <td className="px-5 py-4">
                                  <span className="rounded-full border border-danger/30 bg-danger/10 px-2.5 py-1 text-xs text-danger">
                                    {item.attempts ?? "—"}
                                  </span>
                                </td>
                                <td className="max-w-[260px] px-5 py-4">
                                  <p className="line-clamp-3 break-words text-xs text-muted-foreground">
                                    {item.error || "No error detail provided"}
                                  </p>
                                </td>
                                <td className="px-5 py-4 whitespace-nowrap text-xs text-muted-foreground">
                                  {formatDate(item.dead_lettered_at)}
                                </td>
                                <td className="px-5 py-4">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedDeadLetter(
                                        isExpanded
                                          ? null
                                          : item.dead_letter_message_id,
                                      )
                                    }
                                    className="rounded-lg border border-border px-3 py-2 text-xs font-medium text-foreground transition hover:bg-background"
                                  >
                                    {isExpanded ? "Hide" : "Inspect"}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {expandedDeadLetter && (
                      <div className="border-t border-border bg-background/50 p-5">
                        {deadLetters.dead_letters
                          .filter(
                            (item) =>
                              item.dead_letter_message_id ===
                              expandedDeadLetter,
                          )
                          .map((item) => (
                            <div key={item.dead_letter_message_id}>
                              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                                <h3 className="font-semibold text-foreground">
                                  Dead-letter details
                                </h3>
                                <button
                                  type="button"
                                  onClick={() => setExpandedDeadLetter(null)}
                                  className="text-xs text-muted-foreground hover:text-foreground"
                                >
                                  Close details
                                </button>
                              </div>

                              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                <div className="rounded-lg border border-border bg-surface p-3">
                                  <p className="text-xs text-muted-foreground">
                                    Original consumer group
                                  </p>
                                  <p className="mt-1 break-all font-mono text-xs text-foreground">
                                    {item.original_group || "—"}
                                  </p>
                                </div>
                                <div className="rounded-lg border border-border bg-surface p-3">
                                  <p className="text-xs text-muted-foreground">
                                    Original message ID
                                  </p>
                                  <p className="mt-1 break-all font-mono text-xs text-foreground">
                                    {item.original_message_id || "—"}
                                  </p>
                                </div>
                                <div className="rounded-lg border border-border bg-surface p-3 sm:col-span-2">
                                  <p className="text-xs text-muted-foreground">
                                    Error
                                  </p>
                                  <p className="mt-1 break-words text-sm text-foreground">
                                    {item.error || "No error detail provided"}
                                  </p>
                                </div>
                              </div>

                              <div className="mt-4">
                                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                  Original event fields
                                </p>
                                <pre className="max-h-[360px] overflow-auto rounded-lg border border-border bg-surface p-4 text-xs leading-5 text-foreground">
                                  {JSON.stringify(
                                    item.original_fields ?? {},
                                    null,
                                    2,
                                  )}
                                </pre>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}

                    <div className="px-5 pb-2 pt-3 text-xs text-muted-foreground">
                      {deadLetters.matching_scanned.toLocaleString()} matching
                      entries found in the scanned window. The stream contains{" "}
                      {deadLetters.total.toLocaleString()} total entries.
                    </div>

                    {deadLetters.scan_truncated && (
                      <div className="mx-5 mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                        The scan reached its limit of{" "}
                        {deadLetters.scan_limit.toLocaleString()} entries.
                        Additional matching entries may exist outside the
                        scanned window.
                      </div>
                    )}

                    <div className="px-5 pb-4">
                      <Pagination
                        page={deadLetterPage}
                        hasMore={deadLetters.has_more}
                        onPrevious={() =>
                          setDeadLetterPage((current) =>
                            Math.max(1, current - 1),
                          )
                        }
                        onNext={() =>
                          setDeadLetterPage((current) => current + 1)
                        }
                      />
                    </div>
                  </>
                ) : (
                  <div className="p-5">
                    <EmptyState message="No dead-letter events match the selected filters." />
                    {deadLetters && (
                      <p className="mt-3 text-xs text-muted-foreground">
                        {deadLetters.total.toLocaleString()} total entries in
                        the dead-letter stream;{" "}
                        {deadLetters.matching_scanned.toLocaleString()} matched
                        the current filters in the scanned window.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </section>

            <footer className="border-t border-border py-5 text-xs text-muted-foreground">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p>FlowMesh Event Streams</p>
                <p>
                  Last overview check:{" "}
                  {formatDate(streams?.checked_at || overview?.checked_at)}
                </p>
              </div>
            </footer>
          </div>
        </main>
      </div>
    </ProtectedRoute>
  );
}
