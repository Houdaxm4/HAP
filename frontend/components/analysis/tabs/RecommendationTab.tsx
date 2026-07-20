import type { AnalysisDetail } from "@/lib/types";
import { formatScore } from "@/lib/map-backend-analysis";

export default function RecommendationTab({ analysis }: { analysis: AnalysisDetail }) {
  const recommendation = analysis.engineResult?.recommendation;

  if (!recommendation) {
    return (
      <p className="text-sm text-hap-muted">
        Recommendation is not available until the analysis engine completes.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Recommendation</p>
          <p className="mt-1 text-xl font-semibold text-hap-orange">
            {recommendation.recommendation_label}
          </p>
          <p className="mt-0.5 font-mono text-xs text-hap-muted">{recommendation.recommendation}</p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Confidence</p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {recommendation.confidence == null ? "—" : recommendation.confidence.toFixed(2)}
          </p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">Business Quality</p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {formatScore(recommendation.business_quality_score)}
          </p>
          <p className="mt-0.5 text-xs text-hap-muted">
            {recommendation.business_quality_classification}
          </p>
        </div>
        <div className="rounded border border-hap-border bg-hap-panel p-4">
          <p className="text-xs uppercase tracking-wider text-hap-muted">
            Investment Attractiveness
          </p>
          <p className="mt-1 font-mono text-xl font-semibold">
            {formatScore(recommendation.investment_attractiveness_score)}
          </p>
          <p className="mt-0.5 text-xs text-hap-muted">
            {recommendation.investment_attractiveness_classification}
          </p>
        </div>
      </div>

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Structured Reasons
        </h3>
        <ul className="mt-3 space-y-3">
          {(recommendation.reasons ?? []).length === 0 ? (
            <li className="text-sm text-hap-muted">No reasons recorded.</li>
          ) : (
            (recommendation.reasons ?? []).map((reason) => (
              <li key={reason.reason_id} className="rounded border border-hap-border/60 p-3">
                <p className="text-xs uppercase tracking-wider text-hap-muted">
                  {reason.category} · {reason.code}
                </p>
                <p className="mt-1 text-sm">{reason.summary}</p>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
