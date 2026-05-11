"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  fetchUsageReport,
  usageReportCsvUrl,
  type UsageItem,
  type UsageRange,
  type UsageReportQuery,
  type UsageReportResponse,
} from "@/lib/api";

const PAGE_SIZE = 25;

type RangePreset = {
  id: UsageRange;
  label: string;
};

const RANGE_PRESETS: RangePreset[] = [
  { id: "current_month", label: "Current month" },
  { id: "last_2_months", label: "Last 2 months" },
  { id: "last_30_days", label: "Last 30 days" },
  { id: "custom", label: "Custom" },
];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstOfMonthIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPeriod(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const s = new Date(start);
  const e = new Date(end);
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return "—";
  // Show inclusive end-day (backend `end` is exclusive — subtract 1 ms).
  const eDisplay = new Date(e.getTime() - 1);
  const sameMonth =
    s.getFullYear() === eDisplay.getFullYear() && s.getMonth() === eDisplay.getMonth();
  const fmt = (d: Date) =>
    d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
    });
  return sameMonth
    ? `${s.toLocaleDateString(undefined, { year: "numeric", month: "long" })}`
    : `${fmt(s)} → ${fmt(eDisplay)}`;
}

function rowAmountClass(item: UsageItem): string {
  if (item.kind === "spend") return "text-red-300/90";
  if (item.kind === "refund") return "text-amber-200/90";
  return "text-emerald-300/90";
}

function rowAmountValue(item: UsageItem): string {
  if (item.kind === "spend") return `−${item.credits_consumed}`;
  if (item.kind === "refund") return `+${item.credits_granted || -item.delta}`;
  if (item.credits_granted) return `+${item.credits_granted}`;
  return `${item.delta}`;
}

