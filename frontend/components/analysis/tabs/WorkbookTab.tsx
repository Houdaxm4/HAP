"use client";

import { useEffect, useState } from "react";
import {
  artifactUrl,
  fetchCellProvenance,
  fetchWorkbookStructure,
} from "@/lib/api";
import type { AnalysisRecord, CellProvenance, WorkbookStructure } from "@/lib/types";
import PipelineStages from "../PipelineStages";

const ARTIFACTS = [
  { key: "completed_workbook", filename: "completed_workbook.xlsx", label: "Completed Workbook" },
  { key: "provenance_report", filename: "provenance_report.json", label: "Provenance Report" },
  { key: "validation_report", filename: "validation_report.json", label: "Validation Report" },
  { key: "discrepancy_report", filename: "discrepancy_report.json", label: "Discrepancy Report" },
] as const;

export default function WorkbookTab({ analysis }: { analysis: AnalysisRecord }) {
  const [structure, setStructure] = useState<WorkbookStructure | null>(null);
  const [worksheet, setWorksheet] = useState("");
  const [cell, setCell] = useState("");
  const [provenance, setProvenance] = useState<CellProvenance | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [isLookingUp, setIsLookingUp] = useState(false);

  const hasWorkbook = Boolean(analysis.outputs.completed_workbook);

  useEffect(() => {
    if (!analysis.outputs.workbook_structure) {
      setStructure(null);
      return;
    }
    void fetchWorkbookStructure(analysis.id)
      .then(setStructure)
      .catch(() => setStructure(null));
  }, [analysis.id, analysis.outputs.workbook_structure]);

  const handleLookup = async () => {
    if (!worksheet.trim() || !cell.trim()) {
      setLookupError("Enter both worksheet and cell.");
      return;
    }
    setIsLookingUp(true);
    setLookupError(null);
    setProvenance(null);
    try {
      const result = await fetchCellProvenance(analysis.id, worksheet.trim(), cell.trim());
      setProvenance(result);
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : "Provenance lookup failed.");
    } finally {
      setIsLookingUp(false);
    }
  };

  return (
    <div className="space-y-6">
      <PipelineStages analysis={analysis} />

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Pipeline Artifacts
        </h3>
        <ul className="mt-4 space-y-2">
          {ARTIFACTS.map((artifact) => {
            const available = Boolean(
              analysis.outputs[artifact.key as keyof typeof analysis.outputs],
            );
            return (
              <li
                key={artifact.filename}
                className="flex items-center justify-between rounded border border-hap-border px-3 py-2 text-sm"
              >
                <span>{artifact.label}</span>
                {available ? (
                  <a
                    href={artifactUrl(analysis.id, artifact.filename)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-hap-orange hover:underline"
                  >
                    Download
                  </a>
                ) : (
                  <span className="text-xs text-hap-muted">Not available yet</span>
                )}
              </li>
            );
          })}
        </ul>

        {hasWorkbook ? (
          <a
            href={artifactUrl(analysis.id, "completed_workbook.xlsx")}
            className="mt-4 inline-flex rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange transition-colors hover:bg-hap-orange/20"
          >
            Download Completed Workbook
          </a>
        ) : (
          <p className="mt-4 text-sm text-hap-muted">
            Workbook download will be enabled when the backend finishes filling the workbook.
          </p>
        )}
      </div>

      {structure && (
        <div className="overflow-hidden rounded border border-hap-border bg-hap-panel">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
                <th className="px-4 py-3 font-medium">Sheet</th>
                <th className="px-4 py-3 font-medium">Visibility</th>
              </tr>
            </thead>
            <tbody>
              {structure.visible_sheets.map((name) => (
                <tr key={name} className="border-b border-hap-border/50">
                  <td className="px-4 py-3 font-medium">{name}</td>
                  <td className="px-4 py-3 text-hap-success">visible</td>
                </tr>
              ))}
              {structure.hidden_sheets.map((name) => (
                <tr key={name} className="border-b border-hap-border/50">
                  <td className="px-4 py-3 font-medium">{name}</td>
                  <td className="px-4 py-3 text-hap-warning">hidden</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Cell Provenance Lookup
        </h3>
        <p className="mt-2 text-sm text-hap-muted">
          Query explainability for any mapped cell, e.g. Income Statement / B5.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_120px_auto]">
          <input
            value={worksheet}
            onChange={(e) => setWorksheet(e.target.value)}
            placeholder="Worksheet"
            className="rounded border border-hap-border bg-background px-3 py-2 text-sm"
          />
          <input
            value={cell}
            onChange={(e) => setCell(e.target.value.toUpperCase())}
            placeholder="Cell"
            className="rounded border border-hap-border bg-background px-3 py-2 font-mono text-sm uppercase"
          />
          <button
            type="button"
            onClick={() => void handleLookup()}
            disabled={isLookingUp || !analysis.outputs.provenance_report}
            className="rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2 text-sm font-medium text-hap-orange disabled:opacity-50"
          >
            {isLookingUp ? "Looking up..." : "Lookup"}
          </button>
        </div>
        {!analysis.outputs.provenance_report && (
          <p className="mt-2 text-xs text-hap-muted">
            Provenance lookup is available after the fill_workbook stage completes.
          </p>
        )}
        {lookupError && <p className="mt-3 text-sm text-red-400">{lookupError}</p>}
        {provenance && (
          <dl className="mt-4 space-y-2 rounded border border-hap-border px-4 py-3 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Cell</dt>
              <dd className="font-mono">{provenance.cell_ref}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Value</dt>
              <dd className="font-mono">{String(provenance.value ?? "—")}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Filing</dt>
              <dd>{provenance.filing_type ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">XBRL tag</dt>
              <dd className="font-mono text-xs">{provenance.xbrl_tag ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Confidence</dt>
              <dd>{provenance.confidence != null ? `${Math.round(provenance.confidence * 100)}%` : "—"}</dd>
            </div>
            <div>
              <dt className="text-hap-muted">Source</dt>
              <dd className="mt-1 break-all text-xs">
                {provenance.source_document ? (
                  <a
                    href={provenance.source_document}
                    target="_blank"
                    rel="noreferrer"
                    className="text-hap-orange hover:underline"
                  >
                    {provenance.source_document}
                  </a>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-hap-muted">Reasoning</dt>
              <dd className="mt-1 text-hap-muted">{provenance.reasoning ?? provenance.failure_reason ?? "—"}</dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  );
}
