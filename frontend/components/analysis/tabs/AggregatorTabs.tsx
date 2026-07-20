import type { AnalysisDetail, EngineAggregatorResult } from "@/lib/types";
import { formatScore } from "@/lib/map-backend-analysis";

function AggregatorPanel({
  title,
  result,
}: {
  title: string;
  result: EngineAggregatorResult | null | undefined;
}) {
  if (!result) {
    return <p className="text-sm text-hap-muted">{title} result is not available.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Score</p>
          <p className="mt-1 font-mono text-2xl font-semibold">{formatScore(result.score)}</p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Classification</p>
          <p className="mt-1 text-lg font-semibold">{result.classification_label}</p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Confidence</p>
          <p className="mt-1 font-mono text-2xl font-semibold">
            {result.confidence == null ? "—" : result.confidence.toFixed(2)}
          </p>
        </div>
      </div>

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Module Contributions
        </h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
                <th className="px-2 py-2 font-medium">Module</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 font-medium">Score</th>
                <th className="px-2 py-2 font-medium">Weight</th>
              </tr>
            </thead>
            <tbody>
              {(result.module_contributions ?? []).map((item) => (
                <tr key={item.module_name} className="border-b border-hap-border/50">
                  <td className="px-2 py-2">{item.module_name}</td>
                  <td className="px-2 py-2 text-hap-muted">{item.status}</td>
                  <td className="px-2 py-2 font-mono">{formatScore(item.score)}</td>
                  <td className="px-2 py-2 font-mono">
                    {item.effective_weight != null
                      ? item.effective_weight.toFixed(2)
                      : item.weight.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Strengths
          </h3>
          <ul className="mt-3 space-y-2">
            {(result.strengths ?? []).length === 0 ? (
              <li className="text-sm text-hap-muted">None</li>
            ) : (
              (result.strengths ?? []).map((item) => (
                <li key={item.finding_id} className="text-sm">
                  {item.summary}
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Weaknesses
          </h3>
          <ul className="mt-3 space-y-2">
            {(result.weaknesses ?? []).length === 0 ? (
              <li className="text-sm text-hap-muted">None</li>
            ) : (
              (result.weaknesses ?? []).map((item) => (
                <li key={item.risk_id} className="text-sm">
                  {item.summary}
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function BusinessQualityTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <AggregatorPanel
      title="Business Quality"
      result={analysis.engineResult?.business_quality}
    />
  );
}

export function InvestmentAttractivenessTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <AggregatorPanel
      title="Investment Attractiveness"
      result={analysis.engineResult?.investment_attractiveness}
    />
  );
}
