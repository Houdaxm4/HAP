"""Render human documentation from a WorkbookManifest."""

from __future__ import annotations

from pathlib import Path

from workbook_mapping.models import WorkbookManifest


def write_classification_md(manifest: WorkbookManifest, path: Path) -> None:
    lines: list[str] = []
    lines.append("# Workbook Classification (M1.5)")
    lines.append("")
    lines.append(
        f"**Baseline:** {manifest.baseline_ticker} / `{manifest.source_filename}`  "
    )
    lines.append(
        f"**Versions:** filename `{manifest.template_version_filename}` · "
        f"sheet `{manifest.template_version_sheet}`  "
    )
    lines.append(f"**Generated (UTC):** {manifest.generated_at}  ")
    lines.append(f"**Schema:** {manifest.schema_version}  ")
    lines.append(
        f"**Suite structure identical:** {manifest.suite_structure_identical}"
    )
    lines.append("")
    lines.append(
        "This document summarizes the machine-readable "
        "[`Workbook_Manifest.json`](Workbook_Manifest.json). "
        "Future Mode A Excel modules must consume the manifest — not re-scan the workbook for roles/write policy."
    )
    lines.append("")
    lines.append("## Sheet classification")
    lines.append("")
    lines.append(
        "| # | Sheet | Role | Write policy | Fill priority | Formulas | Constants | Writable cells | Purpose |"
    )
    lines.append(
        "|---|-------|------|--------------|---------------|----------|-----------|----------------|---------|"
    )
    for s in manifest.sheets:
        writable_n = sum(1 for c in s.cells if c.writable)
        lines.append(
            f"| {s.index + 1} | `{s.name}` | {s.role.value} | {s.write_policy.value} | "
            f"{s.fill_priority.value} | {s.metrics.formula_cells} | {s.metrics.constant_cells} | "
            f"{writable_n} | {s.purpose} |"
        )
    lines.append("")
    lines.append("## Writable candidate regions (P0 annual)")
    lines.append("")
    for s in manifest.sheets:
        if not s.writable_candidate_regions:
            continue
        for r in s.writable_candidate_regions:
            lines.append(
                f"- **`{s.name}`:** rows {r.start_row}–{r.end_row}, cols {r.start_col}–{r.end_col}, "
                f"{r.cell_count} writable cells — {r.notes}"
            )
    lines.append("")
    lines.append("## Do-not-write summary")
    lines.append("")
    for s in manifest.sheets:
        if s.write_policy.value == "Read-only" or s.fill_priority.value == "Never":
            lines.append(f"- **`{s.name}`:** {'; '.join(s.do_not_write_notes) or 'Read-only / Never'}")
    lines.append("")
    lines.append("## Control cells (annual statements)")
    lines.append("")
    for s in manifest.sheets:
        if s.control_cells:
            lines.append(f"- **`{s.name}`:** {', '.join(f'`{a}`' for a in s.control_cells)}")
    lines.append("")
    lines.append("## Classification legend")
    lines.append("")
    lines.append("| Class | Meaning | Writable? |")
    lines.append("|-------|---------|-----------|")
    lines.append("| Writable Input | HAP may populate from CFM (controls + annual period values) | Yes |")
    lines.append("| Formula | Excel formula cell | No |")
    lines.append("| Output | Formula on valuation/metrics output sheets | No |")
    lines.append("| Read-only | Constant on a read-only policy sheet / meta | No |")
    lines.append("| Historical Data | As-reported or deferred LQ values | No (v0) |")
    lines.append("| Helper | Labels, headers, CapIQ codes | No |")
    lines.append("| Named Range | Target also listed under named_ranges on the cell | — |")
    lines.append("| Protected | Sheet protection enabled | No |")
    lines.append("| Empty | Blank inside used range (region aggregate) | No |")
    lines.append("| Reserved | Hidden row/col content | No |")
    lines.append("")
    lines.append("## Assumptions")
    lines.append("")
    for a in manifest.assumptions:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("## Suite fingerprints")
    lines.append("")
    for fp in manifest.suite_fingerprints:
        lines.append(f"### {fp.ticker}")
        lines.append(f"- Sheets: {len(fp.sheet_names)}")
        lines.append(f"- Roles match baseline policies applied per sheet name.")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_statistics_md(manifest: WorkbookManifest, path: Path) -> None:
    st = manifest.statistics
    lines = [
        "# Workbook Statistics (M1.5)",
        "",
        f"**Baseline:** {manifest.baseline_ticker} (`{manifest.source_filename}`)",
        f"**Generated:** {manifest.generated_at}",
        "",
        "## Totals",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Worksheets | {st.worksheets} |",
        f"| Non-blank used cells | {st.used_cells_nonblank} |",
        f"| Writable cells | {st.writable_cells} |",
        f"| Formula + Output cells | {st.formula_cells} |",
        f"| Read-only cells | {st.read_only_cells} |",
        f"| Protected cells | {st.protected_cells} |",
        f"| Historical Data cells | {st.historical_data_cells} |",
        f"| Output cells | {st.output_cells} |",
        f"| Helper cells | {st.helper_cells} |",
        f"| Reserved cells | {st.reserved_cells} |",
        f"| Empty cells (in used ranges) | {st.empty_cells_in_used_ranges} |",
        f"| Cells touching named ranges | {st.named_range_cells} |",
        f"| Merged ranges | {st.merged_ranges} |",
        f"| Named ranges | {st.named_ranges} |",
        f"| Tables | {st.tables} |",
        f"| Charts | {st.charts} |",
        f"| Data validation rules | {st.data_validation_rules} |",
        f"| Conditional formatting rules | {st.conditional_formatting_rules} |",
        f"| Hidden rows (sum across sheets) | {st.hidden_rows} |",
        f"| Hidden columns (sum across sheets) | {st.hidden_columns} |",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|----------------|------:|",
    ]
    for k, v in sorted(st.classification_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Sheets by role",
        "",
        "| Role | Count |",
        "|------|------:|",
    ]
    for k, v in sorted(st.sheets_by_role.items()):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Sheets by write policy",
        "",
        "| Write policy | Count |",
        "|--------------|------:|",
    ]
    for k, v in sorted(st.sheets_by_write_policy.items()):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_architecture_md(path: Path) -> None:
    text = """# Workbook Classification Architecture (M1.5)

## Purpose

M1.5 introduces a **permanent metadata layer** for Mode A Excel work:

**`Workbook_Manifest.json` is the single source of truth.**

From M2 onward, mapping, fill, validation, and reporting modules must **consume the manifest**.
They must **not** re-inspect the Industrial Template to rediscover sheet roles, write policy, or cell classes
when that information already exists in the manifest.

## Package layout

```text
backend/workbook_mapping/
  models.py              # Pydantic schema (CellClass, SheetClassification, WorkbookManifest, …)
  sheet_policies.py      # Structure-level role / write_policy / fill_priority per sheet name
  scanner.py             # WorkbookScanner — raw openpyxl inventory
  classifier.py          # CellClassifier / WorkbookClassifier
  statistics.py          # StatisticsGenerator
  manifest_builder.py    # ManifestBuilder — orchestration
  docs_writer.py         # Markdown renderers
  __main__.py            # CLI entry: python -m workbook_mapping
```

## Pipeline

```text
Industrial Template .xlsx
        │
        ▼
  WorkbookScanner          (used ranges, formulas, objects, named ranges, protection)
        │
        ▼
  WorkbookClassifier       (sheet policies + per-cell CellClass)
        │
        ▼
  StatisticsGenerator
        │
        ▼
  ManifestBuilder ──────► Workbook_Manifest.json
        │
        ├──► Workbook_Classification.md
        ├──► Workbook_Statistics.md
        └──► Workbook_Architecture.md (this file)
```

## Extensibility

- **New template versions:** re-run the CLI; compare `suite_fingerprints` + sheet hashes against prior manifests.
- **New sheets:** add an entry to `sheet_policies.py` (defaults to Hybrid / Read-only / Never if missing).
- **Richer cell rules:** extend `CellClassifier._classify_cell` without changing consumers of the manifest schema.
- **Schema versioning:** `schema_version` on the manifest; bump when fields change incompatibly.

## Consumer contract (M2+)

1. Load `docs/workbook_mapping/Workbook_Manifest.json` (or a versioned copy under `backend/workbook_mapping/manifests/`).
2. Only emit write intents for cells with `writable=true` and classification `Writable Input`.
3. Refuse writes to Formula / Output / Read-only / Historical Data / Helper / Protected / Reserved / Empty.
4. Respect `fill_priority` (`P0` annual first; `P1` LQ later; `Never` excluded).
5. Use `dependency_edges` for impact analysis — do not re-parse all formulas unless validating the manifest itself.

## What M1.5 does *not* do

- No CFM → cell mapping (M2)
- No write intents engine (M3)
- No Excel mutation / fill (M4)
- No Word / email
"""
    path.write_text(text, encoding="utf-8")
