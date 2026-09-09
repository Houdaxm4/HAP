"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getOutputDownloadUrl,
  listAnalysisOutputs,
  type OutputArtifactDto,
} from "@/lib/api";
import { formatBytes } from "@/lib/map-backend-analysis";
import type { AnalysisDetail } from "@/lib/types";

const EXCEL_EXT = /\.(xlsx|xlsm|xls)$/i;
const WORD_EXT = /\.(docx|doc)$/i;

const GENERIC_WORKBOOK_NAMES = new Set([
  "completed_workbook.xlsx",
  "hap_workbook.xlsx",
]);

function isOfficeDeliverable(name: string): boolean {
  return EXCEL_EXT.test(name) || WORD_EXT.test(name);
}

function isExcel(name: string): boolean {
  return EXCEL_EXT.test(name);
}

function isWord(name: string): boolean {
  return WORD_EXT.test(name);
}

function preferNamedWorkbooks(artifacts: OutputArtifactDto[]): OutputArtifactDto[] {
  const office = artifacts.filter((a) => isOfficeDeliverable(a.name));
  const hasNamedExcel = office.some(
    (a) => isExcel(a.name) && !GENERIC_WORKBOOK_NAMES.has(a.name.toLowerCase()),
  );
  if (!hasNamedExcel) return office;
  return office.filter((a) => !GENERIC_WORKBOOK_NAMES.has(a.name.toLowerCase()));
}

function sortOffice(artifacts: OutputArtifactDto[]): OutputArtifactDto[] {
  return [...artifacts].sort((a, b) => {
    const ae = isExcel(a.name) ? 0 : 1;
    const be = isExcel(b.name) ? 0 : 1;
    if (ae !== be) return ae - be;
    return a.name.localeCompare(b.name);
  });
}

function describe(name: string): string {
  const lower = name.toLowerCase();
  if (isWord(name)) {
    if (lower.includes("quarter")) return "Quarterly update memo";
    if (lower.includes("annual")) return "Annual update memo";
    return "Research and recommendation memo";
  }
  if (lower.includes("fa") || /\d{4}\s+[a-z]{1,5}\s+fa/i.test(name)) {
    return "Finished financial model";
  }
  if (GENERIC_WORKBOOK_NAMES.has(lower)) {
    return "Completed financial model";
  }
  return "Excel workbook";
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
          setArtifacts(listed);
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

  const files = useMemo(() => sortOffice(preferNamedWorkbooks(artifacts)), [artifacts]);
  const excel = files.filter((f) => isExcel(f.name));
  const word = files.filter((f) => isWord(f.name));

  if (isLoading) {
    return <p className="text-sm text-hap-muted">Loading deliverables…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>;
  }

  if (files.length === 0) {
    return (
      <p className="text-sm text-hap-muted">
        {analysis.status === "Failed"
          ? "No Excel or Word files were produced before this run failed."
          : "Excel and Word files appear here when the run finishes."}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Files for this run
        </h3>
        <p className="mt-1 text-sm text-hap-muted">
          Download the completed workbook and the accompanying Word memo.
        </p>
      </div>

      {excel.length > 0 ? (
        <FileGroup title="Excel" files={excel} analysisId={analysis.id} />
      ) : null}
      {word.length > 0 ? (
        <FileGroup title="Word" files={word} analysisId={analysis.id} />
      ) : null}
    </div>
  );
}

function FileGroup({
  title,
  files,
  analysisId,
}: {
  title: string;
  files: OutputArtifactDto[];
  analysisId: string;
}) {
  return (
    <div>
      <h4 className="mb-3 text-sm font-medium">{title}</h4>
      <div className="grid gap-3 sm:grid-cols-2">
        {files.map((file) => (
          <a
            key={file.name}
            href={getOutputDownloadUrl(analysisId, file.name)}
            download={file.name}
            className="flex items-start justify-between gap-4 rounded-xl border border-hap-border bg-hap-panel p-4 transition-colors hover:border-hap-orange/40 hover:bg-hap-panel-elevated"
          >
            <div>
              <p className="text-sm font-medium">{file.name}</p>
              <p className="mt-1 text-xs text-hap-muted">{describe(file.name)}</p>
              <p className="mt-2 font-mono text-[11px] text-hap-muted">
                {formatBytes(file.size_bytes)}
              </p>
            </div>
            <span className="shrink-0 rounded border border-hap-orange/40 bg-hap-orange/10 px-3 py-1.5 text-xs font-semibold text-hap-orange">
              Download
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