export function UsageReport({
  starterRedeemAvailable,
}: {
  starterRedeemAvailable?: boolean;
}) {
  void starterRedeemAvailable;
  const [range, setRange] = useState<UsageRange>("current_month");
  const [from, setFrom] = useState<string>(firstOfMonthIso());
  const [to, setTo] = useState<string>(todayIso());
  const [page, setPage] = useState<number>(1);
  const [data, setData] = useState<UsageReportResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const query: UsageReportQuery = useMemo(
    () => ({
      range,
      from: range === "custom" ? from : undefined,
      to: range === "custom" ? to : undefined,
      page,
      pageSize: PAGE_SIZE,
    }),
    [range, from, to, page],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchUsageReport(query);
      setData(res);
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Could not load usage report";
      setError(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const downloadHref = usageReportCsvUrl(query);

  return (
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-lg font-semibold">Usage report</p>
          <p className="text-sm text-slate-300">
            See every charge and grant on this account. 1 credit = ₹1. Use the
            range selector below to focus the period, then download a CSV for
            your records.
          </p>
        </div>
        <a
          href={downloadHref}
          download
          className="inline-flex items-center justify-center rounded-xl border border-white/25 bg-white/5 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10"
        >
          Download CSV
        </a>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {RANGE_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            onClick={() => {
              setRange(preset.id);
              setPage(1);
            }}
            className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
              range === preset.id
                ? "bg-purple-500/30 text-white"
                : "border border-white/15 bg-white/5 text-slate-200 hover:bg-white/10"
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {range === "custom" ? (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-slate-400">
            From
            <input
              type="date"
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
              className="mt-1 rounded-lg border border-white/15 bg-[#0d1020] px-2 py-1.5 text-sm text-white outline-none focus:ring-2 focus:ring-purple-400/40"
            />
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            To
            <input
              type="date"
              value={to}
              min={from}
              max={todayIso()}
              onChange={(e) => setTo(e.target.value)}
              className="mt-1 rounded-lg border border-white/15 bg-[#0d1020] px-2 py-1.5 text-sm text-white outline-none focus:ring-2 focus:ring-purple-400/40"
            />
          </label>
          <Button variant="outline" size="sm" onClick={() => { setPage(1); void load(); }}>
            Apply
          </Button>
        </div>
      ) : null}

      {error ? (
        <p className="text-sm text-red-300/90">
          Could not load usage: {error}.{" "}
          <button
            type="button"
            className="text-purple-300 underline hover:text-purple-200"
            onClick={() => void load()}
          >
            Retry
          </button>
        </p>
      ) : null}

      {data?.credits_enabled === false ? (
        <p className="text-sm text-amber-200/90">
          Credits are not active on this server. Once enabled, every generation
          will start showing here.
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Period</p>
          <p className="mt-1 text-sm font-semibold">
            {formatPeriod(data?.summary.period_start ?? null, data?.summary.period_end ?? null)}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Charged</p>
          <p className="mt-1 text-sm font-semibold text-red-300/90">
            {data ? `${data.summary.total_charged} credits` : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Granted</p>
          <p className="mt-1 text-sm font-semibold text-emerald-300/90">
            {data ? `+${data.summary.total_granted} credits` : "—"}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Current balance</p>
          <p className="mt-1 text-sm font-semibold text-orange-200">
            {data ? `${data.summary.current_balance} credits` : "—"}
          </p>
        </div>
      </div>

      {data && data.summary.by_query_type.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wide text-slate-400">By query type</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.summary.by_query_type.map((g) => (
              <div
                key={g.query_type}
                className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm"
              >
                <span>{g.query_type}</span>
                <span className="text-slate-300">
                  {g.count} · {g.credits} credits
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-xl border border-white/10 md:block">
        <table className="min-w-full text-sm">
          <thead className="bg-white/5 text-left text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2 font-medium">Date</th>
              <th className="px-3 py-2 font-medium">User Query</th>
              <th className="px-3 py-2 font-medium">Query Type</th>
              <th className="px-3 py-2 font-medium">Count / Per sec</th>
              <th className="px-3 py-2 font-medium text-right">Credit Consumed</th>
              <th className="px-3 py-2 font-medium text-right">Balance After</th>
            </tr>
          </thead>
          <tbody>
            {loading && !data ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-400">
                  Loading usage…
                </td>
              </tr>
            ) : !data || data.items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-400">
                  No activity in this period yet.
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                <tr key={item.id} className="border-t border-white/5">
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">
                    {formatDate(item.created_at)}
                  </td>
                  <td className="px-3 py-2 text-slate-100">
                    <span title={item.user_query}>
                      {item.user_query}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">
                    {item.query_type}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">
                    {item.unit_label}
                  </td>
                  <td
                    className={`whitespace-nowrap px-3 py-2 text-right font-medium ${rowAmountClass(item)}`}
                  >
                    {rowAmountValue(item)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right text-slate-300">
                    {item.balance_after}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile card list — same data, one card per row */}
      <div className="space-y-2 md:hidden">
        {loading && !data ? (
          <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-4 text-center text-sm text-slate-400">
            Loading usage…
          </p>
        ) : !data || data.items.length === 0 ? (
          <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-4 text-center text-sm text-slate-400">
            No activity in this period yet.
          </p>
        ) : (
          data.items.map((item) => (
            <div
              key={item.id}
              className="rounded-xl border border-white/10 bg-white/5 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <p
                  className="min-w-0 flex-1 truncate text-sm font-medium text-slate-100"
                  title={item.user_query}
                >
                  {item.user_query}
                </p>
                <span
                  className={`shrink-0 text-sm font-semibold ${rowAmountClass(item)}`}
                >
                  {rowAmountValue(item)}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {formatDate(item.created_at)}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-300">
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5">
                  {item.query_type}
                </span>
                <span>{item.unit_label}</span>
                <span className="ml-auto text-slate-400">
                  Balance: {item.balance_after}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {data && data.total > data.page_size ? (
        <div className="flex items-center justify-between text-sm text-slate-300">
          <span>
            Page {data.page} of {totalPages} · {data.total} entries
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={loading || data.page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={loading || data.page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
