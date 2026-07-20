"use client";

import type { AnalysisDetail } from "@/lib/types";
import { formatStageLabel } from "@/lib/map-backend-analysis";

type RunActivityPanelProps = {
  analysis?: AnalysisDetail | null;
};

export default function RunActivityPanel({ analysis }: RunActivityPanelProps) {
  if (!analysis) {
    return (
      <aside className="flex h-full w-full flex-col border-t border-hap-border bg-hap-panel lg:w-80 lg:border-t-0 lg:border-l xl:w-96">
        <div className="border-b border-hap-border px-5 py-4">
          <h3 className="text-sm font-semibold">Run activity</h3>
          <p className="text-[10px] text-hap-muted">Pipeline progress &amp; decision log</p>
        </div>
        <div className="flex flex-1 items-center justify-center px-5 py-4">
          <p className="text-center text-sm text-hap-muted">
            Open an analysis to watch stage progress and decision log entries.
          </p>
        </div>
      </aside>
    );
  }

  const log = [...analysis.decisionLog].reverse();

  return (
    <aside className="flex h-full w-full flex-col border-t border-hap-border bg-hap-panel lg:w-80 lg:border-t-0 lg:border-l xl:w-96">
      <div className="shrink-0 border-b border-hap-border px-5 py-4">
        <h3 className="text-sm font-semibold">Run activity</h3>
        <p className="mt-1 text-xs text-hap-muted">
          {analysis.status}
          {analysis.currentStage
            ? ` · ${formatStageLabel(analysis.currentStage)}`
            : ""}
          {` · ${analysis.progress}%`}
        </p>
      </div>

      {analysis.pipelineError ? (
        <div className="border-b border-red-500/30 bg-red-500/10 px-5 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-red-400">
            Pipeline error
          </p>
          <p className="mt-1 text-sm text-red-300">{analysis.pipelineError}</p>
        </div>
      ) : null}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        {log.length === 0 ? (
          <p className="text-sm text-hap-muted">
            {analysis.status === "Running" || analysis.status === "Queued"
              ? "Waiting for the first pipeline stage…"
              : "No decision log entries for this analysis."}
          </p>
        ) : (
          <ol className="space-y-3">
            {log.map((entry) => (
              <li
                key={entry.id}
                className="rounded border border-hap-border/70 bg-background/40 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-hap-orange">{entry.agent}</p>
                  <p className="font-mono text-[10px] text-hap-muted">{entry.timestamp}</p>
                </div>
                <p className="mt-1 text-sm font-medium">{entry.action}</p>
                <p className="mt-0.5 text-xs text-hap-muted">{entry.detail}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
