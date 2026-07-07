"use client";

import type { AnalysisDetail } from "@/lib/types";
import {
  buildMemoFilename,
  buildWorkbookFilename,
  COMPLETION_SUCCESS_MESSAGE,
} from "@/lib/analysis-completion";

type CompletedAnalysisPanelProps = {
  analysis: AnalysisDetail;
  onViewCompleted: () => void;
  compact?: boolean;
};

export default function CompletedAnalysisPanel({
  analysis,
  onViewCompleted,
  compact = false,
}: CompletedAnalysisPanelProps) {
  const workbookName = buildWorkbookFilename(analysis);
  const memoName = buildMemoFilename(analysis);

  return (
    <section
      className={`rounded border border-hap-success/30 bg-hap-success/10 ${
        compact ? "p-4" : "p-6"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-hap-success/20 text-sm font-bold text-hap-success">
          ✓
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-hap-success">
            Analysis complete
          </p>
          <p className={`mt-2 text-foreground/90 ${compact ? "text-sm" : "text-base"}`}>
            {COMPLETION_SUCCESS_MESSAGE}
          </p>
          {!compact && (
            <p className="mt-2 text-sm text-hap-muted">
              {analysis.executiveSummary}
            </p>
          )}
        </div>
      </div>

      <div className={`flex flex-wrap gap-3 ${compact ? "mt-4" : "mt-6"}`}>
        <button
          type="button"
          onClick={onViewCompleted}
          className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange transition-colors hover:border-hap-orange hover:bg-hap-orange/20"
        >
          View completed analysis
        </button>

        <button
          type="button"
          disabled
          title="Coming soon"
          className="inline-flex items-center gap-2 rounded border border-hap-border px-4 py-2 text-sm text-hap-muted opacity-70"
        >
          Download completed workbook
          <span className="rounded bg-hap-panel px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
            Coming soon
          </span>
        </button>

        <button
          type="button"
          disabled
          title="Coming soon"
          className="inline-flex items-center gap-2 rounded border border-hap-border px-4 py-2 text-sm text-hap-muted opacity-70"
        >
          Download investment memo
          <span className="rounded bg-hap-panel px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
            Coming soon
          </span>
        </button>
      </div>

      {!compact && (
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-hap-muted">
          <span>Workbook: {workbookName}</span>
          <span>Memo: {memoName}</span>
          {analysis.completedAt && (
            <span>
              Completed: {new Date(analysis.completedAt).toLocaleString()}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
