"use client";

import { useEffect, useState } from "react";
import { fetchValidationReport } from "@/lib/api";
import type { AnalysisRecord, ValidationReport } from "@/lib/types";

const checkStyles = {
  pass: "bg-hap-success/15 text-hap-success border-hap-success/30",
  warn: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  fail: "bg-red-500/15 text-red-400 border-red-500/30",
};

export default function VerificationTab({ analysis }: { analysis: AnalysisRecord }) {
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!analysis.outputs.validation_report) {
      setReport(null);
      return;
    }
    void fetchValidationReport(analysis.id)
      .then(setReport)
      .catch((err: Error) => setError(err.message));
  }, [analysis.id, analysis.outputs.validation_report]);

  if (!analysis.outputs.validation_report) {
    return (
      <p className="text-sm text-hap-muted">
        Validation report will appear after the validate_workbook stage completes.
      </p>
    );
  }

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>;
  }

  if (!report) {
    return <p className="text-sm text-hap-muted">Loading validation report...</p>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded border border-hap-border bg-hap-panel px-4 py-3 text-sm">
        <p>{report.summary}</p>
        <p className="mt-2 text-xs text-hap-muted">
          {report.pass_count} passed · {report.warn_count} warnings · {report.fail_count} failed
        </p>
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
              {check.concept} ({check.period}) — {check.cell_ref}
            </p>
            <p className="mt-1 text-sm text-hap-muted">{check.message}</p>
            {check.xbrl_tag && (
              <p className="mt-1 font-mono text-xs text-hap-muted">{check.xbrl_tag}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
