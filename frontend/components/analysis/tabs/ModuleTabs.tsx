import type { AnalysisDetail, EngineModuleResult } from "@/lib/types";
import { formatMetricValue, formatScore, getModule } from "@/lib/map-backend-analysis";

function ModulePanel({
  title,
  module,
}: {
  title: string;
  module: EngineModuleResult | null;
}) {
  if (!module) {
    return <p className="text-sm text-hap-muted">{title} module result is not available.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Status</p>
          <p className="mt-1 text-lg font-semibold">{module.status}</p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Score</p>
          <p className="mt-1 font-mono text-2xl font-semibold">{formatScore(module.score)}</p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Confidence</p>
          <p className="mt-1 font-mono text-2xl font-semibold">
            {module.confidence == null ? "—" : module.confidence.toFixed(2)}
          </p>
        </div>
      </div>

      {module.error && (
        <p className="rounded border border-hap-border bg-hap-panel p-4 text-sm text-hap-muted">
          {module.error}
        </p>
      )}

      {(module.component_scores?.length ?? 0) > 0 && (
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Component Scores
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {module.component_scores!.map((component) => (
              <div key={component.code} className="rounded border border-hap-border/60 p-3">
                <p className="text-xs text-hap-muted">{component.label ?? component.code}</p>
                <p className="mt-1 font-mono text-lg font-semibold">
                  {formatScore(component.score)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">Metrics</h3>
        {(module.metrics?.length ?? 0) === 0 ? (
          <p className="mt-3 text-sm text-hap-muted">No metrics for this module.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
                  <th className="px-2 py-2 font-medium">Metric</th>
                  <th className="px-2 py-2 font-medium">Value</th>
                  <th className="px-2 py-2 font-medium">Period</th>
                </tr>
              </thead>
              <tbody>
                {module.metrics!.map((metric) => (
                  <tr key={`${metric.code}-${metric.period ?? ""}`} className="border-b border-hap-border/50">
                    <td className="px-2 py-2">{metric.label ?? metric.code}</td>
                    <td className="px-2 py-2 font-mono">{formatMetricValue(metric.value)}</td>
                    <td className="px-2 py-2 text-hap-muted">{metric.period ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">Findings</h3>
        <ul className="mt-3 space-y-2">
          {(module.findings?.length ?? 0) === 0 ? (
            <li className="text-sm text-hap-muted">None</li>
          ) : (
            module.findings!.map((finding) => (
              <li key={finding.finding_id} className="text-sm">
                <span className="text-hap-muted">[{finding.code}]</span> {finding.summary}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

export function ValuationTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <ModulePanel
      title="Valuation"
      module={getModule(analysis.engineResult, "valuation")}
    />
  );
}

export function ExpectedReturnTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <ModulePanel
      title="Expected Return"
      module={getModule(analysis.engineResult, "expected_return")}
    />
  );
}
