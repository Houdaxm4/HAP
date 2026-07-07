import type { AnalysisDetail } from "@/lib/types";

export default function SummaryTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <div className="rounded border border-hap-border bg-hap-panel p-6">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
        Executive Summary
      </h3>
      <p className="mt-4 text-sm leading-relaxed text-foreground/90">
        {analysis.executiveSummary}
      </p>
      <div className="mt-6 flex gap-3">
        <button className="rounded border border-hap-border px-4 py-2 text-sm text-hap-muted transition-colors hover:border-hap-border-bright hover:text-foreground">
          Export PDF
        </button>
        <button className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange transition-colors hover:bg-hap-orange/20">
          Approve &amp; Publish
        </button>
      </div>
    </div>
  );
}
