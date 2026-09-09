"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import type { AnalysisDetail, AnalysisStatus } from "@/lib/types";
import StatusBadge from "./StatusBadge";

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function formatLongDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function relativeLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = Date.now();
  const diffMs = now - date.getTime();
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return formatLongDate(value);
}

function groupKey(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Undated";
  const today = startOfDay(new Date());
  const that = startOfDay(date);
  const deltaDays = Math.round((today.getTime() - that.getTime()) / 86_400_000);
  if (deltaDays <= 0) return "Today";
  if (deltaDays === 1) return "Yesterday";
  if (deltaDays < 7) return "This week";
  return date.toLocaleDateString("en-US", { year: "numeric", month: "long" });
}

const GROUP_ORDER = ["Today", "Yesterday", "This week"];

type KindFilter = "all" | "complete" | "failed" | "in_flight";

function kindOf(row: AnalysisDetail): KindFilter {
  if (row.status === "Running" || row.status === "Queued") return "in_flight";
  if (row.status === "Failed") return "failed";
  return "complete";
}

export default function HistoryView() {
  const { analyses, isLoadingList, listError } = useAnalysisStore();
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<KindFilter>("all");
  const [typeFilter, setTypeFilter] = useState("all");

  const types = useMemo(() => {
    const set = new Set(analyses.map((a) => a.type).filter(Boolean));
    return [...set].sort();
  }, [analyses]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...analyses]
      .filter((row) => {
        if (kind !== "all" && kindOf(row) !== kind) return false;
        if (typeFilter !== "all" && row.type !== typeFilter) return false;
        if (!q) return true;
        return (
          row.company.toLowerCase().includes(q) ||
          row.ticker.toLowerCase().includes(q) ||
          row.type.toLowerCase().includes(q)
        );
      })
      .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime());
  }, [analyses, query, kind, typeFilter]);

  const grouped = useMemo(() => {
    const map = new Map<string, AnalysisDetail[]>();
    for (const row of filtered) {
      const key = groupKey(row.startedAt);
      const list = map.get(key) ?? [];
      list.push(row);
      map.set(key, list);
    }
    const keys = [...map.keys()].sort((a, b) => {
      const ai = GROUP_ORDER.indexOf(a);
      const bi = GROUP_ORDER.indexOf(b);
      if (ai !== -1 || bi !== -1) {
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      }
      return a < b ? 1 : -1;
    });
    return keys.map((key) => ({ key, rows: map.get(key) ?? [] }));
  }, [filtered]);

  const counts = useMemo(() => {
    return {
      total: analyses.length,
      complete: analyses.filter((a) => a.status === "Complete").length,
      failed: analyses.filter((a) => a.status === "Failed").length,
      running: analyses.filter((a) => a.status === "Running" || a.status === "Queued").length,
    };
  }, [analyses]);

  return (
    <main className="flex h-full flex-1 flex-col overflow-hidden">
      <header className="shrink-0 border-b border-hap-border px-6 py-5 lg:px-8">
        <p className="text-xs uppercase tracking-widest text-hap-muted">Archive</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight lg:text-3xl">History</h2>
        <p className="mt-1 max-w-2xl text-sm text-hap-muted">
          Every analysis HAP has run, grouped by when it started. Open a run to download Excel and Word.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6 lg:px-8">
        <div className="mb-6 grid gap-3 sm:grid-cols-4">
          <StatCard label="All runs" value={counts.total} />
          <StatCard label="Complete" value={counts.complete} tone="success" />
          <StatCard label="In flight" value={counts.running} tone="info" />
          <StatCard label="Failed" value={counts.failed} tone="warning" />
        </div>

        <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search company, ticker, or type…"
            className="w-full rounded-lg border border-hap-border bg-hap-panel px-4 py-2.5 text-sm outline-none ring-hap-orange/30 placeholder:text-hap-muted focus:border-hap-orange/50 focus:ring-1 lg:max-w-sm"
          />
          <div className="flex flex-wrap gap-2">
            {(
              [
                ["all", "All"],
                ["complete", "Complete"],
                ["in_flight", "In flight"],
                ["failed", "Failed"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setKind(id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  kind === id
                    ? "border-hap-orange bg-hap-orange/15 text-hap-orange"
                    : "border-hap-border text-hap-muted hover:border-hap-border-bright hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-full border border-hap-border bg-hap-panel px-3 py-1.5 text-xs text-hap-muted outline-none focus:border-hap-orange/50"
            >
              <option value="all">All types</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </div>

        {listError ? (
          <p className="text-sm text-red-400">{listError}</p>
        ) : isLoadingList ? (
          <p className="text-sm text-hap-muted">Loading history…</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-dashed border-hap-border px-6 py-16 text-center">
            <p className="text-sm font-medium">No matching analyses</p>
            <p className="mt-1 text-sm text-hap-muted">
              {analyses.length === 0
                ? "Start a new analysis from the dashboard. Completed runs will collect here."
                : "Try a different search or filter."}
            </p>
          </div>
        ) : (
          <div className="space-y-8">
            {grouped.map((group) => (
              <section key={group.key}>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-hap-muted">
                  {group.key}
                  <span className="ml-2 font-normal text-hap-muted/70">{group.rows.length}</span>
                </h3>
                <ol className="relative space-y-3 border-l border-hap-border pl-5">
                  {group.rows.map((row) => (
                    <li key={row.id} className="relative">
                      <span className="absolute -left-[1.4rem] top-5 h-2.5 w-2.5 rounded-full border-2 border-hap-panel bg-hap-orange" />
                      <HistoryCard row={row} />
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "success" | "info" | "warning";
}) {
  const color =
    tone === "success"
      ? "text-hap-success"
      : tone === "info"
        ? "text-hap-info"
        : tone === "warning"
          ? "text-hap-warning"
          : "text-foreground";
  return (
    <div className="rounded-xl border border-hap-border bg-hap-panel px-4 py-3">
      <p className="text-[10px] uppercase tracking-widest text-hap-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function HistoryCard({ row }: { row: AnalysisDetail }) {
  return (
    <Link
      href={`/analysis/${row.id}`}
      className="block rounded-xl border border-hap-border bg-hap-panel p-4 transition-colors hover:border-hap-orange/40 hover:bg-hap-panel-elevated"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold text-hap-orange">{row.ticker}</span>
            <StatusBadge status={row.status as AnalysisStatus} />
          </div>
          <p className="mt-1 text-base font-medium">{row.company}</p>
          <p className="mt-0.5 text-xs text-hap-muted">{row.type}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-foreground">{formatLongDate(row.startedAt)}</p>
          <p className="text-xs text-hap-muted">
            {formatTime(row.startedAt)}
            {relativeLabel(row.startedAt) ? ` · ${relativeLabel(row.startedAt)}` : ""}
          </p>
          {row.recommendationLabel ? (
            <p className="mt-1 text-xs text-hap-orange">{row.recommendationLabel}</p>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
