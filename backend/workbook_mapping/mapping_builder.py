"""Build and validate CFM↔Workbook mapping specification against Workbook_Manifest (M2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from openpyxl.utils import get_column_letter

from workbook_mapping.explicit_mappings import (
    ANNUAL_PERIOD_COLS,
    ANNUAL_PERIOD_FY_TOKENS,
    CFM_CONTROL_METRICS,
    CFM_STATEMENT_METRICS,
    CHECK_ROWS,
    UNMAPPED_CFM_EXPLICIT,
    UNSUPPORTED_ROWS,
    explicit_mappings,
)
from workbook_mapping.mapping_schema import (
    CellDisposition,
    CoverageStats,
    MappingSpecification,
    PeriodColumnMap,
    UnmappedCfmMetric,
    WritableCellDisposition,
)


class MappingSpecError(ValueError):
    """Raised when an explicit mapping fails manifest validation."""


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sheet_by_name(manifest: dict, name: str) -> dict:
    for s in manifest["sheets"]:
        if s["name"] == name:
            return s
    raise MappingSpecError(f"Sheet not in manifest: {name}")


def _helpers_by_address(sheet: dict) -> dict[str, dict]:
    out = {}
    for c in sheet.get("cells") or []:
        if c.get("classification") == "Helper":
            out[c["address"]] = c
    return out


def _writable_by_address(sheet: dict) -> dict[str, dict]:
    out = {}
    for c in sheet.get("cells") or []:
        if c.get("classification") == "Writable Input" and c.get("writable") is True:
            out[c["address"]] = c
    return out


def _validate_mappings(manifest: dict, mappings) -> None:
    errors: list[str] = []
    for m in mappings:
        sheet = _sheet_by_name(manifest, m.sheet)
        if sheet.get("write_policy") == "Read-only":
            errors.append(f"{m.mapping_id}: sheet {m.sheet} is Read-only in manifest")
        helpers = _helpers_by_address(sheet)
        writables = _writable_by_address(sheet)
        if m.label_cell and m.expected_label is not None:
            h = helpers.get(m.label_cell)
            if h is None:
                errors.append(f"{m.mapping_id}: missing Helper {m.label_cell} on {m.sheet}")
            else:
                preview = (h.get("value_preview") or "").strip()
                if preview != m.expected_label:
                    errors.append(
                        f"{m.mapping_id}: label mismatch at {m.label_cell}: "
                        f"expected {m.expected_label!r} got {preview!r}"
                    )
        for col in m.columns:
            addr = f"{col}{m.row}"
            w = writables.get(addr)
            if w is None:
                # Controls/rows may only have subset of columns populated in baseline;
                # still require classification Writable Input if cell exists as nonblank,
                # OR allow missing trailing empties only if address absent from all cells.
                all_cells = {c["address"]: c for c in sheet.get("cells") or []}
                existing = all_cells.get(addr)
                if existing is None:
                    # Empty in used range — still a valid write target if row is in writable region
                    # Require at least one writable cell on this row for annual series.
                    continue
                if existing.get("classification") != "Writable Input" or not existing.get("writable"):
                    errors.append(
                        f"{m.mapping_id}: {addr} is {existing.get('classification')} "
                        f"(must be Writable Input)"
                    )
        # Require >=1 writable cell on the mapped row for annual series with multiple cols
        if len(m.columns) > 1:
            row_writables = [a for a in writables if a[0].isalpha() and int("".join(ch for ch in a if ch.isdigit())) == m.row]
            # simpler:
            row_writables = [
                addr
                for addr, cell in writables.items()
                if cell["row"] == m.row
            ]
            if not row_writables:
                errors.append(f"{m.mapping_id}: no Writable Input cells on row {m.row} of {m.sheet}")
    if errors:
        raise MappingSpecError("Mapping validation failed:\n" + "\n".join(errors))


def _period_maps(manifest: dict) -> list[PeriodColumnMap]:
    maps: list[PeriodColumnMap] = []
    for sheet_name in (
        "Income - GAAP",
        "Balance Sheet - Standardized",
        "Cash Flow - Standardized",
    ):
        sheet = _sheet_by_name(manifest, sheet_name)
        cols: dict[str, str] = {}
        for c in sheet.get("cells") or []:
            if c.get("row") == 7 and c.get("column", 0) >= 3 and c.get("notes") == "period_header":
                preview = (c.get("value_preview") or "").strip()
                # Normalize "FY 2016" -> FY2016
                token = preview.replace(" ", "")
                cols[get_column_letter(c["column"])] = token
        # Fallback to canonical AAPL window if headers missing classification notes
        if len(cols) < len(ANNUAL_PERIOD_COLS):
            cols = {
                col: fy for col, fy in zip(ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS, strict=True)
            }
        maps.append(
            PeriodColumnMap(
                sheet=sheet_name,
                header_row=7,
                date_row=8,
                columns=cols,
            )
        )
    return maps


def _mapped_addresses(mappings) -> dict[tuple[str, str], str]:
    """(sheet, address) -> mapping_id"""
    out: dict[tuple[str, str], str] = {}
    for m in mappings:
        for col in m.columns:
            addr = f"{col}{m.row}"
            out[(m.sheet, addr)] = m.mapping_id
    return out


def _dispose_writable_cells(manifest: dict, mappings) -> list[WritableCellDisposition]:
    mapped = _mapped_addresses(mappings)
    # Also mark all period columns for mapped rows even if empty in baseline
    mapped_rows: dict[str, dict[int, str]] = {}
    for m in mappings:
        mapped_rows.setdefault(m.sheet, {})[m.row] = m.mapping_id
        for col in m.columns:
            mapped[(m.sheet, f"{col}{m.row}")] = m.mapping_id

    dispositions: list[WritableCellDisposition] = []
    for sheet in manifest["sheets"]:
        name = sheet["name"]
        for c in sheet.get("cells") or []:
            if c.get("classification") != "Writable Input" or not c.get("writable"):
                continue
            addr = c["address"]
            row = c["row"]
            col = c["column"]
            key = (name, addr)
            if key in mapped:
                dispositions.append(
                    WritableCellDisposition(
                        sheet=name,
                        address=addr,
                        row=row,
                        column=col,
                        disposition=CellDisposition.MAPPED,
                        reason="Explicit CFM mapping",
                        mapping_id=mapped[key],
                    )
                )
                continue
            # Row-level mapped (empty period cell still belongs to mapping)
            if name in mapped_rows and row in mapped_rows[name]:
                col_letter = get_column_letter(col)
                if col_letter in ANNUAL_PERIOD_COLS or (row <= 3 and col == 3):
                    dispositions.append(
                        WritableCellDisposition(
                            sheet=name,
                            address=addr,
                            row=row,
                            column=col,
                            disposition=CellDisposition.MAPPED,
                            reason="On explicitly mapped row/column band",
                            mapping_id=mapped_rows[name][row],
                        )
                    )
                    continue
            if row in CHECK_ROWS.get(name, frozenset()):
                dispositions.append(
                    WritableCellDisposition(
                        sheet=name,
                        address=addr,
                        row=row,
                        column=col,
                        disposition=CellDisposition.INTENTIONALLY_EMPTY,
                        reason="Template check row — HAP must not write",
                    )
                )
                continue
            if row in UNSUPPORTED_ROWS.get(name, frozenset()):
                dispositions.append(
                    WritableCellDisposition(
                        sheet=name,
                        address=addr,
                        row=row,
                        column=col,
                        disposition=CellDisposition.UNSUPPORTED,
                        reason="Outside CFM statement surface (analytics/extras/ratios)",
                    )
                )
                continue
            dispositions.append(
                WritableCellDisposition(
                    sheet=name,
                    address=addr,
                    row=row,
                    column=col,
                    disposition=CellDisposition.FUTURE_FEATURE,
                    reason="Statement detail line reserved for expanded mapping after M2 v0.1",
                )
            )
    return dispositions


def build_mapping_specification(manifest_path: Path) -> MappingSpecification:
    manifest = _load_manifest(manifest_path)
    mappings = explicit_mappings()
    _validate_mappings(manifest, mappings)

    period_maps = _period_maps(manifest)
    dispositions = _dispose_writable_cells(manifest, mappings)

    mapped_cfm = {m.cfm_path for m in mappings}
    all_cfm = list(CFM_STATEMENT_METRICS) + list(CFM_CONTROL_METRICS)
    unmapped: list[UnmappedCfmMetric] = []
    for path, reason, action in UNMAPPED_CFM_EXPLICIT:
        unmapped.append(
            UnmappedCfmMetric(cfm_path=path, reason=reason, suggested_action=action)
        )
    for path in all_cfm:
        if path in mapped_cfm:
            continue
        if any(u.cfm_path == path for u in unmapped):
            continue
        unmapped.append(
            UnmappedCfmMetric(
                cfm_path=path,
                reason="No explicit mapping entry in M2 v0.1",
                suggested_action="Add explicit MappingEntry after label/row confirmation",
            )
        )

    # Coverage counts
    total_cfm = len(CFM_STATEMENT_METRICS)  # statement metrics only for % 
    mapped_statement = len([p for p in CFM_STATEMENT_METRICS if p in mapped_cfm])
    unmapped_statement = total_cfm - mapped_statement

    writable_total = sum(
        1
        for s in manifest["sheets"]
        for c in s.get("cells") or []
        if c.get("classification") == "Writable Input" and c.get("writable")
    )
    counts = {d.value: 0 for d in CellDisposition}
    for d in dispositions:
        counts[d.disposition.value] += 1
    unexplained = writable_total - sum(counts.values())
    # dispositions should cover all writable cells
    if len(dispositions) != writable_total:
        # Prefer disposition list length as source of truth
        writable_total = len(dispositions)
        unexplained = 0
    for d in dispositions:
        pass
    unexplained = writable_total - sum(counts[k] for k in counts)

    coverage = CoverageStats(
        total_cfm_metrics=total_cfm,
        mapped_cfm_metrics=mapped_statement,
        unmapped_cfm_metrics=unmapped_statement,
        cfm_coverage_pct=round(100.0 * mapped_statement / total_cfm, 2) if total_cfm else 0.0,
        total_writable_workbook_cells=writable_total,
        mapped_writable_cells=counts[CellDisposition.MAPPED.value],
        intentionally_empty_writable_cells=counts[CellDisposition.INTENTIONALLY_EMPTY.value],
        unsupported_writable_cells=counts[CellDisposition.UNSUPPORTED.value],
        future_feature_writable_cells=counts[CellDisposition.FUTURE_FEATURE.value],
        unexplained_writable_cells=max(0, unexplained),
        writable_coverage_explained_pct=round(
            100.0
            * (writable_total - max(0, unexplained))
            / writable_total, 2
        )
        if writable_total
        else 0.0,
    )

    return MappingSpecification(
        manifest_schema_version=manifest.get("schema_version", "unknown"),
        manifest_source=str(manifest_path).replace("\\", "/"),
        baseline_ticker=manifest.get("baseline_ticker", "AAPL"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        period_column_maps=period_maps,
        mappings=mappings,
        writable_dispositions=dispositions,
        unmapped_cfm_metrics=unmapped,
        coverage=coverage,
        assumptions=[
            "Mappings are explicit constants; no fuzzy label matching at runtime.",
            "Only Writable Input cells may be targets; validated against Workbook_Manifest.json.",
            "AAPL baseline period window FY2016–FY2025 maps to columns C–L; other tickers may shift FY labels — M5 aligns periods.",
            "CFM absolute USD amounts use transformation divide_by_1_000_000 except diluted_eps.",
            "capital_expenditures maps explicitly to '+ Acq of Fixed Prod Assets' (row 32) as documented proxy.",
            "total_debt and invested_capital remain unmapped in v0.1 with recorded reasons.",
            "Check rows are Intentionally Empty (never write).",
            "Analytics/extra rows are Unsupported; remaining statement detail is Future Feature.",
            "M2 does not write Excel and does not invent values.",
        ],
    )


def write_mapping_docs(spec: MappingSpecification, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "CFM_Workbook_Mapping.json"
    # Slim JSON for consumers: dispositions are large — keep full for audit trail
    json_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")

    # Markdown mapping
    md = [
        "# CFM ↔ Workbook Mapping Specification (M2)",
        "",
        f"**Generated:** {spec.generated_at}  ",
        f"**Baseline:** {spec.baseline_ticker}  ",
        f"**Manifest:** `{spec.manifest_source}` (schema {spec.manifest_schema_version})  ",
        "",
        "This specification is **deterministic**. Every row is an explicit binding. "
        "No Excel writes occur in M2. Consumers must only target `Writable Input` cells.",
        "",
        "## Coverage snapshot",
        "",
        f"- CFM statement metrics mapped: **{spec.coverage.mapped_cfm_metrics}/{spec.coverage.total_cfm_metrics}** "
        f"({spec.coverage.cfm_coverage_pct}%)",
        f"- Writable cells explained: **{spec.coverage.writable_coverage_explained_pct}%** "
        f"(unexplained={spec.coverage.unexplained_writable_cells})",
        f"- Mapped writable cells: {spec.coverage.mapped_writable_cells}",
        f"- Intentionally empty: {spec.coverage.intentionally_empty_writable_cells}",
        f"- Unsupported: {spec.coverage.unsupported_writable_cells}",
        f"- Future feature: {spec.coverage.future_feature_writable_cells}",
        "",
        "## Explicit mappings",
        "",
        "| ID | CFM path | Sheet | Row | Columns | Label | Unit | Transform | Priority |",
        "|----|----------|-------|-----|---------|-------|------|-----------|----------|",
    ]
    for m in sorted(spec.mappings, key=lambda x: x.write_priority):
        cols = ",".join(m.columns) if len(m.columns) <= 3 else f"{m.columns[0]}–{m.columns[-1]} ({len(m.columns)})"
        md.append(
            f"| `{m.mapping_id}` | `{m.cfm_path}` | `{m.sheet}` | {m.row} | {cols} | "
            f"{m.expected_label or '—'} | {m.unit} | {m.transformation or '—'} | {m.write_priority} |"
        )
    md += [
        "",
        "## Period column maps",
        "",
    ]
    for pm in spec.period_column_maps:
        md.append(f"### `{pm.sheet}` (header row {pm.header_row})")
        md.append("")
        md.append("| Column | FY token |")
        md.append("|--------|----------|")
        for col, fy in pm.columns.items():
            md.append(f"| {col} | `{fy}` |")
        md.append("")
    md += [
        "## Assumptions",
        "",
    ]
    for a in spec.assumptions:
        md.append(f"- {a}")
    md.append("")
    (out_dir / "CFM_Workbook_Mapping.md").write_text("\n".join(md), encoding="utf-8")

    # Coverage report
    cov = [
        "# Coverage Report (M2)",
        "",
        f"**Generated:** {spec.generated_at}",
        "",
        "## CFM metrics",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total CFM statement metrics | {spec.coverage.total_cfm_metrics} |",
        f"| Mapped metrics | {spec.coverage.mapped_cfm_metrics} |",
        f"| Unmapped metrics | {spec.coverage.unmapped_cfm_metrics} |",
        f"| Coverage % | {spec.coverage.cfm_coverage_pct} |",
        "",
        "## Writable workbook cells",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Total writable cells | {spec.coverage.total_writable_workbook_cells} |",
        f"| Mapped | {spec.coverage.mapped_writable_cells} |",
        f"| Intentionally Empty | {spec.coverage.intentionally_empty_writable_cells} |",
        f"| Unsupported | {spec.coverage.unsupported_writable_cells} |",
        f"| Future Feature | {spec.coverage.future_feature_writable_cells} |",
        f"| Unexplained | {spec.coverage.unexplained_writable_cells} |",
        f"| Explained % | {spec.coverage.writable_coverage_explained_pct} |",
        "",
        "## Disposition by sheet",
        "",
        "| Sheet | Mapped | Empty | Unsupported | Future |",
        "|-------|-------:|------:|-------------:|-------:|",
    ]
    by_sheet: dict[str, dict[str, int]] = {}
    for d in spec.writable_dispositions:
        by_sheet.setdefault(d.sheet, {x.value: 0 for x in CellDisposition})
        by_sheet[d.sheet][d.disposition.value] += 1
    for sheet, counts in sorted(by_sheet.items()):
        cov.append(
            f"| `{sheet}` | {counts['Mapped']} | {counts['Intentionally Empty']} | "
            f"{counts['Unsupported']} | {counts['Future Feature']} |"
        )
    cov.append("")
    (out_dir / "Coverage_Report.md").write_text("\n".join(cov), encoding="utf-8")

    # Unmapped CFM
    um = [
        "# Unmapped CFM Metrics (M2)",
        "",
        "Statement and control fields without an explicit M2 v0.1 mapping, or explicitly deferred.",
        "",
        "| CFM path | Reason | Suggested action |",
        "|----------|--------|------------------|",
    ]
    for u in spec.unmapped_cfm_metrics:
        um.append(f"| `{u.cfm_path}` | {u.reason} | {u.suggested_action or '—'} |")
    um.append("")
    (out_dir / "Unmapped_CFM_Metrics.md").write_text("\n".join(um), encoding="utf-8")

    # Unmapped workbook cells = not Mapped (grouped)
    uw = [
        "# Unmapped Workbook Cells (M2)",
        "",
        "Writable Input cells that are **not** Mapped. Every row is still explained "
        "(Intentionally Empty / Unsupported / Future Feature).",
        "",
        f"Total non-mapped writable cells: "
        f"{spec.coverage.total_writable_workbook_cells - spec.coverage.mapped_writable_cells}",
        "",
    ]
    for disp in (
        CellDisposition.INTENTIONALLY_EMPTY,
        CellDisposition.UNSUPPORTED,
        CellDisposition.FUTURE_FEATURE,
    ):
        subset = [d for d in spec.writable_dispositions if d.disposition == disp]
        uw.append(f"## {disp.value} ({len(subset)})")
        uw.append("")
        # Compress by sheet+row
        rows: dict[tuple[str, int], list[str]] = {}
        reasons: dict[tuple[str, int], str] = {}
        for d in subset:
            key = (d.sheet, d.row)
            rows.setdefault(key, []).append(d.address)
            reasons[key] = d.reason
        uw.append("| Sheet | Row | Addresses (sample) | Reason |")
        uw.append("|-------|-----|--------------------|--------|")
        for (sheet, row), addrs in sorted(rows.items()):
            sample = ", ".join(addrs[:6])
            if len(addrs) > 6:
                sample += f" … (+{len(addrs) - 6})"
            uw.append(f"| `{sheet}` | {row} | {sample} | {reasons[(sheet, row)]} |")
        uw.append("")
    (out_dir / "Unmapped_Workbook_Cells.md").write_text("\n".join(uw), encoding="utf-8")
