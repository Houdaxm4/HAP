"use client";

import type { AnalysisDetail } from "@/lib/types";
import {
  hasRealOutputs,
  isAnalysisComplete,
  isProcessing,
} from "@/lib/analysis-pipeline";
import { API_BASE_URL } from "@/lib/api";
import {
  OUTPUT_LABELS,
  PIPELINE_PENDING_MESSAGE,
} from "@/lib/pipeline-stages";

type PipelineOutputsPanelProps = {
  analysis: AnalysisDetail;
  onViewSummary: () => void;
  compact?: boolean;
};

export default function PipelineOutputsPanel({
  analysis,
  onViewSummary,
  compact = false,
}: PipelineOutputsPanelProps) {
  const processing = isProcessing(analysis);
  const workbookReady = hasRealOutputs(analysis);
  const outputsReady = isAnalysisComplete(analysis) && workbookReady;

  return (
    <section
      className={`rounded border ${
        outputsReady
          ? "border-hap-success/30 bg-hap-success/10"
          : processing
            ? "border-hap-warning/30 bg-hap-warning/10"
            : "border-hap-info/30 bg-hap-info/10"
      } ${compact ? "p-4" : "p-6"}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
            outputsReady
              ? "bg-hap-success/20 text-hap-success"
              : processing
                ? "bg-hap-warning/20 text-hap-warning"
                : "bg-hap-info/20 text-hap-info"
          }`}
        >
          {outputsReady ? "✓" : processing ? "…" : "•"}
        </div>
        <div className="min-w-0 flex-1">
          <p
            className={`text-xs font-semibold uppercase tracking-widest ${
              outputsReady
                ? "text-hap-success"
                : processing
                  ? "text-hap-warning"
                  : "text-hap-info"
            }`}
          >
            {processing
              ? "Phase 1 processing"
              : workbookReady
                ? "Phase 1 complete"
                : "Pipeline waiting"}
          </p>
          <p className={`mt-2 text-foreground/90 ${compact ? "text-sm" : "text-base"}`}>
            {processing
              ? analysis.pipelineMessage
              : workbookReady
                ? "Phase 1 complete. Workbook filled from SEC filings. Fundamental analysis is next."
                : PIPELINE_PENDING_MESSAGE}
          </p>
          {!compact && !processing && (
            <p className="mt-2 text-sm text-hap-muted">{analysis.pipelineMessage}</p>
          )}
        </div>
      </div>

      <div className={`grid gap-2 ${compact ? "mt-4" : "mt-6"} sm:grid-cols-2`}>
        {(Object.keys(OUTPUT_LABELS) as Array<keyof typeof OUTPUT_LABELS>).map(
          (key) => {
            const status = analysis.pipelineOutputs[key];
            const ready = status === "ready";

            return (
              <div
                key={key}
                className="flex items-center justify-between rounded border border-hap-border bg-hap-panel px-3 py-2 text-sm"
              >
                <span>{OUTPUT_LABELS[key]}</span>
                <span
                  className={`text-xs font-medium uppercase ${
                    ready ? "text-hap-success" : processing ? "text-hap-warning" : "text-hap-muted"
                  }`}
                >
                  {ready ? "Ready" : processing ? "Processing" : "Pending"}
                </span>
              </div>
            );
          },
        )}
      </div>

      <div className={`flex flex-wrap gap-3 ${compact ? "mt-4" : "mt-6"}`}>
        <button
          type="button"
          onClick={onViewSummary}
          className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange transition-colors hover:border-hap-orange hover:bg-hap-orange/20"
        >
          View completed analysis
        </button>

        {workbookReady && analysis.backendAnalysisId ? (
          <a
            href={`${API_BASE_URL}/analysis/${analysis.backendAnalysisId}/outputs/workbook`}
            className="inline-flex items-center gap-2 rounded border border-hap-success/40 bg-hap-success/10 px-4 py-2 text-sm font-medium text-hap-success transition-colors hover:bg-hap-success/20"
          >
            Download completed workbook
          </a>
        ) : (
          <button
            type="button"
            disabled
            title={processing ? "Phase 1 in progress" : "Workbook not ready"}
            className="inline-flex items-center gap-2 rounded border border-hap-border px-4 py-2 text-sm text-hap-muted opacity-70"
          >
            Download completed workbook
            <span className="rounded bg-hap-panel px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
              {processing ? "Processing" : "Pending"}
            </span>
          </button>
        )}

        <button
          type="button"
          disabled
          title="Coming in a later phase"
          className="inline-flex items-center gap-2 rounded border border-hap-border px-4 py-2 text-sm text-hap-muted opacity-70"
        >
          Download investment memo
          <span className="rounded bg-hap-panel px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
            Coming soon
          </span>
        </button>
      </div>
    </section>
  );
}
