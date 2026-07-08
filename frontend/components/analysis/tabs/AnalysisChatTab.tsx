import type { AnalysisRecord } from "@/lib/types";

export default function AnalysisChatTab({ analysis }: { analysis: AnalysisRecord }) {
  return (
    <div className="rounded border border-hap-border bg-hap-panel p-6 text-sm text-hap-muted">
      Per-analysis chat will connect to the HAP Analyst agent after fundamental analysis
      is implemented. Current pipeline status:{" "}
      <span className="text-foreground">{analysis.displayStatus}</span>.
    </div>
  );
}
