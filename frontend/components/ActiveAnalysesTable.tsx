"use client";

import Link from "next/link";
import { useAnalysisStore } from "@/lib/analysis-store-context";
import { formatScore, formatStageLabel } from "@/lib/map-backend-analysis";
import StatusBadge from "./StatusBadge";

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function ActiveAnalysesTable() {
  const { analyses, isLoadingList, listError } = useAnalysisStore();

  return (
    <div id="active-analyses" className="overflow-hidden rounded border border-hap-border bg-hap-panel">
      <div className="border-b border-hap-border px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Active Analyses
        </h3>
      </div>

      <div className="overflow-x-auto">
        {listError ? (
          <p className="px-4 py-6 text-sm text-red-400">{listError}</p>
        ) : isLoadingList ? (
          <p className="px-4 py-6 text-sm text-hap-muted">Loading analyses…</p>
        ) : analyses.length === 0 ? (
          <p className="px-4 py-6 text-sm text-hap-muted">
            No analyses yet. Start a new analysis to see results here.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Progress</th>
                <th className="px-4 py-3 font-medium">Stage</th>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Recommendation</th>
                <th className="px-4 py-3 font-medium">Business Quality</th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-hap-border/50 transition-colors hover:bg-hap-panel-elevated/50"
                >
                  <td className="px-4 py-3">
                    <Link href={`/analysis/${row.id}`} className="group block">
                      <div className="font-medium group-hover:text-hap-orange">
                        {row.company}
                      </div>
                      {row.pipelineError ? (
                        <div className="mt-0.5 max-w-[220px] truncate text-[10px] text-red-400">
                          {row.pipelineError}
                        </div>
                      ) : null}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-hap-orange">
                    {row.ticker}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-hap-border">
                        <div
                          className="h-full rounded-full bg-hap-orange"
                          style={{ width: `${row.progress}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs text-hap-muted">
                        {row.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-hap-muted">
                    {formatStageLabel(row.currentStage)}
                  </td>
                  <td className="px-4 py-3 text-hap-muted">{formatDate(row.startedAt)}</td>
                  <td className="px-4 py-3">
                    {row.recommendationLabel ?? row.recommendation ?? "—"}
                  </td>
                  <td className="px-4 py-3 font-mono">
                    {formatScore(row.businessQualityScore)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
