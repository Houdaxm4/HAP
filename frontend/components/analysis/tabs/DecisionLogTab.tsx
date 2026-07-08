import type { AnalysisRecord } from "@/lib/types";

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function DecisionLogTab({ analysis }: { analysis: AnalysisRecord }) {
  if (analysis.decisionLog.length === 0) {
    return (
      <p className="text-sm text-hap-muted">
        Decision log entries will appear as backend agents complete pipeline stages.
      </p>
    );
  }

  return (
    <div className="space-y-0">
      {analysis.decisionLog.map((entry, i) => (
        <div key={entry.id} className="flex gap-4">
          <div className="flex flex-col items-center">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-hap-border bg-hap-panel-elevated text-[10px] font-medium text-hap-orange">
              {entry.agent.slice(0, 2).toUpperCase()}
            </div>
            {i < analysis.decisionLog.length - 1 && (
              <div className="w-px flex-1 bg-hap-border" />
            )}
          </div>
          <div className="pb-6">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{entry.action}</span>
              <span className="text-xs text-hap-muted">{formatTimestamp(entry.timestamp)}</span>
              {entry.confidence != null && (
                <span className="text-xs text-hap-muted">
                  · {Math.round(entry.confidence * 100)}% confidence
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-hap-orange">{entry.agent}</p>
            <p className="mt-1 text-sm text-hap-muted">{entry.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
