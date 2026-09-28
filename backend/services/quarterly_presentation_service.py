"""Validate supplied quarterly statements. HAP does not fill or reconstruct them."""

from __future__ import annotations

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


class QuarterlyPresentationService:
    """
    Validate supplied quarterly statements against SEC.

    HAP does not reconstruct missing layouts or fill blank statement cells.
    A material SEC conflict is flagged and blocks certification; the supplied value stays.
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
        Copy source→destination (unless already_copied) and validate each statement.
        Does not fill blanks or rebuild layouts. Leaves the source unchanged.
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

            statements: list[QuarterlyStatementPresentation] = []
            for health, decision in assess_all_quarterly_statements(wb):
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
                for disc in stmt.source_discrepancies:
                    input_blockers.append(
                        "STATEMENT_DISCREPANCY "
                        f"{disc.get('cell')} workbook={disc.get('workbook_value')} "
                        f"sec={disc.get('sec_value')} period={disc.get('fiscal_period')} "
                        f"fy={disc.get('fiscal_year')}"
                    )
            summary = (
                f"Quarterly statement validation: PRESERVE={preserve}, "
                f"INCOMPLETE={incomplete}. "
                "HAP did not reconstruct statements."
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
                summary=summary,
            )
        finally:
            wb.close()

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
            current = float(cell.value)
            target = float(match.value)
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

