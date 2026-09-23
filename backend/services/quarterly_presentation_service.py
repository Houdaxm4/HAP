"""Apply quarterly presentation decisions (Bloomberg preserve/gaps or SEC layout)."""

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
    SecLineItem,
)
from services.accounting_concept_matcher import resolve_workbook_gap
from services.hap_analysis_layout_service import HapAnalysisLayoutService
from services.quarterly_dependency_service import QuarterlyDependencyService
from services.quarterly_health_service import (
    BODY_END,
    BODY_START,
    LABEL_COL,
    VALUE_COL,
    YTD_COL,
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
_NOTES_COL = 10
_HEADER_NUMBER_FORMAT = "#,##0.00;(#,##0.00)"
_EPS_NUMBER_FORMAT = "0.00"
from services.yahoo_quarterly_statement_service import (
    BASIC_CF_LAYOUT,
    BASIC_IS_LAYOUT,
    YahooQuarterlyStatementService,
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
        if entry.decision == PresentationDecision.BLOCKED:
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
    Inspect LQ statements at the fact level. SEC EDGAR is authoritative for reported
    statements; Yahoo Finance is a supplementary fallback with explicit attribution.
    Missing facts stay unresolved — never written as zero.
    """

    def __init__(self) -> None:
        self.yahoo = YahooQuarterlyStatementService()

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
        Copy source→destination (unless already_copied), assess each statement,
        apply SEC layout only where SEC_10Q_PRESENTATION_REQUIRED.
        Leaves source unchanged.
        """
        if not already_copied:
            destination_workbook_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_workbook_path, destination_workbook_path)

        wb = load_workbook(destination_workbook_path)
        try:
            fy, fp = (None, None)
            if company_facts:
                fy, fp = select_latest_10q_period(company_facts)
            yahoo_bundle = self.yahoo.fetch(ticker)
            fiscal_q = self._detect_fiscal_quarter(wb)
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
                    entry.reason = f"BLOOMBERG_PRESERVE — {health.reason}"
                    entry.rows_filled.extend(
                        self._fill_blank_ytd_from_sec(wb, health.statement, company_facts, fy, fp)
                    )
                    self._reconcile_populated_with_sec(
                        wb, entry, company_facts, fy, fp
                    )
                    self._record_sec_provenance(entry, company_facts, fy, fp)
                elif decision == PresentationDecision.BLOOMBERG_FILL_GAPS:
                    rows = iter_statement_rows(wb[health.sheet]) if health.present else []
                    entry.rows_preserved = [r["cell_ref"] for r in rows if r["populated"] or r["formula"]]
                    needles = health.major_totals_missing or list(health.missing_fact_labels)
                    filled, discrepancies, unresolved = self._fill_major_gaps(
                        wb,
                        health.statement,
                        needles,
                        company_facts,
                        yahoo_bundle,
                        fy,
                        fp,
                        fiscal_q,
                    )
                    entry.rows_filled = filled
                    entry.source_discrepancies = discrepancies
                    entry.unresolved_facts = unresolved
                    entry.data_source_primary = "sec"
                    entry.data_source_secondary = "yahoo"
                    entry.rows_filled.extend(
                        self._fill_blank_ytd_from_sec(wb, health.statement, company_facts, fy, fp)
                    )
                    entry.reason = f"BLOOMBERG_FILL_GAPS — SEC-first, Yahoo supplementary. {health.reason}"
                    self._reconcile_populated_with_sec(
                        wb, entry, company_facts, fy, fp
                    )
                    self._record_sec_provenance(entry, company_facts, fy, fp)
                elif decision == PresentationDecision.BLOCKED:
                    entry.blocked_or_ambiguous = [health.reason]
                    entry.reason = f"BLOCKED — {health.reason}"
                elif decision in (
                    PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED,
                    PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED,
                ):
                    self._apply_authoritative_rebuild(
                        wb,
                        entry,
                        health,
                        company_facts=company_facts,
                        yahoo_bundle=yahoo_bundle,
                        fy=fy,
                        fp=fp,
                        fiscal_q=fiscal_q,
                        ticker=ticker,
                    )
                statements.append(entry)

            preserve = sum(
                1 for s in statements if s.decision == PresentationDecision.BLOOMBERG_PRESERVE
            )
            gaps = sum(
                1 for s in statements if s.decision == PresentationDecision.BLOOMBERG_FILL_GAPS
            )
            yahoo_n = sum(
                1
                for s in statements
                if s.decision == PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED
            )
            sec_n = sum(
                1
                for s in statements
                if s.decision == PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED
            )
            blocked = sum(1 for s in statements if s.decision == PresentationDecision.BLOCKED)
            summary = (
                f"Quarterly presentation: PRESERVE={preserve}, FILL_GAPS={gaps}, "
                f"YAHOO_BASIC={yahoo_n}, SEC_10Q={sec_n}, BLOCKED={blocked}"
            )
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
                summary=summary,
            )
        finally:
            wb.close()

    @staticmethod
    def _detect_fiscal_quarter(wb) -> int:
        from services.quarterly_review_service import _detect_fiscal_quarter

        sheet = STATEMENT_SHEETS[QuarterlyStatementKind.INCOME]
        if sheet in wb.sheetnames:
            q = _detect_fiscal_quarter(wb[sheet])
            if q:
                return q
        return 3

    def _apply_authoritative_rebuild(
        self,
        workbook: Workbook,
        entry: QuarterlyStatementPresentation,
        health,
        *,
        company_facts: dict[str, Any] | None,
        yahoo_bundle,
        fy: int | None,
        fp: str | None,
        fiscal_q: int,
        ticker: str,
    ) -> None:
        """SEC layout first; Yahoo basic template only when SEC has no populated facts."""
        kind = health.statement
        sec_items = (
            extract_sec_10q_statement(
                company_facts or {},
                kind,
                fiscal_year=fy,
                fiscal_period=fp,
            )
            if company_facts
            else []
        )
        populated_sec = [i for i in sec_items if i.value is not None]
        unresolved_sec = [i for i in sec_items if i.value is None]
        entry.sec_line_items = sec_items
        if company_facts is not None and populated_sec:
            entry.sec_filing_form = populated_sec[0].form
            entry.sec_filing_period = populated_sec[0].fiscal_period
            entry.sec_accession = populated_sec[0].accession_number
            ytd_items: list[SecLineItem] = []
            if kind == QuarterlyStatementKind.INCOME:
                ytd_items = extract_sec_10q_statement(
                    company_facts,
                    kind,
                    fiscal_year=fy,
                    fiscal_period=fp,
                    duration_kind="ytd",
                    include_unresolved=False,
                )
            applied = self._apply_sec_layout(
                workbook,
                kind,
                sec_items,
                ytd_items=ytd_items,
                ticker=ticker,
                fiscal_quarter=fiscal_q,
            )
            entry.decision = PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED
            entry.rows_superseded = applied["superseded"]
            entry.sec_rows_introduced = applied["introduced"]
            entry.blocked_or_ambiguous = applied["ambiguous"]
            entry.derivation_notes = applied.get("derivation_notes") or []
            entry.data_source_primary = "sec"
            yahoo_fill, discrepancies = self._fill_remaining_from_yahoo(
                workbook, kind, unresolved_sec, yahoo_bundle, fiscal_q, company_facts, fy, fp
            )
            entry.yahoo_rows_introduced = yahoo_fill
            entry.source_discrepancies = discrepancies
            if yahoo_fill:
                entry.data_source_secondary = "yahoo"
            entry.unresolved_facts = [
                {
                    "label": i.label,
                    "reason": i.unresolved_reason or "unresolved",
                    "statement": kind.value,
                }
                for i in unresolved_sec
                if not any(i.label in row for row in yahoo_fill)
            ]
            entry.reason = (
                f"SEC_10Q_PRESENTATION_REQUIRED — Bloomberg layout unusable; "
                f"reconstructed from SEC ({len(populated_sec)} populated, "
                f"{len(entry.unresolved_facts)} unresolved, form={entry.sec_filing_form}, "
                f"fp={entry.sec_filing_period})"
            )
            return

        yahoo_periods = self.yahoo.values_for_periods(
            yahoo_bundle,
            kind,
            fiscal_quarter=fiscal_q,
            company_facts=company_facts,
            fiscal_year=fy,
            fiscal_period=fp,
        )
        yahoo_values = yahoo_periods.values if yahoo_periods else {}
        has_yahoo = any(v is not None for v in yahoo_values.values())
        if has_yahoo:
            applied_y = self._apply_yahoo_basic_template(
                workbook, kind, yahoo_periods, fiscal_quarter=fiscal_q
            )
            entry.decision = PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED
            entry.yahoo_rows_introduced = applied_y["introduced"]
            entry.ytd_provenance = applied_y.get("ytd_provenance", {})
            entry.rows_superseded = applied_y["superseded"]
            entry.blocked_or_ambiguous = applied_y["ambiguous"]
            entry.data_source_primary = "yahoo"
            entry.data_source_secondary = "sec" if company_facts else None
            entry.unresolved_facts = [
                {"label": a, "reason": "missing after Yahoo fallback", "statement": kind.value}
                for a in applied_y["ambiguous"]
            ]
            entry.reason = (
                "YAHOO_BASIC_TEMPLATE — SEC facts unavailable; Yahoo supplementary fallback "
                f"({len(applied_y['introduced'])} rows). SEC remains authoritative when present."
            )
            return

        entry.decision = PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED
        entry.unresolved_facts = [
            {
                "label": i.label,
                "reason": i.unresolved_reason or "absent from SEC and Yahoo",
                "statement": kind.value,
            }
            for i in (unresolved_sec or [SecLineItem(statement=kind.value, label="(statement)")])
        ] or [
            {
                "label": kind.value,
                "reason": "No SEC or Yahoo facts; statement left blank (not zero-filled)",
                "statement": kind.value,
            }
        ]
        entry.blocked_or_ambiguous = [
            f"{u['label']}: {u['reason']}" for u in entry.unresolved_facts
        ]
        entry.reason = (
            "SEC_10Q_PRESENTATION_REQUIRED — no populated SEC or Yahoo facts; "
            "left unresolved (not represented as zero)"
        )

    def _fill_remaining_from_yahoo(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        unresolved: list[SecLineItem],
        yahoo_bundle,
        fiscal_q: int,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        filled: list[str] = []
        discrepancies: list[dict[str, Any]] = []
        if not unresolved:
            return filled, discrepancies
        sheet_name = STATEMENT_SHEETS[kind]
        if sheet_name not in workbook.sheetnames:
            return filled, discrepancies
        values = self.yahoo.values_for_periods(
            yahoo_bundle,
            kind,
            fiscal_quarter=fiscal_q,
            company_facts=company_facts,
            fiscal_year=fy,
            fiscal_period=fp,
        )
        items = self.yahoo.to_sec_line_items(values, kind, fiscal_quarter=fiscal_q)
        ws = workbook[sheet_name]
        for fact in unresolved:
            match = resolve_workbook_gap(fact.label, kind, items)
            if match.decision != "MATCHED" or match.value is None:
                continue
            target_row = None
            for r in range(BODY_START, BODY_END + 1):
                label = ws.cell(row=r, column=LABEL_COL).value
                if label and str(label).strip().startswith(fact.label):
                    target_row = r
                    break
            if target_row is None:
                continue
            cell = ws.cell(row=target_row, column=VALUE_COL)
            if _is_formula(cell.value):
                continue
            cell.value = match.value
            filled.append(
                f"{sheet_name}!C{target_row}:{fact.label}={match.value} [yahoo supplementary]"
            )
        return filled, discrepancies

    def _fill_blank_ytd_from_sec(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> list[str]:
        """Write SEC year-to-date amounts into blank YTD cells. Do not invent zeros."""
        filled: list[str] = []
        if kind not in {QuarterlyStatementKind.INCOME, QuarterlyStatementKind.CASH_FLOW}:
            return filled
        if not company_facts:
            return filled
        sheet_name = STATEMENT_SHEETS[kind]
        if sheet_name not in workbook.sheetnames:
            return filled
        ytd_items = [
            item
            for item in extract_sec_10q_statement(
                company_facts,
                kind,
                fiscal_year=fy,
                fiscal_period=fp,
                duration_kind="ytd",
                include_unresolved=False,
            )
            if item.value is not None
        ]
        if not ytd_items:
            return filled
        ws = workbook[sheet_name]
        for row in range(BODY_START, BODY_END + 1):
            label = ws.cell(row, LABEL_COL).value
            cell = ws.cell(row, YTD_COL)
            if label in (None, "") or _is_formula(cell.value):
                continue
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                continue
            match = resolve_workbook_gap(str(label).strip(), kind, ytd_items)
            if match.decision != "MATCHED" or match.value is None:
                continue
            cell.value = match.value
            cell.number_format = _HEADER_NUMBER_FORMAT
            filled.append(
                f"{sheet_name}!G{row}:{label}={match.value} "
                f"[ytd concept={match.accounting_concept} method={match.match_method}]"
            )
        return filled

    def _fill_major_gaps(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        missing_majors: list[str],
        company_facts: dict[str, Any] | None,
        yahoo_bundle,
        fy: int | None,
        fp: str | None,
        fiscal_q: int,
    ) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
        filled: list[str] = []
        discrepancies: list[dict[str, Any]] = []
        if still_sec := (missing_majors and company_facts):
            filled.extend(
                self._fill_major_gaps_from_sec(
                    workbook, kind, missing_majors, company_facts, fy, fp
                )
            )
        still_missing = [m for m in missing_majors if not self._needle_was_written(m, filled)]
        yahoo_filled = self._fill_major_gaps_from_yahoo(
            workbook, kind, still_missing, yahoo_bundle, fiscal_q, company_facts, fy, fp
        )
        filled.extend(yahoo_filled)
        if company_facts and yahoo_filled:
            discrepancies.extend(
                self._record_sec_yahoo_conflicts(
                    kind, missing_majors, company_facts, yahoo_bundle, fy, fp, fiscal_q
                )
            )
        unresolved = [
            {
                "label": m,
                "reason": "absent from SEC and Yahoo; left blank (not zero)",
                "statement": kind.value,
            }
            for m in missing_majors
            if not self._needle_was_written(m, filled)
        ]
        _ = still_sec
        return filled, discrepancies, unresolved

    def _record_sec_yahoo_conflicts(
        self,
        kind: QuarterlyStatementKind,
        missing_majors: list[str],
        company_facts: dict[str, Any],
        yahoo_bundle,
        fy: int | None,
        fp: str | None,
        fiscal_q: int,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        sec_items = extract_sec_10q_statement(
            company_facts, kind, fiscal_year=fy, fiscal_period=fp, include_unresolved=False
        )
        yahoo_values = self.yahoo.values_for_periods(
            yahoo_bundle, kind, fiscal_quarter=fiscal_q, company_facts=company_facts,
            fiscal_year=fy, fiscal_period=fp,
        )
        yahoo_items = self.yahoo.to_sec_line_items(yahoo_values, kind, fiscal_quarter=fiscal_q)
        for needle in missing_majors:
            sec_match = resolve_workbook_gap(needle, kind, sec_items)
            y_match = resolve_workbook_gap(needle, kind, yahoo_items)
            if (
                sec_match.decision == "MATCHED"
                and y_match.decision == "MATCHED"
                and sec_match.value is not None
                and y_match.value is not None
                and abs(sec_match.value) > 0
            ):
                rel = abs(sec_match.value - y_match.value) / max(abs(sec_match.value), 1e-9)
                if rel > _CONFLICT_TOLERANCE:
                    out.append(
                        {
                            "label": needle,
                            "sec_value": sec_match.value,
                            "yahoo_value": y_match.value,
                            "authority": "sec",
                            "relative_difference": round(rel, 4),
                        }
                    )
        return out

    def _fill_major_gaps_from_yahoo(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        missing_majors: list[str],
        yahoo_bundle,
        fiscal_q: int,
        company_facts: dict[str, Any] | None = None,
        fy: int | None = None,
        fp: str | None = None,
    ) -> list[str]:
        filled: list[str] = []
        if not missing_majors:
            return filled
        sheet_name = STATEMENT_SHEETS[kind]
        if sheet_name not in workbook.sheetnames:
            return filled
        ws = workbook[sheet_name]
        values = self.yahoo.values_for_periods(
            yahoo_bundle,
            kind,
            fiscal_quarter=fiscal_q,
            company_facts=company_facts,
            fiscal_year=fy,
            fiscal_period=fp,
        )
        items = self.yahoo.to_sec_line_items(values, kind, fiscal_quarter=fiscal_q)

        def _n(s: Any) -> str:
            return " ".join(str(s or "").lower().split())

        for needle in missing_majors:
            for r in range(BODY_START, BODY_END + 1):
                label = ws.cell(row=r, column=LABEL_COL).value
                value = ws.cell(row=r, column=VALUE_COL).value
                if label is None or needle not in _n(label):
                    continue
                if _is_formula(value) or isinstance(value, (int, float)):
                    continue
                match = resolve_workbook_gap(str(label).strip(), kind, items)
                if match.decision != "MATCHED" or match.value is None:
                    continue
                ws.cell(row=r, column=VALUE_COL).value = match.value
                filled.append(
                    f"{sheet_name}!C{r}:{label}={match.value} [yahoo concept={match.accounting_concept}]"
                )
                break
        return filled

    def _apply_yahoo_basic_template(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        yahoo_periods,
        *,
        fiscal_quarter: int,
    ) -> dict[str, list[str] | dict]:
        from services.yahoo_quarterly_statement_service import YahooPeriodValues

        period_values = (
            yahoo_periods
            if isinstance(yahoo_periods, YahooPeriodValues)
            else YahooPeriodValues(values=yahoo_periods)
        )
        yahoo_values = period_values.values
        ytd_prov = self.yahoo.provenance_report(period_values)

        sheet_name = STATEMENT_SHEETS[kind]
        result: dict[str, Any] = {"superseded": [], "introduced": [], "ambiguous": [], "ytd_provenance": ytd_prov}
        if sheet_name not in workbook.sheetnames:
            result["ambiguous"].append(f"Sheet {sheet_name} missing")
            return result

        layout = BASIC_IS_LAYOUT if kind == QuarterlyStatementKind.INCOME else BASIC_CF_LAYOUT
        ws = workbook[sheet_name]

        # Clear Bloomberg body (preserve formulas)
        for r in range(BODY_START, BODY_END + 1):
            lc = ws.cell(row=r, column=LABEL_COL)
            vc = ws.cell(row=r, column=VALUE_COL)
            if _is_formula(lc.value) or _is_formula(vc.value):
                continue
            if lc.value is not None or vc.value is not None:
                result["superseded"].append(f"{sheet_name}!A{r}/C{r}:{lc.value!r}")
                lc.value = None
                vc.value = None
                if kind == QuarterlyStatementKind.INCOME:
                    for col in (4, 7, 8):
                        if not _is_formula(ws.cell(row=r, column=col).value):
                            ws.cell(row=r, column=col).value = None

        for row, label, field_name, _ in layout:
            ws.cell(row=row, column=LABEL_COL).value = label
            fq = yahoo_values.get(f"fq_{field_name}")
            py = yahoo_values.get(f"py_{field_name}")
            if fq is not None:
                prov = period_values.ytd_provenance.get(field_name)
                prov_tag = f" [{prov.provenance}]" if prov else ""
                ws.cell(row=row, column=VALUE_COL).value = fq
                result["introduced"].append(f"{sheet_name}!C{row}:{label}={fq} [yahoo fq]{prov_tag}")
            else:
                result["ambiguous"].append(f"Missing Yahoo FQ value for {label}")
            if py is not None:
                ws.cell(row=row, column=4).value = py  # col D prior-year FQ
            if fiscal_quarter >= 2:
                ytd = yahoo_values.get(f"ytd_{field_name}")
                py_ytd = yahoo_values.get(f"py_ytd_{field_name}")
                if ytd is not None:
                    prov = period_values.ytd_provenance.get(field_name)
                    tag = prov.provenance if prov else "unknown"
                    comp = f" components={prov.components}" if prov and prov.components else ""
                    ws.cell(row=row, column=YTD_COL).value = ytd
                    result["introduced"].append(
                        f"{sheet_name}!G{row}:{label}={ytd} [ytd {tag}{comp}]"
                    )
                if py_ytd is not None:
                    ws.cell(row=row, column=8).value = py_ytd

        banner = ws.cell(row=7, column=LABEL_COL)
        if banner.value is None or not _is_formula(banner.value):
            banner.value = "Yahoo Finance basic template (fallback) — values in millions"

        return result

    def _fill_major_gaps_from_sec(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        missing_majors: list[str],
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> list[str]:
        """Fill blank major-line VALUE cells via accounting-concept SEC matching."""
        filled: list[str] = []
        if not missing_majors or not company_facts:
            return filled
        sheet_name = STATEMENT_SHEETS[kind]
        if sheet_name not in workbook.sheetnames:
            return filled
        ws = workbook[sheet_name]
        items = extract_sec_10q_statement(
            company_facts, kind, fiscal_year=fy, fiscal_period=fp
        )
        if not items:
            return filled

        def _n(s: Any) -> str:
            return " ".join(str(s or "").lower().split())

        def _component(label: Any) -> bool:
            text = _n(label)
            return text.startswith("+") or text.startswith("-")

        for needle in missing_majors:
            # Fill every blank parent row. A shorter needle such as
            # "investing activities" also occurs inside component labels;
            # those rows are not the section total.
            for r in range(BODY_START, BODY_END + 1):
                label = ws.cell(row=r, column=LABEL_COL).value
                value = ws.cell(row=r, column=VALUE_COL).value
                if label is None or _component(label):
                    continue
                if needle not in _n(label):
                    continue
                if _is_formula(value) or isinstance(value, (int, float)):
                    continue
                workbook_label = str(label).strip()
                match = resolve_workbook_gap(workbook_label, kind, items)
                if match.decision != "MATCHED" or match.value is None:
                    filled.append(
                        f"{sheet_name}!C{r}:{workbook_label} "
                        f"[{match.decision}] {match.reason}"
                    )
                    continue
                ws.cell(row=r, column=VALUE_COL).value = match.value
                filled.append(
                    f"{sheet_name}!C{r}:{workbook_label}={match.value} "
                    f"[concept={match.accounting_concept} xbrl={match.sec_xbrl_concept} "
                    f"method={match.match_method} conf={match.confidence}]"
                )
        return filled

    @staticmethod
    def _needle_was_written(needle: str, filled: list[str]) -> bool:
        token = " ".join(needle.lower().split())
        for row in filled:
            text = " ".join(str(row).lower().split())
            if (
                token in text
                and "=" in text
                and "review" not in text
                and "unresolved" not in text
                and "[blocked]" not in text
            ):
                return True
        return False

    def _record_sec_provenance(
        self,
        entry: QuarterlyStatementPresentation,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> None:
        """Cite the filing used for gap fill without changing written values."""
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

    def _apply_sec_layout(
        self,
        workbook: Workbook,
        kind: QuarterlyStatementKind,
        sec_items: list[SecLineItem],
        ytd_items: list[SecLineItem] | None = None,
        ticker: str | None = None,
        fiscal_quarter: int | None = None,
    ) -> dict[str, Any]:
        sheet_name = STATEMENT_SHEETS[kind]
        result: dict[str, Any] = {
            "superseded": [],
            "introduced": [],
            "ambiguous": [],
            "derivation_notes": [],
        }
        if sheet_name not in workbook.sheetnames:
            result["ambiguous"].append(f"Sheet {sheet_name} missing")
            return result
        if not sec_items:
            return result

        ws = workbook[sheet_name]
        for r in range(BODY_START, BODY_END + 1):
            label_cell = ws.cell(row=r, column=LABEL_COL)
            value_cell = ws.cell(row=r, column=VALUE_COL)
            if _is_formula(label_cell.value) or _is_formula(value_cell.value):
                continue
            if label_cell.value is not None or value_cell.value is not None:
                result["superseded"].append(f"{sheet_name}!A{r}/C{r}:{label_cell.value!r}")
                label_cell.value = None
                value_cell.value = None
                for col in (4, YTD_COL, 8, _NOTES_COL):
                    extra = ws.cell(row=r, column=col)
                    if not _is_formula(extra.value):
                        extra.value = None

        titles = {
            QuarterlyStatementKind.INCOME: "Consolidated Statements of Income",
            QuarterlyStatementKind.BALANCE_SHEET: "Consolidated Balance Sheets",
            QuarterlyStatementKind.CASH_FLOW: "Consolidated Statements of Cash Flows",
        }
        populated = next((i for i in sec_items if i.value is not None), sec_items[0])
        period_end = populated.period_end or ""
        fp = populated.fiscal_period or (f"Q{fiscal_quarter}" if fiscal_quarter else "")
        form = populated.form or "10-Q"
        unit = populated.unit or "USD_millions"
        self._write_header_if_free(ws, 7, f"SEC {form} presentation ({fp}) — not Bloomberg taxonomy")
        self._write_header_if_free(
            ws,
            8,
            f"{ticker or ''} | {fp} | period end {period_end} | {unit} | {titles.get(kind, kind.value)}",
        )
        self._write_header_if_free(
            ws,
            9,
            f"Source: SEC EDGAR accession {populated.accession_number or 'n/a'} "
            f"{populated.source_url or ''}".strip(),
        )
        hdr = ws.cell(row=10, column=LABEL_COL)
        if hdr.value is None or not _is_formula(hdr.value):
            ws.cell(row=10, column=LABEL_COL).value = "Line item"
            ws.cell(row=10, column=VALUE_COL).value = "Fiscal quarter"
            ws.cell(row=10, column=YTD_COL).value = "YTD"
            ws.cell(row=10, column=_NOTES_COL).value = "Source / derivation / mapping id"

        write_row = BODY_START
        for item in sec_items:
            while write_row <= BODY_END:
                if _is_formula(ws.cell(row=write_row, column=LABEL_COL).value) or _is_formula(
                    ws.cell(row=write_row, column=VALUE_COL).value
                ):
                    write_row += 1
                    continue
                break
            if write_row > BODY_END:
                result["ambiguous"].append(f"No space for SEC line {item.label}")
                break
            label = item.label
            if item.duration_kind == "ytd" and item.extraction_method != "derived_ytd_subtract":
                label = f"{item.label} (YTD)"
            map_id = item.xbrl_concept or item.label
            ws.cell(row=write_row, column=LABEL_COL).value = label
            value_cell = ws.cell(row=write_row, column=VALUE_COL)
            if item.value is not None:
                value_cell.value = item.value
                if "share" in (item.unit or "").lower() or "eps" in item.label.lower():
                    value_cell.number_format = _EPS_NUMBER_FORMAT
                else:
                    value_cell.number_format = _HEADER_NUMBER_FORMAT
            notes = []
            if item.extraction_method:
                notes.append(item.extraction_method)
            if item.derivation:
                notes.append(item.derivation)
                result["derivation_notes"].append(f"{item.label}: {item.derivation}")
            if item.unresolved_reason:
                notes.append(item.unresolved_reason)
                result["ambiguous"].append(f"{item.label}: {item.unresolved_reason}")
            notes.append(f"map={map_id}")
            if item.accession_number:
                notes.append(f"accn={item.accession_number}")
            ws.cell(row=write_row, column=_NOTES_COL).value = "; ".join(notes)
            ytd_val = item.ytd_value
            if ytd_val is None and ytd_items:
                ytd_hit = next(
                    (y for y in ytd_items if y.label == item.label and y.value is not None),
                    None,
                )
                if ytd_hit is not None:
                    ytd_val = ytd_hit.value
            if ytd_val is not None and not _is_formula(ws.cell(row=write_row, column=YTD_COL).value):
                ytd_cell = ws.cell(row=write_row, column=YTD_COL)
                ytd_cell.value = ytd_val
                ytd_cell.number_format = _HEADER_NUMBER_FORMAT
            result["introduced"].append(
                f"{sheet_name}!A{write_row}:{label}={item.value} "
                f"[{item.xbrl_concept}/{item.duration_kind}/{item.extraction_method}]"
            )
            write_row += 1

        return result

    def _reconcile_populated_with_sec(
        self,
        workbook: Workbook,
        entry: QuarterlyStatementPresentation,
        company_facts: dict[str, Any] | None,
        fy: int | None,
        fp: str | None,
    ) -> None:
        """Replace populated IS/CF values that conflict with SEC. Never invent zeros."""
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
            entry.source_discrepancies.append(
                {
                    "label": str(label),
                    "cell": f"{entry.sheet}!{cell.coordinate}",
                    "workbook_value": current,
                    "sec_value": target,
                    "authority": "sec",
                    "relative_difference": round(relative, 4),
                    "extraction_method": match.match_method,
                    "fiscal_year": fy,
                    "fiscal_period": fp,
                }
            )
            cell.value = target
            entry.rows_filled.append(
                f"{entry.sheet}!{cell.coordinate}:{label}={target} "
                f"[sec_reconcile was={current} method={match.match_method}]"
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
            if entry.decision == PresentationDecision.BLOCKED and not entry.derivation_notes:
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
                        f"{len(entry.source_discrepancies)} populated value(s) replaced because SEC disagreed.",
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

    @staticmethod
    def _write_header_if_free(ws, row: int, text: str) -> None:
        cell = ws.cell(row=row, column=LABEL_COL)
        if cell.value is None or not _is_formula(cell.value):
            cell.value = text
