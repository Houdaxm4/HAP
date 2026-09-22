"""Analyst intelligence: completeness gate, research, reasonableness, judgment context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import (
    AnnualCompletenessReport,
    CompletenessItem,
    ResearchQuestion,
)
from services.annual_continuity_service import detect_year_columns
from services.annual_growth_analysis_service import AnnualGrowthAnalysisService
from services.annual_normalized_base_service import AnnualNormalizedBaseService
from services.annual_tax_research_service import AnnualTaxResearchService
from services.expected_return_validation_service import ExpectedReturnValidationService
from services.valuation_validation_service import ValuationValidationService

ER_SHEET = "Expected Returns & Buybacks"
EV_SHEET = "Enterprise Value"
FM_SHEET = "Final Metrics"
INPUTS_SHEET = "Inputs"
INCOME_SHEET = "Income - GAAP"

_TAX_ROWS = range(106, 113)
_PE10_ROW = 10
_RECON_TOL = 0.005


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        if v != v:
            return None
        return float(v)
    if isinstance(v, str) and v.startswith("#"):
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _is_formula(cell_val: Any) -> bool:
    return isinstance(cell_val, str) and cell_val.startswith("=")


class AnnualAnalystIntelligenceService:
    def __init__(self) -> None:
        self.tax_research = AnnualTaxResearchService()
        self.er_validator = ExpectedReturnValidationService()
        self.val_validator = ValuationValidationService()
        self.growth_analysis = AnnualGrowthAnalysisService()
        self.normalized_base = AnnualNormalizedBaseService()

    def assess_completeness(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        new_fiscal_year: str | None,
    ) -> AnnualCompletenessReport:
        items: list[CompletenessItem] = []
        wb = load_workbook(workbook_path, data_only=True)
        try:
            if INPUTS_SHEET not in wb.sheetnames:
                return AnnualCompletenessReport(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    fiscal_year=new_fiscal_year,
                    summary="Inputs sheet missing.",
                )
            ws = wb[INPUTS_SHEET]
            cols = detect_year_columns(ws)
            fy = new_fiscal_year or max(
                (k for k in cols if k.startswith("FY")), default=None, key=lambda x: x
            )
            col = cols.get(fy) if fy else None

            if col:
                for row in _TAX_ROWS:
                    label = str(ws.cell(row, 1).value or "").strip()
                    if not label or label.lower() == "tax table":
                        continue
                    val = ws.cell(row, col).value
                    status = "POPULATED" if val not in (None, "") else "MISSING_REQUIRED_INPUT"
                    items.append(
                        CompletenessItem(
                            concept=f"tax_{label.lower().replace(' ', '_')}",
                            status=status,
                            workbook_location=f"Inputs!{ws.cell(row, col).coordinate}",
                            value=val,
                        )
                    )

                pe10_val = ws.cell(_PE10_ROW, col).value
                items.append(
                    CompletenessItem(
                        concept="pe10_new_fy",
                        status="POPULATED" if pe10_val not in (None, "") else "MISSING_REQUIRED_INPUT",
                        workbook_location=f"Inputs!{ws.cell(_PE10_ROW, col).coordinate}",
                        value=pe10_val,
                    )
                )

            price = _num(wb[INPUTS_SHEET]["B63"].value) if INPUTS_SHEET in wb.sheetnames else None
            items.append(
                CompletenessItem(
                    concept="current_market_price",
                    status="POPULATED" if price else "MISSING_REQUIRED_INPUT",
                    workbook_location="Inputs!B63",
                    value=price,
                )
            )
        finally:
            wb.close()

        missing = [i for i in items if i.status == "MISSING_REQUIRED_INPUT"]
        return AnnualCompletenessReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=new_fiscal_year,
            items=items,
            all_required_populated=len(missing) == 0,
            summary=(
                f"Completeness: {len(items) - len(missing)}/{len(items)} required inputs populated; "
                f"{len(missing)} missing."
            ),
        )

    def research_tax(
        self,
        *,
        company_facts: dict[str, Any] | None,
        fiscal_year: str,
        ticker: str,
        completeness: AnnualCompletenessReport,
    ) -> tuple[dict[str, Any], list[ResearchQuestion]]:
        if not fiscal_year:
            return {}, []
        return self.tax_research.extract_tax_inputs(
            company_facts=company_facts,
            fiscal_year=fiscal_year,
            ticker=ticker,
        )

    def build_judgment_context(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        company_facts: dict[str, Any] | None = None,
        research_evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        wb = load_workbook(workbook_path, data_only=True)
        wb_f = load_workbook(workbook_path, data_only=False)
        evidence = list(research_evidence or [])
        ctx: dict[str, Any] = {"evidence": evidence}

        try:
            analyses = self.growth_analysis.analyze_workbooks(wb, wb_f)
            er_a = analyses["er"]
            oe_a = analyses["oe"]
            gr_a = analyses["graham"]
            base_a = self.normalized_base.analyze_workbooks(wb, wb_f)
            evidence.extend(er_a.evidence[:8])
            evidence.extend(oe_a.distortions_identified[:6])
            evidence.extend(gr_a.evidence[:6])
            evidence.extend(base_a.distortions_identified[:6])

            if ER_SHEET in wb.sheetnames:
                ctx["expected_return"] = _num(wb[ER_SHEET]["E14"].value)

            er_report = self.er_validator.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
                company_facts=company_facts,
            )
            val_report = self.val_validator.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
            )
            if er_report.growth.independent_eps_cagr is not None:
                evidence.append(
                    f"Independent EPS CAGR {er_report.growth.independent_eps_cagr:.1%} "
                    f"({er_report.growth.growth_decision.value})."
                )

            hist_oe = oe_a.historical_observations
            hist_gr = gr_a.historical_observations
            ctx.update(
                {
                    "er_analysis": er_a.model_dump(),
                    "oe_analysis": oe_a.model_dump(),
                    "graham_analysis": gr_a.model_dump(),
                    "oe_base_analysis": base_a.model_dump(),
                    "book_value_growth": er_a.existing_assumption,
                    "eps_growth": hist_gr.get("eps_10y_cagr") if hist_gr.get("eps_10y_cagr") is not None else gr_a.existing_assumption,
                    "eps_growth_5y": hist_gr.get("eps_5y_cagr"),
                    "owner_earnings_growth": oe_a.existing_assumption,
                    "owner_earnings_total_change": hist_oe.get("oe_total_change_b6"),
                    "owner_earnings_3y": hist_oe.get("oe_3y_cagr"),
                    "owner_earnings_5y": hist_oe.get("oe_5y_cagr"),
                    "owner_earnings_10y": hist_oe.get("oe_10y_cagr"),
                    "prefer_eps": False,
                    "eps_distorted": bool(gr_a.distortions_identified),
                    "normalized_bv_growth": er_a.selected_prospective_rate if er_a.decision == "ADJUST" else None,
                    "normalized_eps_growth": gr_a.selected_prospective_rate if gr_a.decision == "ADJUST" else None,
                    "normalized_oe_growth": oe_a.selected_prospective_rate if oe_a.decision == "ADJUST" else None,
                    "bv_classification": er_a.decision,
                    "eps_classification": gr_a.decision,
                    "oe_classification": oe_a.decision,
                    "er_validation": er_report,
                    "valuation_validation": val_report,
                    "assumption_cells": self._discover_assumption_cells(wb_f),
                    "fm_c31_ignored": hist_gr.get("fm_c31_ignored"),
                }
            )
        finally:
            wb.close()
            wb_f.close()
        return ctx

    def _discover_assumption_cells(self, wb_f) -> dict[str, str]:
        """Locate writable growth-assumption cells (non-formula) by label scan."""
        cells: dict[str, str] = {}
        if ER_SHEET in wb_f.sheetnames:
            ws = wb_f[ER_SHEET]
            for row in range(1, 25):
                label = str(ws.cell(row, 1).value or "").lower()
                if "growth" in label and not _is_formula(ws.cell(row, 2).value):
                    cells["er_growth"] = f"{ER_SHEET}!B{row}"
        if EV_SHEET in wb_f.sheetnames:
            ev = wb_f[EV_SHEET]
            for row in range(1, 55):
                label = str(ev.cell(row, 1).value or "").lower()
                if "owners earnings growth" in label:
                    for col_letter, key in (("B", "oe_growth_b"), ("C", "oe_growth_c")):
                        addr = f"{col_letter}{row}"
                        if not _is_formula(ev[addr].value):
                            cells[key] = f"{EV_SHEET}!{addr}"
                if "eps 10 year cagr" in label or "eps 10-year cagr" in label:
                    if not _is_formula(ev.cell(row, 2).value):
                        cells["graham_eps"] = f"{EV_SHEET}!B{row}"
        return cells

    def mark_completeness_resolved(
        self,
        completeness: AnnualCompletenessReport,
        *,
        concept_prefix: str,
        value: Any,
        source: str,
    ) -> None:
        for item in completeness.items:
            if item.concept.startswith(concept_prefix) and item.status == "MISSING_REQUIRED_INPUT":
                item.status = "RESEARCHED"
                item.value = value
                item.attempted_sources.append(source)

    def mark_completeness_unavailable(
        self,
        completeness: AnnualCompletenessReport,
        *,
        concept_prefix: str,
        attempted: list[str],
        reason: str,
    ) -> None:
        for item in completeness.items:
            if item.concept.startswith(concept_prefix) and item.status in {
                "MISSING_REQUIRED_INPUT",
                "RESEARCHED",
            }:
                item.status = "SOURCE_DATA_UNAVAILABLE"
                item.attempted_sources.extend(attempted)
                item.reason = reason
