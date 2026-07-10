"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchWorkbookStructure } from "@/lib/api";
import type { AnalysisRecord, WorkbookStructure } from "@/lib/types";

const visibilityStyles = {
  visible: "text-hap-success",
  hidden: "text-hap-warning",
  veryHidden: "text-red-400",
};

export default function WorkbookTab({ analysis }: { analysis: AnalysisRecord }) {
  const [structure, setStructure] = useState<WorkbookStructure | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canLoad =
    Boolean(analysis.outputs.workbook_structure) ||
    analysis.stagesCompleted.includes("workbook_parsed") ||
    analysis.files.prefilled_workbook != null;

  useEffect(() => {
    if (!canLoad) return;

    let cancelled = false;

    void fetchWorkbookStructure(analysis.id)
      .then((payload) => {
        if (cancelled) return;
        setStructure(payload);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Failed to load workbook structure.";
        setError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [analysis.id, analysis.outputs.workbook_structure, analysis.stagesCompleted, canLoad]);

  if (!canLoad) {
    return (
      <p className="text-sm text-hap-muted">
        Upload a workbook to generate structure metadata.
      </p>
    );
  }

  if (!structure && !error) {
    return <p className="text-sm text-hap-muted">Parsing workbook metadata...</p>;
  }

  if (error && !structure) {
    return (
      <p className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
        {error}
      </p>
    );
  }

  if (!structure) {
    return <p className="text-sm text-hap-muted">Workbook structure not available yet.</p>;
  }

  const metadataEntries = [
    ["Filename", structure.workbook_filename],
    ["Title", structure.metadata.title],
    ["Creator", structure.metadata.creator],
    ["Modified", structure.metadata.modified],
    ["Sheets", String(structure.metadata.sheet_count)],
    ["Named ranges", String(structure.metadata.defined_name_count)],
    ["Formula cells", String(structure.formula_count)],
    ["Editable cells", String(structure.editable_cell_count)],
  ].filter(([, value]) => value);

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Sheets", value: structure.worksheet_names.length },
          { label: "Hidden", value: structure.hidden_sheets.length },
          { label: "Formulas", value: structure.formula_count },
          { label: "Editable", value: structure.editable_cell_count },
        ].map((stat) => (
          <div key={stat.label} className="rounded border border-hap-border bg-hap-panel p-4">
            <p className="text-xs uppercase tracking-wider text-hap-muted">{stat.label}</p>
            <p className="mt-1 font-mono text-xl font-semibold">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Workbook Metadata
          </h3>
          <dl className="mt-3 space-y-2 text-sm">
            {metadataEntries.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4">
                <dt className="text-hap-muted">{label}</dt>
                <dd className="truncate font-mono text-right">{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="rounded border border-hap-border bg-hap-panel p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Named Ranges
          </h3>
          {structure.named_ranges.length === 0 ? (
            <p className="mt-3 text-sm text-hap-muted">No named ranges detected.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {structure.named_ranges.map((range) => (
                <li key={range.name} className="flex justify-between gap-3">
                  <span className="font-medium">{range.name}</span>
                  <span className="truncate font-mono text-xs text-hap-muted">
                    {range.destinations.join(", ") || range.attr_text || "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="overflow-hidden rounded border border-hap-border bg-hap-panel">
        <div className="border-b border-hap-border px-4 py-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">
            Worksheets
          </h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-hap-border text-left text-xs uppercase tracking-wider text-hap-muted">
              <th className="px-4 py-3 font-medium">Sheet</th>
              <th className="px-4 py-3 font-medium">Visibility</th>
              <th className="px-4 py-3 font-medium">Range</th>
              <th className="px-4 py-3 font-medium">Editable</th>
              <th className="px-4 py-3 font-medium">Formulas</th>
            </tr>
          </thead>
          <tbody>
            {structure.worksheets.map((sheet) => (
              <tr
                key={sheet.name}
                className="border-b border-hap-border/50 hover:bg-hap-panel-elevated/50"
              >
                <td className="px-4 py-3 font-medium">{sheet.name}</td>
                <td className={`px-4 py-3 capitalize ${visibilityStyles[sheet.visibility]}`}>
                  {sheet.visibility}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-hap-muted">
                  {sheet.dimensions ?? "—"}
                </td>
                <td className="px-4 py-3 font-mono text-hap-muted">{sheet.editable_cell_count}</td>
                <td className="px-4 py-3 font-mono text-hap-muted">{sheet.formula_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <CellList
          title="Formula Cells"
          empty="No formula cells detected."
          cells={structure.formula_cells}
        />
        <CellList
          title="Editable Cells"
          empty="No editable cells detected."
          cells={structure.editable_cells.slice(0, 40)}
          footer={
            structure.editable_cells.length > 40
              ? `Showing 40 of ${structure.editable_cells.length} editable cells.`
              : undefined
          }
        />
      </div>
    </div>
  );
}

function CellList({
  title,
  empty,
  cells,
  footer,
}: {
  title: string;
  empty: string;
  cells: string[];
  footer?: string;
}) {
  return (
    <section className="rounded border border-hap-border bg-hap-panel p-5">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-hap-muted">{title}</h3>
      {cells.length === 0 ? (
        <p className="mt-3 text-sm text-hap-muted">{empty}</p>
      ) : (
        <ul className="mt-3 max-h-56 space-y-1 overflow-y-auto font-mono text-xs text-hap-muted">
          {cells.map((cell) => (
            <li key={cell}>{cell}</li>
          ))}
        </ul>
      )}
      {footer && <p className="mt-3 text-xs text-hap-muted">{footer}</p>}
    </section>
  );
}
