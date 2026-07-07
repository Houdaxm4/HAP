"use client";

import { useCallback, useEffect, useState } from "react";
import FileUploadBox from "./FileUploadBox";
import type { NewAnalysisFormData } from "@/lib/types";

type NewAnalysisModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: NewAnalysisFormData) => void;
};

const ANALYSIS_TYPES: {
  value: NewAnalysisFormData["analysisType"];
  label: string;
  description: string;
}[] = [
  { value: "new_company", label: "New Company", description: "Full initiation coverage" },
  { value: "annual_update", label: "Annual Update", description: "Yearly model refresh" },
  { value: "quarterly_update", label: "Quarterly Update", description: "Q earnings update" },
];

const initialForm: NewAnalysisFormData = {
  companyName: "",
  ticker: "",
  analysisType: "new_company",
  prefilledWorkbook: null,
  previousWorkbook: null,
  customRunFilter: null,
  notes: "",
};

export default function NewAnalysisModal({
  isOpen,
  onClose,
  onSubmit,
}: NewAnalysisModalProps) {
  const [form, setForm] = useState<NewAnalysisFormData>(initialForm);
  const [errors, setErrors] = useState<Partial<Record<keyof NewAnalysisFormData, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetForm = useCallback(() => {
    setForm(initialForm);
    setErrors({});
    setIsSubmitting(false);
  }, []);

  const handleClose = useCallback(() => {
    resetForm();
    onClose();
  }, [onClose, resetForm]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, handleClose]);

  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  const validate = (): boolean => {
    const next: Partial<Record<keyof NewAnalysisFormData, string>> = {};
    if (!form.companyName.trim()) next.companyName = "Company name is required";
    if (!form.ticker.trim()) {
      next.ticker = "Ticker is required";
    } else if (!/^[A-Za-z]{1,5}$/.test(form.ticker.trim())) {
      next.ticker = "Enter a valid ticker (1–5 letters)";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    await new Promise((r) => setTimeout(r, 600));

    onSubmit({
      ...form,
      ticker: form.ticker.toUpperCase(),
    });

    resetForm();
    setIsSubmitting(false);
  };

  const update = <K extends keyof NewAnalysisFormData>(
    key: K,
    value: NewAnalysisFormData[K],
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-analysis-title"
        className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-hap-border bg-hap-panel shadow-2xl shadow-black/50"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-hap-border px-6 py-4">
          <div>
            <h2 id="new-analysis-title" className="text-lg font-semibold">
              New Analysis
            </h2>
            <p className="text-xs text-hap-muted">
              Configure and launch an investment analysis run
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded p-1.5 text-hap-muted transition-colors hover:bg-hap-border hover:text-foreground"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-6 py-5">
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="companyName" className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-hap-muted">
                    Company Name
                  </label>
                  <input
                    id="companyName"
                    type="text"
                    value={form.companyName}
                    onChange={(e) => update("companyName", e.target.value)}
                    placeholder="e.g. Apple Inc."
                    className={`w-full rounded-lg border bg-background px-3 py-2.5 text-sm transition-colors focus:outline-none focus:ring-1 ${
                      errors.companyName
                        ? "border-red-500/50 focus:border-red-500 focus:ring-red-500/30"
                        : "border-hap-border focus:border-hap-orange/50 focus:ring-hap-orange/30"
                    }`}
                  />
                  {errors.companyName && (
                    <p className="mt-1 text-xs text-red-400">{errors.companyName}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="ticker" className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-hap-muted">
                    Ticker
                  </label>
                  <input
                    id="ticker"
                    type="text"
                    value={form.ticker}
                    onChange={(e) => update("ticker", e.target.value.toUpperCase())}
                    placeholder="e.g. AAPL"
                    maxLength={5}
                    className={`w-full rounded-lg border bg-background px-3 py-2.5 font-mono text-sm uppercase transition-colors focus:outline-none focus:ring-1 ${
                      errors.ticker
                        ? "border-red-500/50 focus:border-red-500 focus:ring-red-500/30"
                        : "border-hap-border focus:border-hap-orange/50 focus:ring-hap-orange/30"
                    }`}
                  />
                  {errors.ticker && (
                    <p className="mt-1 text-xs text-red-400">{errors.ticker}</p>
                  )}
                </div>
              </div>

              <div>
                <span className="mb-2 block text-xs font-medium uppercase tracking-wider text-hap-muted">
                  Analysis Type
                </span>
                <div className="grid gap-2 sm:grid-cols-3">
                  {ANALYSIS_TYPES.map((type) => (
                    <button
                      key={type.value}
                      type="button"
                      onClick={() => update("analysisType", type.value)}
                      className={`rounded-lg border px-3 py-3 text-left transition-all ${
                        form.analysisType === type.value
                          ? "border-hap-orange bg-hap-orange/10 ring-1 ring-hap-orange/30"
                          : "border-hap-border bg-hap-panel-elevated hover:border-hap-border-bright"
                      }`}
                    >
                      <p className={`text-sm font-medium ${form.analysisType === type.value ? "text-hap-orange" : ""}`}>
                        {type.label}
                      </p>
                      <p className="mt-0.5 text-[10px] text-hap-muted">{type.description}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="mb-3 block text-xs font-medium uppercase tracking-wider text-hap-muted">
                  Workbooks &amp; Filters
                </span>
                <div className="grid gap-3 sm:grid-cols-3">
                  <FileUploadBox
                    label="Prefilled Workbook"
                    description=".xlsx, .xls"
                    file={form.prefilledWorkbook}
                    onFileChange={(f) => update("prefilledWorkbook", f)}
                  />
                  <FileUploadBox
                    label="Previous Workbook"
                    description=".xlsx, .xls"
                    file={form.previousWorkbook}
                    onFileChange={(f) => update("previousWorkbook", f)}
                  />
                  <FileUploadBox
                    label="custom_run_filter"
                    description=".csv, .xlsx"
                    file={form.customRunFilter}
                    onFileChange={(f) => update("customRunFilter", f)}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="notes" className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-hap-muted">
                  Notes
                </label>
                <textarea
                  id="notes"
                  value={form.notes}
                  onChange={(e) => update("notes", e.target.value)}
                  rows={3}
                  placeholder="Special instructions, assumptions, or context for this run..."
                  className="w-full resize-none rounded-lg border border-hap-border bg-background px-3 py-2.5 text-sm transition-colors focus:border-hap-orange/50 focus:outline-none focus:ring-1 focus:ring-hap-orange/30"
                />
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3 border-t border-hap-border px-6 py-4">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="rounded-lg border border-hap-border px-5 py-2.5 text-sm font-medium text-hap-muted transition-colors hover:border-hap-border-bright hover:bg-hap-panel-elevated hover:text-foreground disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex min-w-[140px] items-center justify-center gap-2 rounded-lg bg-hap-orange px-5 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-hap-orange-dim disabled:opacity-60"
            >
              {isSubmitting ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Starting...
                </>
              ) : (
                "Start Analysis"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
