import type { AnalysisDetail } from "@/lib/types";

const checkStyles = {
  pass: "bg-hap-success/15 text-hap-success border-hap-success/30",
  warn: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  fail: "bg-red-500/15 text-red-400 border-red-500/30",
  pending: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
};

export default function VerificationTab({ analysis }: { analysis: AnalysisDetail }) {
  const report = analysis.validationReport;
  const comparisons = analysis.engineResult?.metric_comparisons ?? [];

  if (!report && comparisons.length === 0) {
    return (
      <p className="text-sm text-hap-muted">
        Verification data is not available yet.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {report && (
        <div className="space-y-3">
          <div className="rounded border border-hap-border bg-hap-panel p-4 text-sm text-hap-muted">
            {report.summary ||
              `Pass ${report.pass_count} · Warn ${report.warn_count} · Fail ${report.fail_count}`}
          </div>
          {report.checks.map((check) => (
            <div
              key={`${check.cell_ref}-${check.check_type}`}
              className="flex items-start gap-4 rounded border border-hap-border bg-hap-panel p-4"
            >
              <span
                className={`shrink-0 rounded border px-2 py-0.5 text-xs font-medium uppercase ${checkStyles[check.status]}`}
              >
                {check.status}
              </span>
              <div>
                <p className="font-medium">
                  {check.concept} · {check.cell_ref}
                </p>
                <p className="mt-1 text-sm text-hap-muted">{check.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {comparisons.length > 0 && (
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Metric Comparisons
          </h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
                  <th className="px-2 py-2 font-medium">Metric</th>
                  <th className="px-2 py-2 font-medium">Workbook</th>
                  <th className="px-2 py-2 font-medium">HAP</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {comparisons.map((item, index) => (
                  <tr key={`${item.metric_code}-${index}`} className="border-b border-hap-border/50">
                    <td className="px-2 py-2">{item.metric_code}</td>
                    <td className="px-2 py-2 font-mono">{String(item.workbook_value ?? "—")}</td>
                    <td className="px-2 py-2 font-mono">{String(item.hap_value ?? "—")}</td>
                    <td className="px-2 py-2 text-hap-muted">{item.status ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
