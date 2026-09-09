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


def _cagr(start: float | None, end: float | None, years: int) -> float | None:
    if start is None or end is None or years <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1.0 / years) - 1.0


def _classify_growth(g: float | None, *, horizon: str = "10y") -> str:
    if g is None:
        return "UNKNOWN"
    if g > 0.30:
        return "VERY_AGGRESSIVE"
    if g > 0.18:
        return "AGGRESSIVE"
    if g < -0.10:
        return "DISTORTED"
    if g < 0:
        return "CONSERVATIVE"
    if horizon == "20y" and g > 0.12:
        return "AGGRESSIVE"
    return "REASONABLE"


def _is_formula(cell_val: Any) -> bool:
    return isinstance(cell_val, str) and cell_val.startswith("=")


class AnnualAnalystIntelligenceService:
    def __init__(self) -> None:
        self.tax_research = AnnualTaxResearchService()
        self.er_validator = ExpectedReturnValidationService()
        self.val_validator = ValuationValidationService()

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
            # --- Book value growth (Expected Return methodology) ---
            bv_growth = None
            if ER_SHEET in wb.sheetnames:
                er = wb[ER_SHEET]
                bv_growth = _num(er["A11"].value)
                if bv_growth is None:
                    bv_growth = _num(er["B5"].value)
                ctx["expected_return"] = _num(er["E14"].value)

            # --- EPS growth (Graham / ER alternate) ---
            eps_growth = None
            if FM_SHEET in wb.sheetnames:
                eps_growth = _num(wb[FM_SHEET]["L31"].value)
            if eps_growth is None and ER_SHEET in wb.sheetnames:
                eps_growth = _num(wb[ER_SHEET]["B5"].value)

            eps_5y = _num(wb[FM_SHEET]["C31"].value) if FM_SHEET in wb.sheetnames else None

            # --- Owner earnings growth ---
            oe_growth = None
            oe_3y = oe_5y = oe_10y = None
            if EV_SHEET in wb.sheetnames:
                oe_growth = _num(wb[EV_SHEET]["B6"].value)
                if oe_growth is None:
                    oe_growth = _num(wb[EV_SHEET]["C6"].value)
            oe_series = self._owner_earnings_series(wb)
            if len(oe_series) >= 4:
                oe_3y = _cagr(oe_series[-4], oe_series[-1], 3)
            if len(oe_series) >= 6:
                oe_5y = _cagr(oe_series[-6], oe_series[-1], 5)
            if len(oe_series) >= 10:
                oe_10y = _cagr(oe_series[0], oe_series[-1], len(oe_series) - 1)

            # --- Revenue / operating income growth for cross-check ---
            rev_cagr = oi_cagr = None
            if INCOME_SHEET in wb.sheetnames and FM_SHEET in wb.sheetnames:
                rev_cagr = _num(wb[FM_SHEET]["C31"].value) if "C31" in wb[FM_SHEET] else None

            # --- ER validation (read-only deep review) ---
            er_report = self.er_validator.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
                company_facts=company_facts,
            )
            if bv_growth is None and er_report.growth.workbook_growth_assumption is not None:
                bv_growth = er_report.growth.workbook_growth_assumption
            if eps_growth is None and er_report.growth.independent_eps_cagr is not None:
                eps_growth = er_report.growth.independent_eps_cagr
            if eps_5y is None and er_report.growth.recent_5y_cagr is not None:
                eps_5y = er_report.growth.recent_5y_cagr
            if er_report.growth.independent_eps_cagr is not None:
                evidence.append(
                    f"Independent EPS CAGR {er_report.growth.independent_eps_cagr:.1%} "
                    f"({er_report.growth.growth_decision.value})."
                )
            if er_report.growth.recent_5y_cagr is not None:
                evidence.append(f"Recent 5y EPS CAGR {er_report.growth.recent_5y_cagr:.1%}.")
            if bv_growth is not None:
                evidence.append(f"BV per-share growth {bv_growth:.1%}.")
            if oe_growth is not None:
                evidence.append(f"Owner Earnings YoY growth {oe_growth:.1%}.")

            # --- Valuation validation ---
            val_report = self.val_validator.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
            )

            # --- Expected Return reasonableness ---
            bv_class = _classify_growth(bv_growth)
            eps_class = _classify_growth(eps_growth)
            prefer_eps = False
            normalized_bv = None
            if bv_class in {"AGGRESSIVE", "VERY_AGGRESSIVE", "DISTORTED"}:
                if eps_class == "REASONABLE" and eps_growth is not None:
                    prefer_eps = True
                    evidence.append(
                        f"BV growth {bv_growth:.1%} classified {bv_class}; EPS growth "
                        f"{eps_growth:.1%} more sustainable."
                    )
                else:
                    candidates = [
                        g
                        for g in (
                            er_report.growth.recent_5y_cagr,
                            er_report.growth.independent_eps_cagr,
                            eps_growth,
                            0.08,
                        )
                        if g is not None and -0.05 < g < 0.18
                    ]
                    normalized_bv = min(candidates) if candidates else 0.08
                    evidence.append(
                        f"BV growth {bv_growth:.1%} normalized to {normalized_bv:.1%}."
                    )

            # --- Graham EPS sustainability ---
            graham_class = _classify_growth(eps_growth)
            eps_distorted = False
            normalized_eps = None
            if eps_growth is not None and eps_5y is not None:
                if abs(eps_growth - eps_5y) > 0.08:
                    graham_class = "DISTORTED"
                    eps_distorted = True
                    evidence.append(
                        f"10y EPS CAGR {eps_growth:.1%} diverges from 5y {eps_5y:.1%}."
                    )
            if graham_class in {"AGGRESSIVE", "VERY_AGGRESSIVE", "DISTORTED"}:
                sustainable = [
                    g for g in (eps_5y, er_report.growth.recent_5y_cagr, rev_cagr, 0.08) if g is not None
                ]
                normalized_eps = min(max(sustainable), 0.12) if sustainable else 0.08
                evidence.append(
                    f"Graham EPS growth {eps_growth:.1%} → normalized {normalized_eps:.1%}."
                )

            # --- Owner Earnings sustainability (20y horizon discipline) ---
            oe_class = _classify_growth(oe_growth, horizon="20y")
            normalized_oe = None
            if oe_growth is not None:
                windows = [w for w in (oe_3y, oe_5y, oe_10y) if w is not None]
                if windows and abs(oe_growth - windows[-1]) > 0.15:
                    oe_class = "DISTORTED"
                if oe_class in {"AGGRESSIVE", "VERY_AGGRESSIVE", "DISTORTED"}:
                    sustainable_oe = [w for w in windows if w is not None and -0.05 < w < 0.12]
                    normalized_oe = min(sustainable_oe) if sustainable_oe else 0.08
                    evidence.append(
                        f"OE growth {oe_growth:.1%} ({oe_class}) → normalized {normalized_oe:.1%} "
                        f"(3y={oe_3y}, 5y={oe_5y}, 10y={oe_10y})."
                    )

            ctx.update(
                {
                    "book_value_growth": bv_growth,
                    "eps_growth": eps_growth,
                    "eps_growth_5y": eps_5y,
                    "owner_earnings_growth": oe_growth,
                    "owner_earnings_3y": oe_3y,
                    "owner_earnings_5y": oe_5y,
                    "owner_earnings_10y": oe_10y,
                    "prefer_eps": prefer_eps,
                    "eps_distorted": eps_distorted,
                    "normalized_bv_growth": normalized_bv,
                    "normalized_eps_growth": normalized_eps,
                    "normalized_oe_growth": normalized_oe,
                    "bv_classification": bv_class,
                    "eps_classification": graham_class,
                    "oe_classification": oe_class,
                    "er_validation": er_report,
                    "valuation_validation": val_report,
                    "assumption_cells": self._discover_assumption_cells(wb_f),
                }
            )
        finally:
            wb.close()
            wb_f.close()
        return ctx

    def _owner_earnings_series(self, wb) -> list[float]:
        """Owner earnings proxy: Net Income + D&A + CapEx per Inputs FY columns."""
        if INPUTS_SHEET not in wb.sheetnames:
            return []
        ws = wb[INPUTS_SHEET]
        cols = detect_year_columns(ws)
        fy_cols = sorted(
            ((k, c) for k, c in cols.items() if k.startswith("FY")),
            key=lambda x: x[0],
        )
        series: list[float] = []
        for _fy, col in fy_cols:
            ni = _num(ws.cell(38, col).value)
            da = _num(ws.cell(44, col).value)
            capex = _num(ws.cell(46, col).value)
            if ni is None:
                continue
            oe = ni + (da or 0) + (capex or 0)
            series.append(oe)
        return series

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
