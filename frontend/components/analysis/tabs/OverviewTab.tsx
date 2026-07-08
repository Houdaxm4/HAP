"use client";

import { useEffect, useState } from "react";
import type { AnalysisRecord } from "@/lib/types";
import PipelineStages from "../PipelineStages";

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function OverviewTab({ analysis }: { analysis: AnalysisRecord }) {
  const [backendReachable, setBackendReachable] = useState(true);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_HAP_API_URL ?? "http://127.0.0.1:8000";
    void fetch(`${base}/health`)
      .then((response) => setBackendReachable(response.ok))
      .catch(() => setBackendReachable(false));
  }, []);

  const uploadedFiles = [
    analysis.files.prefilled_workbook,
    analysis.files.previous_workbook,
    analysis.files.custom_run_filter,
  ].filter(Boolean);

  return (
    <div className="space-y-6">
      {!backendReachable && (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          Backend is not reachable. Start the HAP API before running analyses.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Pipeline Status
          </h3>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Display status</dt>
              <dd className="font-medium">{analysis.displayStatus}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Backend state</dt>
              <dd className="font-mono text-xs">{analysis.pipelineState}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Started</dt>
              <dd>{formatTimestamp(analysis.startedAt)}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-hap-muted">Last updated</dt>
              <dd>{formatTimestamp(analysis.updatedAt)}</dd>
            </div>
          </dl>
        </div>

        <PipelineStages analysis={analysis} />
      </div>

      <div className="rounded border border-hap-border bg-hap-panel p-5">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
          Uploaded Files
        </h3>
        {uploadedFiles.length === 0 ? (
          <p className="mt-3 text-sm text-hap-muted">No files uploaded yet.</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {uploadedFiles.map((file) => (
              <li
                key={file!.stored_filename}
                className="flex items-center justify-between rounded border border-hap-border px-3 py-2 text-sm"
              >
                <span>{file!.filename}</span>
                <span className="text-xs text-hap-muted">{formatFileSize(file!.size_bytes)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
