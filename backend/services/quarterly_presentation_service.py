"""Validate supplied quarterly statements. HAP does not fill or reconstruct them."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

from models.quarterly_presentation import (
    STATEMENT_SHEETS,
    PresentationDecision,
    QuarterlyPresentationReport,
    QuarterlyStatementKind,
    QuarterlyStatementPresentation,
)
from services.accounting_concept_matcher import resolve_workbook_gap
from services.formula_dependencies import MetricDependencies
from services.hap_analysis_layout_service import HapAnalysisLayoutService
from services.quarterly_dependency_service import QuarterlyDependencyService
from services.quarterly_health_service import (
    BODY_END,
    BODY_START,
    LABEL_COL,
    VALUE_COL,
    assess_all_quarterly_statements,
    iter_statement_rows,
)
from services.sec_10q_statement_service import (
    extract_sec_10q_statement,
    select_latest_10q_period,
)

# Same-period differences at or below this relative gap are treated as
# rounding or presentation precision. A different reporting period is not
# a tolerance question; period selection has to be right before this applies.
_CONFLICT_TOLERANCE = 0.05

# Legacy classifier labels. Historical reports may still contain them.
# No production mode treats them as a request to fill or rebuild a statement.
_LEGACY_FILL_DECISIONS = frozenset(
    {
        PresentationDecision.BLOOMBERG_FILL_GAPS,
        PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED,
        PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED,
    }
)
_INCOMPLETE_DECISIONS = frozenset(
    {
        PresentationDecision.BLOCKED,
        PresentationDecision.STATEMENT_INCOMPLETE,
        *_LEGACY_FILL_DECISIONS,
    }
)


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def quarter_incorporated(report: QuarterlyPresentationReport | None) -> bool:
    """True only when the latest quarter was actually written into IS and CF."""
    if report is None:
        return False
    needed = {QuarterlyStatementKind.INCOME, QuarterlyStatementKind.CASH_FLOW}
    found = [entry for entry in report.statements if entry.statement in needed]
    if len(found) < 2:
        return False
    for entry in found:
        if entry.decision in _INCOMPLETE_DECISIONS:
            return False
        has_rows = bool(
            entry.rows_preserved
            or entry.rows_filled
            or entry.sec_rows_introduced
            or entry.yahoo_rows_introduced
        )
        if not has_rows:
            return False
    return True


# "Liabilities & Shareholders' Equity" is liabilities PLUS equity (it must equal total assets). A SEC "Liabilities" figure
# is not that amount, so a row with this label is never filled from a liabilities fact.
_LIABILITIES_AND_EQUITY = re.compile(r"liabilit\w*\s*(?:&|and)\s*(?:(?:share|stock)?holders?\W*s?\W*)?equity", re.IGNORECASE)


def sheet_value_for(kind: QuarterlyStatementKind, match: Any, sec_items: list[Any], fiscal_period: str | None) -> float | None:
    """The SEC figure in the convention of the supplied sheet.

    Income and balance-sheet cells hold the latest quarter / quarter-end amount. The quarterly cash-flow sheet holds the
    cumulative year-to-date amount, so a matched cash-flow line must use its YTD companion, never the standalone quarter
    (writing the standalone figure there would understate every Q2/Q3 cash-flow line).
    """
    if match is None or match.value is None:
        return None
    if kind != QuarterlyStatementKind.CASH_FLOW or (fiscal_period or "").upper() == "Q1":
        return float(match.value)  # in Q1 the quarter and the year-to-date amounts are the same
    for item in sec_items:
        if item.xbrl_concept == match.sec_xbrl_concept and item.ytd_value is not None:
            return float(item.ytd_value)
    return None


CHECK_ROW_NOTE = (
    "HAP NOTE: this check compares the breakdown lines with the total above. The total was filled from the SEC 10-Q "
    "because it was blank; the breakdown lines were blank in the supplied workbook, so a difference here is expected "
    "and is not a data error."
)


class QuarterlyPresentationService:
    """
    Validate supplied quarterly statements against SEC.

    Blank statement cells are filled from the SEC 10-Q (shaded, source in the comment). A blank that no filing
    can fill is flagged only when a reported metric depends on it; unused blanks are ignored. HAP does not
    rebuild layouts. A material SEC conflict on a supplied value is flagged for the analyst; the value stays.
    """


    def plan_and_apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        source_workbook_path: Path,
        destination_workbook_path: Path,
        company_facts: dict[str, Any] | None,
        already_copied: bool = False,
        defer_notes: bool = False,
    ) -> QuarterlyPresentationReport:
        """
        Copy source→destination (unless already_copied), fill blank cells from the SEC 10-Q, flag the important
        ones no filing can fill, and validate each statement. Does not rebuild layouts. Leaves the source unchanged.
        """
        if not already_copied:
            destination_workbook_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_workbook_path, destination_workbook_path)

        wb = load_workbook(destination_workbook_path)
        try:
            fy, fp = (None, None)
            if company_facts:
                fy, fp = select_latest_10q_period(company_facts)
            dependency_snapshot = QuarterlyDependencyService().snapshot(wb)

            filled_from_sec: list[dict[str, Any]] = []
            flagged_missing: list[str] = []
            if company_facts:
                metric_deps = MetricDependencies(wb)
                for kind, sheet_name in STATEMENT_SHEETS.items():
                    if sheet_name in wb.sheetnames:
                        filled, missing = self._fill_blanks_from_sec(wb, kind, sheet_name, company_facts, fy, fp, metric_deps)
                        filled_from_sec.extend(filled)
                        flagged_missing.extend(missing)

            statements: list[QuarterlyStatementPresentation] = []
            for health, decision in assess_all_quarterly_statements(wb):
                if health.present and health.major_totals_present:
                    # The statement has its major totals; remaining gaps are filled, unused, or flagged individually.
                    decision = PresentationDecision.BLOOMBERG_PRESERVE
                entry = QuarterlyStatementPresentation(
                    statement=health.statement,
                    sheet=health.sheet,
                    health=health,
                    decision=decision,
                    reason=health.reason,
                    bloomberg_populated=health.populated_rows,
                    bloomberg_missing=health.missing_required_rows,
                )
                if decision == PresentationDecision.BLOOMBERG_PRESERVE:
                    rows = iter_statement_rows(wb[health.sheet]) if health.present else []
                    entry.rows_preserved = [r["cell_ref"] for r in rows if r["populated"] or r["formula"]]
                    entry.reason = (
                        f"BLOOMBERG_PRESERVE — supplied statement retained. {health.reason}"
                    )
                    entry.data_source_primary = "workbook"
                    self._reconcile_populated_with_sec(wb, entry, company_facts, fy, fp)
                    self._record_sec_provenance(entry, company_facts, fy, fp)
                else:
                    # STATEMENT_INCOMPLETE, BLOCKED, and any retired fill label.
                    self._mark_statement_incomplete(entry, health)
                    if health.present and health.sheet in wb.sheetnames:
                        rows = iter_statement_rows(wb[health.sheet])
                        entry.rows_preserved = [
                            r["cell_ref"] for r in rows if r["populated"] or r["formula"]
                        ]
                    self._reconcile_populated_with_sec(wb, entry, company_facts, fy, fp)
                    self._record_sec_provenance(entry, company_facts, fy, fp)
                statements.append(entry)

            preserve = sum(
                1 for s in statements if s.decision == PresentationDecision.BLOOMBERG_PRESERVE
            )
            incomplete = sum(1 for s in statements if s.decision in _INCOMPLETE_DECISIONS)
            input_blockers: list[str] = []
            for stmt in statements:
                if stmt.decision in _INCOMPLETE_DECISIONS:
                    input_blockers.append(stmt.reason)
                # Material differences from SEC (stmt.source_discrepancies) are flagged in the workbook and the report;
                # they no longer block.
            summary = (
                f"Quarterly statement validation: PRESERVE={preserve}, "
                f"INCOMPLETE={incomplete}; filled_from_sec={len(filled_from_sec)}; "
                f"important_data_unavailable={len(flagged_missing)}. HAP did not rebuild layouts."
            )
            if input_blockers:
                summary += f"; input_blockers={len(input_blockers)}"
            dependency = QuarterlyDependencyService().reconnect(wb, dependency_snapshot)
            if not defer_notes:
                self._write_statement_notes(wb, statements, fy, fp)
            if dependency["unresolved_dependencies"]:
                summary += f"; unresolved_dependencies={len(dependency['unresolved_dependencies'])}"
            wb.save(destination_workbook_path)
            return QuarterlyPresentationReport(
                analysis_id=analysis_id,
                ticker=ticker,
                statements=statements,
                dependency_diff=dependency["changed_formulas"],
                unresolved_dependencies=dependency["unresolved_dependencies"],
                fiscal_year=fy,
                fiscal_period=fp,
                input_blockers=input_blockers,
                filled_from_sec=filled_from_sec,
                flagged_missing=flagged_missing,
                summary=summary,
            )
        finally:
            wb.close()

    @staticmethod
    def _fill_blanks_from_sec(
        wb: Workbook,
        kind: QuarterlyStatementKind,
        sheet_name: str,
        company_facts: dict[str, Any],
        fy: int | None,
        fp: str | None,
        deps: MetricDependencies,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Fill blank latest-quarter cells from the 10-Q; flag the blanks that feed a metric and cannot be filled."""
        from services.workbook_flag_service import flag_filled, flag_missing_data, set_comment

        ws = wb[sheet_name]
        sec_items = [
            item
            for item in extract_sec_10q_statement(
                company_facts, kind, fiscal_year=fy, fiscal_period=fp, include_unresolved=False
            )
            if item.value is not None
        ]
        filled: list[dict[str, Any]] = []
        missing: list[str] = []
        for row in iter_statement_rows(ws):
            if row["populated"] or row["formula"]:
                continue
            cell = ws.cell(row["row"], VALUE_COL)
            if cell.value not in (None, ""):
                continue
            if _LIABILITIES_AND_EQUITY.search(row["label"]):
                continue
            match = resolve_workbook_gap(row["label"], kind, sec_items) if sec_items else None
            value = sheet_value_for(kind, match, sec_items, fp) if match is not None and match.decision == "MATCHED" else None
            if value is not None:
                source = f"SEC {fp or ''} FY{fy or ''} {match.match_method or ''}".strip()
                if kind == QuarterlyStatementKind.CASH_FLOW:
                    source += " (year-to-date, as the sheet holds cumulative cash flow)"
                cell.value = value
                flag_filled(
                    ws, cell.coordinate, value=value, source=source,
                    reason="The supplied workbook left this quarterly cell blank; the 10-Q reports the figure.",
                )
                filled.append({"cell": f"{sheet_name}!{cell.coordinate}", "label": row["label"], "value": value, "source": source})
                below = ws.cell(row["row"] + 1, LABEL_COL).value
                if isinstance(below, str) and below.strip().lower() == "check":
                    set_comment(ws.cell(row["row"] + 1, VALUE_COL), CHECK_ROW_NOTE)  # explain the expected difference
            elif any(deps.feeds_metrics(sheet_name, row["row"], col) for col in range(VALUE_COL, VALUE_COL + 6)):
                flag_missing_data(
                    ws, cell.coordinate, concept=row["label"],
                    reason="Blank in the supplied workbook and not found in the SEC 10-Q.",
                )
                missing.append(f"{sheet_name}!{cell.coordinate}: {row['label']}")
        return filled, missing

    @staticmethod
    def _mark_statement_incomplete(entry: QuarterlyStatementPresentation, health) -> None:
        """Record a missing statement. Do not write SEC or Yahoo values into it."""
        missing = list(health.major_totals_missing or []) or list(health.missing_fact_labels or [])[:12]
        entry.decision = PresentationDecision.STATEMENT_INCOMPLETE
        entry.blocked_or_ambiguous = [health.reason]
        entry.unresolved_facts = [
            {
                "label": label,
                "sheet": health.sheet,
                "reason": "STATEMENT_INCOMPLETE — supplied workbook is missing this line. HAP did not infer it.",
                "statement": health.statement.value,
            }
            for label in missing
        ] or [
            {
                "label": health.statement.value,
                "sheet": health.sheet,
                "reason": health.reason or "STATEMENT_INCOMPLETE",
                "statement": health.statement.value,
            }
        ]
        shown = ", ".join(str(label) for label in missing[:8]) or health.reason
        entry.reason = (
            f"STATEMENT_INCOMPLETE — {health.sheet}: {shown}. "
            "Upstream must supply the statement. HAP did not reconstruct it."
        )
        entry.data_source_primary = "workbook"

    def _record_sec_provenance(
        self,
        entry: QuarterlyStatementPresentation,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> None:
        """Cite the filing used for validation. Do not change written values."""
        if not company_facts or entry.statement not in {
            QuarterlyStatementKind.INCOME,
            QuarterlyStatementKind.CASH_FLOW,
        }:
            return
        items = [
            item
            for item in extract_sec_10q_statement(
                company_facts,
                entry.statement,
                fiscal_year=fy,
                fiscal_period=fp,
                include_unresolved=False,
            )
            if item.value is not None
        ]
        cited = next((item for item in items if item.accession_number), None)
        if cited is None:
            return
        entry.sec_accession = cited.accession_number
        entry.sec_filing_form = cited.form
        entry.sec_filing_period = cited.fiscal_period
        entry.derivation_notes = [
            f"{item.label}: {item.derivation}" for item in items if item.derivation
        ]


    def _reconcile_populated_with_sec(
        self,
        workbook: Workbook,
        entry: QuarterlyStatementPresentation,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> None:
        """Flag populated IS/CF values that conflict with SEC. Do not rewrite them."""
        kind = entry.statement
        if kind not in {QuarterlyStatementKind.INCOME, QuarterlyStatementKind.CASH_FLOW}:
            return
        if not company_facts or entry.sheet not in workbook.sheetnames:
            return
        sec_items = [
            item
            for item in extract_sec_10q_statement(
                company_facts,
                kind,
                fiscal_year=fy,
                fiscal_period=fp,
                include_unresolved=False,
            )
            if item.value is not None
        ]
        if not sec_items:
            return
        ws = workbook[entry.sheet]
        for row in range(BODY_START, BODY_END + 1):
            label = ws.cell(row, LABEL_COL).value
            cell = ws.cell(row, VALUE_COL)
            if label in (None, "") or _is_formula(cell.value):
                continue
            if not isinstance(cell.value, (int, float)) or isinstance(cell.value, bool):
                continue
            match = resolve_workbook_gap(str(label).strip(), kind, sec_items)
            if match.decision != "MATCHED" or match.value is None:
                continue
            target = sheet_value_for(kind, match, sec_items, fp)
            if target is None:
                continue
            current = float(cell.value)
            if abs(target) <= 1e-12 and abs(current) <= 1e-12:
                continue
            relative = abs(current - target) / max(abs(target), abs(current), 1e-9)
            if relative <= _CONFLICT_TOLERANCE:
                continue
            from services.workbook_flag_service import flag_discrepancy

            provenance = f"SEC {fp or ''} FY{fy or ''} {match.match_method or ''}".strip()
            entry.source_discrepancies.append(
                {
                    "label": str(label),
                    "cell": f"{entry.sheet}!{cell.coordinate}",
                    "workbook_value": current,
                    "sec_value": target,
                    "authority": "sec",
                    "material": True,
                    "action": "flag_for_upstream",
                    "relative_difference": round(relative, 4),
                    "extraction_method": match.match_method,
                    "fiscal_year": fy,
                    "fiscal_period": fp,
                }
            )
            flag_discrepancy(
                ws,
                cell.coordinate,
                workbook_value=current,
                source_value=target,
                provenance=provenance,
                issue=(
                    "Material difference versus the SEC filing. "
                    "Supplied value preserved for upstream correction."
                ),
            )

    def _write_statement_notes(
        self,
        workbook: Workbook,
        statements: list[QuarterlyStatementPresentation],
        fy: int | None,
        fp: str | None,
    ) -> None:
        layout = HapAnalysisLayoutService()
        for entry in statements:
            if entry.statement not in {
                QuarterlyStatementKind.INCOME,
                QuarterlyStatementKind.CASH_FLOW,
            }:
                continue
            if entry.sheet not in workbook.sheetnames:
                continue
            if entry.decision in _INCOMPLETE_DECISIONS and not entry.derivation_notes:
                continue
            rows: list[tuple[str, Any]] = [
                ("Reporting period", f"FY{fy} {fp}" if fy and fp else (fp or "latest filed quarter")),
                ("Presentation decision", entry.decision.value),
                ("Primary source", entry.data_source_primary or "bloomberg"),
            ]
            if entry.sec_accession:
                rows.append(("SEC accession", entry.sec_accession))
            if entry.derivation_notes:
                rows.append(("Derivation", "; ".join(entry.derivation_notes[:4])))
            if entry.source_discrepancies:
                rows.append(
                    (
                        "SEC reconciliation",
                        f"{len(entry.source_discrepancies)} populated value(s) differ from SEC "
                        "and were flagged for upstream correction. Supplied values were not overwritten.",
                    )
                )
            if entry.unresolved_facts:
                rows.append(
                    (
                        "Unresolved",
                        "; ".join(
                            f"{u.get('label')}: {u.get('reason')}" for u in entry.unresolved_facts[:4]
                        ),
                    )
                )
            layout.write_notes_section(workbook[entry.sheet], rows)

