"use client";

import type { AnalysisDetail, PipelineStage } from "@/lib/types";
import {
  isStageComplete,
  isStageCurrent,
  PIPELINE_STAGE_DESCRIPTIONS,
  PIPELINE_STAGE_LABELS,
  PIPELINE_STAGES,
} from "@/lib/pipeline-stages";

type PipelineProgressProps = {
  analysis: AnalysisDetail;
};

function stageState(
  currentStage: PipelineStage,
  stage: PipelineStage,
): "complete" | "current" | "upcoming" {
  if (isStageComplete(currentStage, stage)) return "complete";
  if (isStageCurrent(currentStage, stage)) return "current";
  return "upcoming";
}

export default function PipelineProgress({ analysis }: PipelineProgressProps) {
  return (
    <section className="rounded border border-hap-border bg-hap-panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Analysis pipeline
          </h3>
          <p className="mt-2 text-sm text-foreground/90">{analysis.pipelineMessage}</p>
        </div>
        {!analysis.backendConnected && !analysis.isDemo && (
          <span className="rounded border border-hap-warning/30 bg-hap-warning/10 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-hap-warning">
            Backend offline — local state only
          </span>
        )}
      </div>

      <ol className="mt-5 space-y-3">
        {PIPELINE_STAGES.map((stage, index) => {
          const state = stageState(analysis.pipelineStage, stage);

          return (
            <li
              key={stage}
              className={`rounded border px-4 py-3 ${
                state === "current"
                  ? "border-hap-orange/40 bg-hap-orange/10"
                  : state === "complete"
                    ? "border-hap-success/30 bg-hap-success/5"
                    : "border-hap-border bg-hap-panel-elevated/40"
              }`}
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                    state === "complete"
                      ? "bg-hap-success/20 text-hap-success"
                      : state === "current"
                        ? "bg-hap-orange/20 text-hap-orange"
                        : "bg-hap-border text-hap-muted"
                  }`}
                >
                  {state === "complete" ? "✓" : index + 1}
                </span>
                <div>
                  <p
                    className={`text-sm font-medium ${
                      state === "current" ? "text-hap-orange" : "text-foreground"
                    }`}
                  >
                    {PIPELINE_STAGE_LABELS[stage]}
                  </p>
                  <p className="mt-1 text-xs text-hap-muted">
                    {PIPELINE_STAGE_DESCRIPTIONS[stage]}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
