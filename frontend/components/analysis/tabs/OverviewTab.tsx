import type { AnalysisDetail } from "@/lib/types";
import { formatMetricValue, formatScore } from "@/lib/map-backend-analysis";

export default function OverviewTab({ analysis }: { analysis: AnalysisDetail }) {
  const engine = analysis.engineResult;
  const recommendation = engine?.recommendation;
  const metrics = engine?.metrics?.slice(0, 8) ?? [];

  if (!engine) {
    return (
      <div className="space-y-4">
        {analysis.pipelineError ? (
          <div className="rounded border border-red-500/40 bg-red-500/10 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-red-400">
              Pipeline failed
            </p>
            <p className="mt-1 text-sm text-red-300">{analysis.pipelineError}</p>
          </div>
        ) : null}
        <p className="text-sm text-hap-muted">
          {analysis.status === "Complete"
            ? "Analysis engine result is not available yet."
            : analysis.status === "Failed"
              ? "No overview is available because the analysis failed."
              : `Pipeline in progress (${analysis.progress}%). Overview will populate when analysis completes.`}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Recommendation</p>
          <p className="mt-1 text-xl font-semibold text-hap-orange">
            {recommendation?.recommendation_label ?? analysis.recommendationLabel ?? "—"}
          </p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Business Quality</p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {formatScore(engine.business_quality?.score)}
          </p>
          <p className="mt-0.5 text-xs text-hap-muted">
            {engine.business_quality?.classification_label ?? "—"}
          </p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">
            Investment Attractiveness
          </p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {formatScore(engine.investment_attractiveness?.score)}
          </p>
          <p className="mt-0.5 text-xs text-hap-muted">
            {engine.investment_attractiveness?.classification_label ?? "—"}
          </p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Confidence</p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {engine.confidence == null ? "—" : engine.confidence.toFixed(2)}
          </p>
        </div>
      </div>

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Key Metrics
        </h3>
        {metrics.length === 0 ? (
          <p className="mt-3 text-sm text-hap-muted">No metrics available from the engine result.</p>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map((metric) => (
              <div key={`${metric.code}-${metric.period ?? ""}`} className="rounded border border-hap-border/60 p-3">
                <p className="text-xs text-hap-muted">{metric.name ?? metric.label ?? metric.code}</p>
                <p className="mt-1 font-mono text-lg font-semibold">
                  {formatMetricValue(metric.value)}
                </p>
                {metric.period && (
                  <p className="mt-0.5 text-[10px] text-hap-muted">{metric.period}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
