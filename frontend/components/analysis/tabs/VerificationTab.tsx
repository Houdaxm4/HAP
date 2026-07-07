import type { AnalysisDetail } from "@/lib/types";

const checkStyles = {
  pass: "bg-hap-success/15 text-hap-success border-hap-success/30",
  warn: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  pending: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
};

export default function VerificationTab({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <div className="space-y-3">
      {analysis.verificationChecks.length === 0 ? (
        <p className="text-sm text-hap-muted">No verification checks yet.</p>
      ) : (
        analysis.verificationChecks.map((check) => (
          <div
            key={check.id}
            className="flex items-start gap-4 rounded border border-hap-border bg-hap-panel p-4"
          >
            <span
              className={`shrink-0 rounded border px-2 py-0.5 text-xs font-medium uppercase ${checkStyles[check.status]}`}
            >
              {check.status}
            </span>
            <div>
              <p className="font-medium">{check.label}</p>
              <p className="mt-1 text-sm text-hap-muted">{check.detail}</p>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
