"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchCustomRunValidation } from "@/lib/api";
import type { AnalysisRecord, CustomRunValidationReport } from "@/lib/types";

const checkStyles = {
  pass: "bg-hap-success/15 text-hap-success border-hap-success/30",
  warn: "bg-hap-warning/15 text-hap-warning border-hap-warning/30",
  fail: "bg-red-500/15 text-red-300 border-red-500/30",
  pending: "bg-hap-muted/15 text-hap-muted border-hap-muted/30",
};

const CHECK_LABELS: Record<string, string> = {
  required_columns: "Required columns",
  ticker: "Ticker",
  fiscal_dates: "Fiscal dates",
  quarter_sequence: "Quarter sequence",
  duplicate_periods: "Duplicate periods",
  missing_quarters: "Missing quarters",
  numeric_consistency: "Numeric consistency",
  workbook_reference: "Workbook references",
};

export default function VerificationTab({ analysis }: { analysis: AnalysisRecord }) {
  const [report, setReport] = useState<CustomRunValidationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canLoad =
    Boolean(analysis.outputs.custom_run_validation_report) ||
    analysis.stagesCompleted.includes("custom_run_filter_validated") ||
    analysis.files.custom_run_filter != null;

  useEffect(() => {
    if (!canLoad) return;

    let cancelled = false;
    void fetchCustomRunValidation(analysis.id)
      .then((payload) => {
        if (cancelled) return;
        setReport(payload);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Failed to load custom_run validation report.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [
    analysis.id,
    analysis.outputs.custom_run_validation_report,
    analysis.stagesCompleted,
    canLoad,
  ]);

  if (!canLoad) {
    return (
      <p className="text-sm text-hap-muted">
        Upload a custom_run_filter to generate a validation report.
      </p>
    );
  }

  if (!report && !error) {
    return <p className="text-sm text-hap-muted">Loading custom_run_filter validation...</p>;
  }

  if (error && !report) {
    return (
      <p className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
        {error}
      </p>
    );
  }

  if (!report) {
    return <p className="text-sm text-hap-muted">No verification checks yet.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
              custom_run_filter Validation
            </h3>
            <p className="mt-2 text-sm text-foreground/90">{report.summary}</p>
            <p className="mt-1 text-xs text-hap-muted">
              Source: {report.source_filename} · {report.entry_count} rows · ticker{" "}
              <span className="font-mono text-hap-orange">{report.ticker}</span>
            </p>
          </div>
          <div className="flex gap-2 text-xs">
            <span className={`rounded border px-2 py-1 ${checkStyles.pass}`}>
              {report.pass_count} pass
            </span>
            <span className={`rounded border px-2 py-1 ${checkStyles.warn}`}>
              {report.warn_count} warn
            </span>
            <span className={`rounded border px-2 py-1 ${checkStyles.fail}`}>
              {report.fail_count} fail
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {report.checks.map((check, index) => (
          <div
            key={`${check.check_type}-${index}`}
            className="flex items-start gap-4 rounded border border-hap-border bg-hap-panel p-4"
          >
            <span
              className={`shrink-0 rounded border px-2 py-0.5 text-xs font-medium uppercase ${checkStyles[check.status]}`}
            >
              {check.status}
            </span>
            <div className="min-w-0">
              <p className="font-medium">
                {CHECK_LABELS[check.check_type] ?? check.check_type}
              </p>
              <p className="mt-1 text-sm text-hap-muted">{check.message}</p>
              {(check.concept || check.period || check.cell_ref || check.row_number) && (
                <p className="mt-1 font-mono text-[11px] text-hap-muted">
                  {[
                    check.concept ? `concept=${check.concept}` : null,
                    check.period ? `period=${check.period}` : null,
                    check.cell_ref ? `cell=${check.cell_ref}` : null,
                    check.row_number ? `row=${check.row_number}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {analysis.verificationChecks.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Pipeline Checks
          </h3>
          {analysis.verificationChecks.map((check) => (
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
          ))}
        </div>
      )}
    </div>
  );
}
