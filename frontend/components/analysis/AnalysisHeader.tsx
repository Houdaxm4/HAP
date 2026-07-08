"use client";

import Link from "next/link";
import type { AnalysisRecord } from "@/lib/types";
import { stageLabel } from "@/lib/pipeline-stages";
import StatusBadge from "../StatusBadge";

type AnalysisHeaderProps = {
  analysis: AnalysisRecord;
};

export default function AnalysisHeader({ analysis }: AnalysisHeaderProps) {
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
            {analysis.type} &middot; {stageLabel(analysis.currentStage)}
          </p>
        </div>

        <div className="flex items-center gap-4">
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
          <StatusBadge status={analysis.displayStatus} />
        </div>
      </div>
    </header>
  );
}
