"use client";

import { useEffect, useState } from "react";
import {
  getOutputDownloadUrl,
  listAnalysisOutputs,
  type OutputArtifactDto,
} from "@/lib/api";
import { formatBytes } from "@/lib/map-backend-analysis";
import type { AnalysisDetail } from "@/lib/types";

const PRIORITY_ORDER = [
  "hap_workbook.xlsx",
  "completed_workbook.xlsx",
  "analysis_engine_result.json",
  "company_financial_model.json",
  "validation_report.json",
  "discrepancy_report.json",
  "provenance_report.json",
  "custom_run_data.json",
  "sec_filings_manifest.json",
  "company_facts.json",
  "workbook_structure.json",
];

const DESCRIPTIONS: Record<string, string> = {
  "completed_workbook.xlsx": "Industrial Template copy (preserved input workbook)",
  "hap_workbook.xlsx": "HAP institutional workbook (17-sheet standard deliverable)",
  "analysis_engine_result.json": "Full Analysis Engine result (modules, scores, recommendation)",
  "company_financial_model.json": "Canonical CompanyFinancialModel",
  "validation_report.json": "Validation checks (pass / warn / fail)",
  "discrepancy_report.json": "Discrepancy report (same validation payload today)",
  "provenance_report.json": "SEC + Custom Run provenance for imported values",
  "custom_run_data.json": "Parsed Custom_Run_Filter data",
  "sec_filings_manifest.json": "SEC filings selected for this run",
  "company_facts.json": "Raw SEC companyfacts JSON",
  "workbook_structure.json": "Parsed Industrial Template structure (can be very large)",
};

function sortArtifacts(artifacts: OutputArtifactDto[]): OutputArtifactDto[] {
  return [...artifacts].sort((a, b) => {
    const ai = PRIORITY_ORDER.indexOf(a.name);
    const bi = PRIORITY_ORDER.indexOf(b.name);
    if (ai === -1 && bi === -1) {
      return a.name.localeCompare(b.name);
    }
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

export default function DeliverablesTab({ analysis }: { analysis: AnalysisDetail }) {
  const [artifacts, setArtifacts] = useState<OutputArtifactDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const listed = await listAnalysisOutputs(analysis.id);
        if (!cancelled) {
          setArtifacts(sortArtifacts(listed));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to list deliverables.");
          setArtifacts([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [analysis.id, analysis.status, analysis.progress]);

  if (isLoading) {
    return <p className="text-sm text-hap-muted">Loading deliverables…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>;
  }

  if (artifacts.length === 0) {
    return (
      <p className="text-sm text-hap-muted">
        {analysis.status === "Failed"
          ? "No artifacts were written before the pipeline failed."
          : "No deliverables yet. They appear as each pipeline stage completes."}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Downloadable artifacts
        </h3>
        <p className="mt-1 text-sm text-hap-muted">
          Inspect every output the backend already produced for this analysis.
        </p>
      </div>

      <div className="overflow-hidden rounded border border-hap-border bg-hap-panel">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
              <th className="px-4 py-3 font-medium">Artifact</th>
              <th className="px-4 py-3 font-medium">Size</th>
              <th className="px-4 py-3 font-medium">Description</th>
              <th className="px-4 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {artifacts.map((artifact) => {
              const large = artifact.size_bytes > 50 * 1024 * 1024;
              return (
                <tr
                  key={artifact.name}
                  className="border-b border-hap-border/50 align-top"
                >
                  <td className="px-4 py-3 font-mono text-xs text-hap-orange">
                    {artifact.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-hap-muted">
                    {formatBytes(artifact.size_bytes)}
                    {large ? (
                      <span className="mt-1 block text-[10px] text-hap-warning">
                        Large file
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-hap-muted">
                    {DESCRIPTIONS[artifact.name] ?? "Pipeline output artifact"}
                  </td>
                  <td className="px-4 py-3">
                    <a
                      href={getOutputDownloadUrl(analysis.id, artifact.name)}
                      download={artifact.name}
                      className="inline-flex rounded border border-hap-orange/40 bg-hap-orange/10 px-3 py-1.5 text-xs font-semibold text-hap-orange transition-colors hover:border-hap-orange hover:bg-hap-orange/20"
                    >
                      Download
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
