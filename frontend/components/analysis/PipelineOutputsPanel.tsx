"use client";

import type { AnalysisDetail } from "@/lib/types";
import {
  hasRealOutputs,
  isAnalysisComplete,
} from "@/lib/analysis-pipeline";
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
  const outputsReady = isAnalysisComplete(analysis) && hasRealOutputs(analysis);
  const pending = !outputsReady;

  return (
    <section
      className={`rounded border ${
        outputsReady
          ? "border-hap-success/30 bg-hap-success/10"
          : "border-hap-info/30 bg-hap-info/10"
      } ${compact ? "p-4" : "p-6"}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
            outputsReady
              ? "bg-hap-success/20 text-hap-success"
              : "bg-hap-info/20 text-hap-info"
          }`}
        >
          {outputsReady ? "✓" : "…"}
        </div>
        <div className="min-w-0 flex-1">
          <p
            className={`text-xs font-semibold uppercase tracking-widest ${
              outputsReady ? "text-hap-success" : "text-hap-info"
            }`}
          >
            {outputsReady ? "Outputs ready" : "Pipeline in progress"}
          </p>
          <p className={`mt-2 text-foreground/90 ${compact ? "text-sm" : "text-base"}`}>
            {outputsReady
              ? "Analysis complete. Review the completed workbook and investment memo."
              : PIPELINE_PENDING_MESSAGE}
          </p>
          {!compact && (
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
                    ready ? "text-hap-success" : "text-hap-muted"
                  }`}
                >
                  {ready ? "Ready" : "Pending"}
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
    </section>
  );
}
