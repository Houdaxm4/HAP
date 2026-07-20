"use client";

import Link from "next/link";
import type { AnalysisDetail } from "@/lib/types";
import { formatScore, formatStageLabel } from "@/lib/map-backend-analysis";
import StatusBadge from "../StatusBadge";

type AnalysisHeaderProps = {
  analysis: AnalysisDetail;
  onOpenDeliverables?: () => void;
};

export default function AnalysisHeader({
  analysis,
  onOpenDeliverables,
}: AnalysisHeaderProps) {
  return (
    <header className="shrink-0 border-b border-hap-border px-6 py-5 lg:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs text-hap-muted">
            <Link href="/" className="hover:text-hap-orange">
              Command Center
            </Link>
            <span className="mx-2">/</span>
            <span>{analysis.ticker}</span>
          </p>
          <div className="mt-2 flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{analysis.company}</h1>
            <span className="font-mono text-lg text-hap-orange">{analysis.ticker}</span>
          </div>
          <p className="mt-1 text-sm text-hap-muted">
            {analysis.type}
            {analysis.recommendationLabel
              ? ` · ${analysis.recommendationLabel}`
              : ""}
            {analysis.businessQualityScore != null
              ? ` · BQ ${formatScore(analysis.businessQualityScore)}`
              : ""}
          </p>
          {(analysis.status === "Running" || analysis.status === "Queued") && (
            <p className="mt-2 text-xs text-hap-info">
              Stage: {formatStageLabel(analysis.currentStage)}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {onOpenDeliverables ? (
            <button
              type="button"
              onClick={onOpenDeliverables}
              className="rounded border border-hap-orange/40 bg-hap-orange/10 px-3 py-2 text-xs font-semibold text-hap-orange transition-colors hover:border-hap-orange hover:bg-hap-orange/20"
            >
              Download deliverables
            </button>
          ) : null}
          <div className="text-right">
            <p className="text-xs uppercase tracking-wider text-hap-muted">Progress</p>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 w-32 overflow-hidden rounded-full bg-hap-border">
                <div
                  className="h-full rounded-full bg-hap-orange transition-all duration-500"
                  style={{ width: `${analysis.progress}%` }}
                />
              </div>
              <span className="font-mono text-sm">{analysis.progress}%</span>
            </div>
          </div>
          <StatusBadge status={analysis.status} />
        </div>
      </div>

      {analysis.pipelineError ? (
        <div className="mt-4 rounded border border-red-500/40 bg-red-500/10 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-red-400">
            Analysis failed
          </p>
          <p className="mt-1 text-sm text-red-300">{analysis.pipelineError}</p>
        </div>
      ) : null}
    </header>
  );
}
