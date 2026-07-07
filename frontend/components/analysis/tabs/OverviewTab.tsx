import type { AnalysisDetail } from "@/lib/types";

export default function OverviewTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {analysis.keyMetrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded border border-hap-border bg-hap-panel p-4"
          >
            <p className="text-xs uppercase tracking-wider text-hap-muted">
              {metric.label}
            </p>
            <p className="mt-1 font-mono text-xl font-semibold">{metric.value}</p>
            {metric.change && (
              <p className="mt-0.5 text-xs text-hap-success">{metric.change}</p>
            )}
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Investment Thesis
          </h3>
          <p className="mt-3 text-sm leading-relaxed text-foreground/90">
            {analysis.thesis}
          </p>
        </div>

        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Valuation
          </h3>
          <div className="mt-3 space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-hap-muted">Price Target</span>
              <span className="font-mono font-semibold text-hap-orange">
                {analysis.priceTarget}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-hap-muted">Rating</span>
              <span className="font-medium text-hap-success">{analysis.rating}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-hap-muted">Market Cap</span>
              <span className="font-mono">{analysis.marketCap}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
