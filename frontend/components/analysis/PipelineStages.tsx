"use client";

import {
  PIPELINE_STAGES,
  PIPELINE_STAGE_LABELS,
  stageLabel,
  type PipelineStageId,
} from "@/lib/pipeline-stages";
import type { AnalysisRecord } from "@/lib/types";

type PipelineStagesProps = {
  analysis: AnalysisRecord;
};

export default function PipelineStages({ analysis }: PipelineStagesProps) {
  const completed = new Set(analysis.stagesCompleted);
  const current = analysis.currentStage;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Pipeline Stages
        </h3>
        <span className="text-xs text-hap-muted">{stageLabel(current)}</span>
      </div>

      <ol className="space-y-2">
        {PIPELINE_STAGES.map((stage) => {
          const isComplete = completed.has(stage);
          const isCurrent = current === stage && !isComplete;

          return (
            <li
              key={stage}
              className={`flex items-center gap-3 rounded border px-3 py-2 text-sm ${
                analysis.displayStatus === "Failed" && current === stage
                  ? "border-red-500/40 bg-red-500/10"
                  : isCurrent
                    ? "border-hap-orange/40 bg-hap-orange/10"
                    : isComplete
                      ? "border-hap-success/30 bg-hap-success/5"
                      : "border-hap-border bg-hap-panel"
              }`}
            >
              <span
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ${
                  analysis.displayStatus === "Failed" && current === stage
                    ? "bg-red-500/20 text-red-300"
                    : isComplete
                      ? "bg-hap-success/20 text-hap-success"
                      : isCurrent
                        ? "bg-hap-orange/20 text-hap-orange"
                        : "bg-hap-border text-hap-muted"
                }`}
              >
                {isComplete ? "✓" : analysis.displayStatus === "Failed" && current === stage ? "!" : "•"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-medium">{PIPELINE_STAGE_LABELS[stage as PipelineStageId]}</p>
              </div>
            </li>
          );
        })}
      </ol>

      {analysis.pipelineError && (
        <p className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {analysis.pipelineError}
        </p>
      )}
    </div>
  );
}
