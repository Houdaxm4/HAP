"""Read-only ROIC / NOPAT / Invested Capital review for Industrial Template.

Does not modify the workbook. Reconstructs house methodology from known
template cell bindings, compares independently, and surfaces judgment items.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.roic_validation import (
    ClassificationJudgment,
    RoicAnalystItem,
    RoicAnalystReview,
    RoicDecision,
    RoicPeriodResult,
    RoicValidationReport,
)
from workbook_mapping.explicit_mappings import ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS

IC_SHEET = "IC & NOPAT & ROIC "
BS_SHEET = "Balance Sheet - Standardized"
INCOME_SHEET = "Income - GAAP"
INPUTS_SHEET = "Inputs"
TAX_SHEET = "Tax"
FINAL_METRICS_SHEET = "Final Metrics"

# House OA / OL composition (Inputs!81-85 → IC sheet)
OA_CURRENT_ROWS = {
    11: ("Cash & Cash Equivalents", "operating_asset", "Included in house OA current; excess cash is judgment-sensitive."),
    14: ("Accounts & Notes Receivable", "operating_asset", "Core operating working-capital asset."),
    20: ("Inventories", "operating_asset", "Core operating working-capital asset."),
    27: ("Prepaid Expenses", "operating_asset", "Operating prepaid asset."),
}
OA_NONCURRENT_ROWS = {
    37: ("PP&E Net (As Reported)", "operating_asset", "Core operating fixed asset."),
    48: ("Total Intangible Assets", "operating_asset", "Includes goodwill/intangibles per house method."),
    51: ("Prepaid Expense (LT)", "operating_asset", "Long-term operating prepaid."),
}
OL_CURRENT_ROWS = {
    65: ("Accounts Payable", "operating_liability", "Core operating working-capital liability."),
    68: ("Other Payables & Accruals", "operating_liability", "Operating accruals per house method."),
    78: ("ST Deferred Revenue", "operating_liability", "Operating deferred revenue."),
}
OL_NONCURRENT_ROWS = {
    98: ("LT Deferred Revenue", "operating_liability", "Long-term operating deferred revenue."),
}
EXPLICIT_NON_OPERATING = {
    12: ("ST Investments", "non_operating", "Excluded from house OA (marketable / investment)."),
    43: ("LT Investments & Receivables", "non_operating", "Excluded from house OA."),
    45: ("LT Marketable Securities", "non_operating", "Excluded from house OA."),
}
EXPLICIT_FINANCING = {
    70: ("ST Debt", "financing", "Debt excluded from operating liabilities."),
    86: ("LT Debt", "financing", "Debt excluded from operating liabilities."),
}
AMBIGUOUS_ROWS = {
    66: ("Accrued Taxes", "ambiguous", "Tax accruals not in house OL; classification is judgment-sensitive."),
    67: ("Interest & Dividends Payable", "ambiguous", "Financing-like payable excluded from house OL — confirm."),
    71: ("ST Lease Liabilities", "ambiguous", "Lease liabilities on BS vs capitalized leases on Leases sheet."),
    88: ("LT Lease Liabilities", "ambiguous", "Lease liabilities on BS vs capitalized leases on Leases sheet."),
}

# Absolute dollar tolerance (USD millions) and ratio tolerances
_IC_ABS_TOL = 1.0
_NOPAT_ABS_TOL = 1.0
_ROIC_ABS_TOL = 0.005  # 50 bps
_WACC_MIN = 0.01
_WACC_MAX = 0.25
_CASH_OA_MATERIAL_SHARE = 0.25  # cash / OA


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def _near(a: float | None, b: float | None, tol: float) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def _period_label_from_value(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if hasattr(value, "year"):
        return f"FY{value.year}"
    text = str(value).strip()
    if text.upper().startswith("FY"):
        return text.upper()[:6] if len(text) >= 6 else text.upper()
    # datetime-like string
    for token in text.replace("/", "-").split("-"):
        if token.isdigit() and len(token) == 4:
            return f"FY{token}"
    return fallback


def _spread_interpretation(spread: float | None) -> str:
    if spread is None:
        return "spread_unavailable"
    if spread > 0.02:
        return "value_creation"
    if spread < -0.02:
        return "value_destruction"
    return "weak_neutral"


class RoicValidationService:
    """Inspect workbook ROIC architecture and validate economics (read-only)."""

    def validate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        invested_capital_convention: str = "ending",
    ) -> RoicValidationReport:
        path = Path(workbook_path)
        wb_vals = load_workbook(path, data_only=True)
        wb_formulas = load_workbook(path, data_only=False)

        methodology = self._methodology_metadata(
            wb_formulas,
            invested_capital_convention=invested_capital_convention,
        )
        periods = self._build_periods(wb_vals, wb_formulas, invested_capital_convention)
        classifications = self._classifications(wb_vals, periods)

        validated = review = disc = watch = material = 0
        for p in periods:
            if p.decision == RoicDecision.VALIDATED:
                validated += 1
            elif p.decision == RoicDecision.DISCREPANCY:
                disc += 1
            elif p.decision == RoicDecision.MATERIAL_REVIEW:
                material += 1
            elif p.decision == RoicDecision.WATCH:
                watch += 1
            else:
                review += 1

        for c in classifications:
            if c.status == RoicDecision.MATERIAL_REVIEW:
                material += 1
            elif c.status == RoicDecision.WATCH:
                watch += 1
            elif c.status == RoicDecision.DISCREPANCY:
                disc += 1
            elif c.status == RoicDecision.REVIEW_REQUIRED:
                review += 1

        hist = self._historical_spread_interpretation(periods)
        overall = self._overall_decision(periods, classifications)
        summary = (
            f"ROIC review {ticker}: {len(periods)} periods; "
            f"validated={validated}, review={review}, discrepancy={disc}, "
            f"watch={watch}, material_review={material}. {hist}"
        )

        wb_vals.close()
        wb_formulas.close()

        return RoicValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=str(path),
            methodology=methodology,
            periods=periods,
            classifications=classifications,
            validated_count=validated,
            review_required_count=review,
            discrepancy_count=disc,
            watch_count=watch,
            material_review_count=material,
            historical_spread_interpretation=hist,
            summary=summary,
            overall_decision=overall,
        )

    def build_analyst_review(self, report: RoicValidationReport) -> RoicAnalystReview:
        items: list[RoicAnalystItem] = []

        # Tax / NOPAT house vs economic
        zero_tax_periods = [
            p for p in report.periods if (p.operating_taxes_workbook or 0) == 0 and p.nopat_workbook is not None
        ]
        if zero_tax_periods and any(
            (p.tax_rate_economic or 0) > 0.05 for p in report.periods
        ):
            sample = zero_tax_periods[-1]
            items.append(
                RoicAnalystItem(
                    period=sample.period,
                    topic="operating_taxes_missing",
                    status=RoicDecision.MATERIAL_REVIEW,
                    observation=(
                        "House operating taxes are zero across periods while the income "
                        "statement shows material income-tax expense — NOPAT is effectively pretax."
                    ),
                    quantitative_evidence={
                        "operating_taxes_workbook": sample.operating_taxes_workbook,
                        "tax_rate_economic": sample.tax_rate_economic,
                        "nopat_workbook": sample.nopat_workbook,
                        "nopat_independent_economic": sample.nopat_independent_economic,
                    },
                    economic_interpretation=(
                        "ROIC is overstated relative to after-tax operating profit until "
                        "Inputs tax table / Tax sheet operating taxes are populated."
                    ),
                )
            )

        # Cash in OA
        cash_items = [
            c
            for c in report.classifications
            if "Cash" in c.workbook_line and c.classification == "operating_asset"
        ]
        material_cash = [c for c in cash_items if c.status in (RoicDecision.WATCH, RoicDecision.MATERIAL_REVIEW)]
        if material_cash:
            c = material_cash[-1]
            items.append(
                RoicAnalystItem(
                    period=c.period,
                    topic="excess_cash_in_invested_capital",
                    status=c.status,
                    observation=c.reason,
                    quantitative_evidence={"value": c.value, "evidence": c.evidence},
                    economic_interpretation=(
                        "Including large cash balances raises invested capital and depresses ROIC; "
                        "excluding excess cash would increase ROIC further."
                    ),
                )
            )

        # Goodwill / intangibles
        gw = [
            c
            for c in report.classifications
            if "Intangible" in c.workbook_line or "Goodwill" in c.workbook_line
        ]
        if gw:
            c = gw[-1]
            items.append(
                RoicAnalystItem(
                    period=c.period,
                    topic="acquisition_intangibles_in_oa",
                    status=RoicDecision.WATCH,
                    observation=c.reason,
                    quantitative_evidence={"value": c.value},
                    economic_interpretation=(
                        "House ROIC is labeled 'Including Goodwill' — acquisition intangibles "
                        "remain in operating assets by design."
                    ),
                )
            )

        # Ambiguous classifications (dedupe by line)
        seen_amb: set[str] = set()
        for c in report.classifications:
            if c.classification != "ambiguous":
                continue
            if c.workbook_line in seen_amb:
                continue
            seen_amb.add(c.workbook_line)
            items.append(
                RoicAnalystItem(
                    period=c.period,
                    topic=f"ambiguous_classification:{c.workbook_line}",
                    status=RoicDecision.REVIEW_REQUIRED,
                    observation=c.reason,
                    quantitative_evidence={"value": c.value, "confidence": c.confidence},
                    economic_interpretation="Ambiguous item flagged for analyst review — not reclassified automatically.",
                    recommendation="do_not_guess_review_required",
                )
            )

        # Spread trend
        spreads = [p.roic_minus_wacc for p in report.periods if p.roic_minus_wacc is not None]
        if spreads:
            items.append(
                RoicAnalystItem(
                    period=None,
                    topic="roic_minus_wacc_trend",
                    status=RoicDecision.VALIDATED if all(s > 0 for s in spreads) else RoicDecision.WATCH,
                    observation=report.historical_spread_interpretation,
                    quantitative_evidence={
                        "spreads": spreads,
                        "min": min(spreads),
                        "max": max(spreads),
                        "mean": sum(spreads) / len(spreads),
                    },
                    economic_interpretation=report.historical_spread_interpretation,
                )
            )

        # Formula reconciliation failures
        for p in report.periods:
            if p.decision == RoicDecision.DISCREPANCY:
                items.append(
                    RoicAnalystItem(
                        period=p.period,
                        topic="roic_reconciliation_discrepancy",
                        status=RoicDecision.DISCREPANCY,
                        observation=p.explanation,
                        quantitative_evidence={
                            "roic_workbook": p.roic_workbook,
                            "roic_independent": p.roic_independent,
                            "ic_diff": p.invested_capital_difference,
                            "nopat_diff": p.nopat_difference_house,
                        },
                        economic_interpretation="Independent reconstruction does not match workbook within tolerance.",
                    )
                )

        material_count = sum(1 for i in items if i.status == RoicDecision.MATERIAL_REVIEW)
        watch_count = sum(1 for i in items if i.status == RoicDecision.WATCH)
        disc_count = sum(1 for i in items if i.status == RoicDecision.DISCREPANCY)
        summary = (
            f"{len(items)} ROIC analyst items "
            f"(material={material_count}, watch={watch_count}, discrepancy={disc_count})."
        )
        return RoicAnalystReview(
            analysis_id=report.analysis_id,
            ticker=report.ticker,
            items=items,
            material_count=material_count,
            watch_count=watch_count,
            discrepancy_count=disc_count,
            historical_spread_interpretation=report.historical_spread_interpretation,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _methodology_metadata(self, wb_formulas, *, invested_capital_convention: str) -> dict[str, Any]:
        ic = wb_formulas[IC_SHEET] if IC_SHEET in wb_formulas.sheetnames else None
        return {
            "ic_sheet": IC_SHEET,
            "invested_capital_formula": "Operating Assets - Operating Liabilities + Capitalized Leases + Capitalized R&D",
            "invested_capital_cells": {
                "operating_assets": "row 3 (=Inputs!row80)",
                "operating_liabilities": "row 4 (=Inputs!row83)",
                "capitalized_leases": "row 5 (=Leases!B16 …)",
                "capitalized_rd": "row 6 (='R&D'!E3 …)",
                "invested_capital": "row 7 (=OA-OL+Leases+R&D)",
            },
            "nopat_formula": "Revenue - OpEx + LeaseExp - LeaseDep + R&D Exp - R&D Amort - Operating Taxes",
            "nopat_cell": "row 20",
            "roic_formula": "NOPAT / Invested Capital (same column)",
            "roic_cell": "row 23",
            "wacc_source": "Final Metrics row 7 = Inputs!row54/100 (Bloomberg / BS C126)",
            "roic_minus_wacc": "Final Metrics row 8 = ROIC - WACC",
            "invested_capital_convention": invested_capital_convention,
            "averaging_note": (
                "Per-period ROIC uses ending invested capital in the same FY column; "
                "Final Metrics col B AVERAGE(C:L) is a 10-year average of the ratio, not average capital."
            ),
            "sample_formulas": {
                "IC_C7": ic["C7"].value if ic is not None else None,
                "NOPAT_C20": ic["C20"].value if ic is not None else None,
                "ROIC_C23": ic["C23"].value if ic is not None else None,
            },
            "oa_composition": {
                "current_bs_rows": list(OA_CURRENT_ROWS.keys()),
                "noncurrent_bs_rows": list(OA_NONCURRENT_ROWS.keys()),
            },
            "ol_composition": {
                "current_bs_rows": list(OL_CURRENT_ROWS.keys()),
                "noncurrent_bs_rows": list(OL_NONCURRENT_ROWS.keys()),
            },
        }

    def _build_periods(
        self,
        wb_vals,
        wb_formulas,
        invested_capital_convention: str,
    ) -> list[RoicPeriodResult]:
        if IC_SHEET not in wb_vals.sheetnames:
            return []

        ic = wb_vals[IC_SHEET]
        ic_f = wb_formulas[IC_SHEET]
        bs = wb_vals[BS_SHEET] if BS_SHEET in wb_vals.sheetnames else None
        income = wb_vals[INCOME_SHEET] if INCOME_SHEET in wb_vals.sheetnames else None
        inputs = wb_vals[INPUTS_SHEET] if INPUTS_SHEET in wb_vals.sheetnames else None
        tax = wb_vals[TAX_SHEET] if TAX_SHEET in wb_vals.sheetnames else None
        fm = wb_vals[FINAL_METRICS_SHEET] if FINAL_METRICS_SHEET in wb_vals.sheetnames else None

        results: list[RoicPeriodResult] = []
        for idx, col_letter in enumerate(ANNUAL_PERIOD_COLS):
            col = 3 + idx  # C=3
            fy = ANNUAL_PERIOD_FY_TOKENS[idx]
            if bs is not None:
                fy = _period_label_from_value(bs.cell(8, col).value, fy)

            oa_wb = _num(ic.cell(3, col).value)
            ol_wb = _num(ic.cell(4, col).value)
            leases = _num(ic.cell(5, col).value) or 0.0
            rd_cap = _num(ic.cell(6, col).value) or 0.0
            ic_wb = _num(ic.cell(7, col).value)

            # Independent OA/OL from BS house rows
            oa_ind = self._sum_bs_rows(bs, col, list(OA_CURRENT_ROWS) + list(OA_NONCURRENT_ROWS))
            ol_ind = self._sum_bs_rows(bs, col, list(OL_CURRENT_ROWS) + list(OL_NONCURRENT_ROWS))
            if oa_ind is None:
                oa_ind = oa_wb
            if ol_ind is None:
                ol_ind = ol_wb

            ic_ind = None
            if oa_ind is not None and ol_ind is not None:
                ic_ind = oa_ind - ol_ind + leases + rd_cap

            if invested_capital_convention == "average" and idx > 0 and results:
                prev = results[-1].invested_capital_independent
                if prev is not None and ic_ind is not None:
                    ic_ind_avg = (prev + ic_ind) / 2.0
                else:
                    ic_ind_avg = ic_ind
                # Workbook still uses ending; independent path can use average when requested
                ic_for_roic = ic_ind_avg
            else:
                ic_for_roic = ic_ind

            rev = _num(ic.cell(11, col).value)
            opex = _num(ic.cell(12, col).value)
            oi = _num(ic.cell(13, col).value)
            lease_exp = _num(ic.cell(14, col).value) or 0.0
            lease_dep = _num(ic.cell(15, col).value) or 0.0
            rd_exp = _num(ic.cell(16, col).value) or 0.0
            rd_amort = _num(ic.cell(17, col).value) or 0.0
            op_tax = _num(ic.cell(19, col).value)
            nopat_wb = _num(ic.cell(20, col).value)
            roic_wb = _num(ic.cell(23, col).value)

            # Fallback from Inputs / Income if IC cached blank
            if rev is None and inputs is not None:
                rev = _num(inputs.cell(87, col).value)
            if opex is None and inputs is not None:
                opex = _num(inputs.cell(88, col).value)
            if oi is None and inputs is not None:
                oi = _num(inputs.cell(89, col).value)
            if oi is None and rev is not None and opex is not None:
                oi = rev - opex

            nopat_house = None
            if rev is not None and opex is not None:
                nopat_house = rev - opex + lease_exp - lease_dep + rd_exp - rd_amort - (op_tax or 0.0)

            # Economic tax rate from Income statement
            pretax = _num(income.cell(42, col).value) if income is not None else None
            tax_exp = _num(income.cell(44, col).value) if income is not None else None
            tax_rate_econ = _safe_div(tax_exp, pretax) if pretax and pretax != 0 else None
            tax_rate_wb = _num(tax.cell(26, col).value) if tax is not None else None

            # Economic NOPAT: after-tax operating profit on adjusted pretax operating base
            # Use house pretax NOPAT bridge before tax, then apply economic rate.
            pretax_op = None
            if rev is not None and opex is not None:
                pretax_op = rev - opex + lease_exp - lease_dep + rd_exp - rd_amort
            nopat_econ = None
            if pretax_op is not None and tax_rate_econ is not None:
                nopat_econ = pretax_op * (1.0 - tax_rate_econ)
            elif oi is not None and tax_rate_econ is not None:
                nopat_econ = oi * (1.0 - tax_rate_econ)

            nopat_diff = _diff(nopat_wb, nopat_house)
            if _near(nopat_wb, nopat_house, _NOPAT_ABS_TOL):
                nopat_decision = RoicDecision.VALIDATED
            elif nopat_wb is None or nopat_house is None:
                nopat_decision = RoicDecision.SOURCE_MISSING
            else:
                nopat_decision = RoicDecision.DISCREPANCY

            # Flag pretax house NOPAT when economic tax is material
            if (
                nopat_decision == RoicDecision.VALIDATED
                and (op_tax or 0) == 0
                and tax_rate_econ is not None
                and tax_rate_econ > 0.05
            ):
                nopat_decision = RoicDecision.REVIEW_REQUIRED

            ic_diff = _diff(ic_wb, ic_ind)
            roic_ind = _safe_div(nopat_house if nopat_house is not None else nopat_wb, ic_for_roic)
            # When comparing to workbook, use ending IC (workbook convention)
            roic_ind_ending = _safe_div(
                nopat_house if nopat_house is not None else nopat_wb,
                ic_ind if invested_capital_convention == "ending" else ic_for_roic,
            )
            roic_diff = _diff(roic_wb, roic_ind_ending)

            if _near(roic_wb, roic_ind_ending, _ROIC_ABS_TOL):
                roic_decision = RoicDecision.VALIDATED
            elif roic_wb is None or roic_ind_ending is None:
                roic_decision = RoicDecision.SOURCE_MISSING
            else:
                roic_decision = RoicDecision.DISCREPANCY

            # WACC
            wacc = None
            if fm is not None:
                wacc = _num(fm.cell(7, col).value)
            if wacc is None and inputs is not None:
                raw = _num(inputs.cell(54, col).value)
                if raw is not None:
                    wacc = raw / 100.0 if raw > 1.0 else raw

            wacc_status = RoicDecision.VALIDATED
            if wacc is None:
                wacc_status = RoicDecision.SOURCE_MISSING
            elif wacc < _WACC_MIN or wacc > _WACC_MAX:
                wacc_status = RoicDecision.REVIEW_REQUIRED

            spread = None
            if fm is not None and _num(fm.cell(8, col).value) is not None:
                spread = _num(fm.cell(8, col).value)
            elif roic_wb is not None and wacc is not None:
                spread = roic_wb - wacc

            decision, explanation = self._period_decision(
                nopat_decision=nopat_decision,
                roic_decision=roic_decision,
                ic_diff=ic_diff,
                wacc_status=wacc_status,
                op_tax=op_tax,
                tax_rate_econ=tax_rate_econ,
                invested_capital_convention=invested_capital_convention,
            )

            results.append(
                RoicPeriodResult(
                    period=fy,
                    column=col_letter,
                    operating_assets=oa_wb if oa_wb is not None else oa_ind,
                    operating_liabilities=ol_wb if ol_wb is not None else ol_ind,
                    capitalized_leases=leases,
                    capitalized_rd=rd_cap,
                    invested_capital_workbook=ic_wb,
                    invested_capital_independent=ic_ind,
                    invested_capital_difference=ic_diff,
                    revenue=rev,
                    operating_expenses=opex,
                    operating_income=oi,
                    lease_expense=lease_exp,
                    lease_depreciation=lease_dep,
                    rd_expense=rd_exp,
                    rd_amortization=rd_amort,
                    operating_taxes_workbook=op_tax,
                    tax_rate_workbook=tax_rate_wb,
                    tax_rate_economic=tax_rate_econ,
                    nopat_workbook=nopat_wb,
                    nopat_independent_house=nopat_house,
                    nopat_independent_economic=nopat_econ,
                    nopat_difference_house=nopat_diff,
                    nopat_decision=nopat_decision,
                    roic_workbook=roic_wb,
                    roic_independent=roic_ind_ending,
                    roic_difference=roic_diff,
                    roic_decision=roic_decision,
                    wacc=wacc,
                    wacc_status=wacc_status,
                    roic_minus_wacc=spread,
                    spread_interpretation=_spread_interpretation(spread),
                    decision=decision,
                    explanation=explanation,
                    evidence={
                        "ic_formula": ic_f.cell(7, col).value,
                        "nopat_formula": ic_f.cell(20, col).value,
                        "roic_formula": ic_f.cell(23, col).value,
                        "invested_capital_convention": invested_capital_convention,
                        "ic_for_roic_independent": ic_for_roic,
                    },
                )
            )
        return results

    def _sum_bs_rows(self, bs, col: int, rows: list[int]) -> float | None:
        if bs is None:
            return None
        total = 0.0
        any_val = False
        for r in rows:
            v = _num(bs.cell(r, col).value)
            if v is not None:
                total += v
                any_val = True
        return total if any_val else None

    def _classifications(self, wb_vals, periods: list[RoicPeriodResult]) -> list[ClassificationJudgment]:
        if BS_SHEET not in wb_vals.sheetnames or not periods:
            return []
        bs = wb_vals[BS_SHEET]
        # Use latest period for material classification snapshot + all periods for cash share
        latest = periods[-1]
        col = ANNUAL_PERIOD_COLS.index(latest.column) + 3 if latest.column in ANNUAL_PERIOD_COLS else 12
        judgments: list[ClassificationJudgment] = []

        def add(row: int, label: str, classification: str, reason: str, status: RoicDecision, confidence: float):
            val = _num(bs.cell(row, col).value)
            judgments.append(
                ClassificationJudgment(
                    workbook_line=label,
                    sheet=BS_SHEET,
                    row=row,
                    value=val,
                    period=latest.period,
                    classification=classification,
                    reason=reason,
                    confidence=confidence,
                    evidence=f"{BS_SHEET}!{get_column_letter(col)}{row}",
                    status=status,
                )
            )

        for row, (label, cls, reason) in {**OA_CURRENT_ROWS, **OA_NONCURRENT_ROWS}.items():
            status = RoicDecision.VALIDATED
            conf = 0.9
            if row == 11:  # cash
                oa = latest.operating_assets
                cash = _num(bs.cell(11, col).value)
                if cash is not None and oa and oa > 0 and cash / oa >= _CASH_OA_MATERIAL_SHARE:
                    status = RoicDecision.MATERIAL_REVIEW
                    reason = (
                        f"Cash is {cash / oa:.0%} of operating assets — excess-cash treatment "
                        "materially affects invested capital / ROIC."
                    )
                    conf = 0.7
                elif cash is not None and oa and oa > 0 and cash / oa >= 0.10:
                    status = RoicDecision.WATCH
                    reason = f"Cash is {cash / oa:.0%} of OA; monitor excess-cash vs operating cash."
                    conf = 0.75
            if row == 48:  # intangibles incl goodwill
                status = RoicDecision.WATCH
                conf = 0.8
            add(row, label, cls, reason, status, conf)

        for row, (label, cls, reason) in {**OL_CURRENT_ROWS, **OL_NONCURRENT_ROWS}.items():
            add(row, label, cls, reason, RoicDecision.VALIDATED, 0.9)

        for row, (label, cls, reason) in EXPLICIT_NON_OPERATING.items():
            add(row, label, cls, reason, RoicDecision.VALIDATED, 0.95)

        for row, (label, cls, reason) in EXPLICIT_FINANCING.items():
            add(row, label, cls, reason, RoicDecision.VALIDATED, 0.95)

        for row, (label, cls, reason) in AMBIGUOUS_ROWS.items():
            add(row, label, cls, reason, RoicDecision.REVIEW_REQUIRED, 0.4)

        return judgments

    def _period_decision(
        self,
        *,
        nopat_decision: RoicDecision,
        roic_decision: RoicDecision,
        ic_diff: float | None,
        wacc_status: RoicDecision,
        op_tax: float | None,
        tax_rate_econ: float | None,
        invested_capital_convention: str,
    ) -> tuple[RoicDecision, str]:
        if roic_decision == RoicDecision.DISCREPANCY or nopat_decision == RoicDecision.DISCREPANCY:
            return (
                RoicDecision.DISCREPANCY,
                "Independent house reconstruction differs from workbook beyond tolerance.",
            )
        if ic_diff is not None and abs(ic_diff) > _IC_ABS_TOL:
            return (
                RoicDecision.DISCREPANCY,
                f"Invested capital reconciliation gap of {ic_diff:.2f} (USD millions).",
            )
        if (op_tax or 0) == 0 and tax_rate_econ is not None and tax_rate_econ > 0.05:
            return (
                RoicDecision.MATERIAL_REVIEW,
                "House NOPAT uses zero operating taxes while economic tax rate is material; "
                f"IC convention={invested_capital_convention}.",
            )
        if wacc_status == RoicDecision.SOURCE_MISSING:
            return RoicDecision.REVIEW_REQUIRED, "WACC missing; ROIC validated but spread incomplete."
        if wacc_status == RoicDecision.REVIEW_REQUIRED:
            return RoicDecision.REVIEW_REQUIRED, "WACC outside plausible band; do not overwrite."
        if nopat_decision == RoicDecision.REVIEW_REQUIRED:
            return RoicDecision.REVIEW_REQUIRED, "NOPAT house math matches but tax treatment needs review."
        if roic_decision == RoicDecision.VALIDATED and nopat_decision == RoicDecision.VALIDATED:
            return (
                RoicDecision.VALIDATED,
                f"House ROIC reconciles (ending IC convention={invested_capital_convention}).",
            )
        return RoicDecision.REVIEW_REQUIRED, "Incomplete inputs for full ROIC validation."

    def _historical_spread_interpretation(self, periods: list[RoicPeriodResult]) -> str:
        spreads = [(p.period, p.roic_minus_wacc) for p in periods if p.roic_minus_wacc is not None]
        if not spreads:
            return "Insufficient ROIC−WACC history."
        values = [s for _, s in spreads]
        positive = sum(1 for s in values if s > 0.02)
        negative = sum(1 for s in values if s < -0.02)
        mean = sum(values) / len(values)
        if positive == len(values):
            tone = (
                f"Across {len(values)} fiscal years, ROIC−WACC is consistently positive "
                f"(mean spread {mean:.1%}), indicating sustained economic value creation on the house ROIC basis."
            )
        elif negative == len(values):
            tone = (
                f"Across {len(values)} fiscal years, ROIC−WACC is consistently negative "
                f"(mean {mean:.1%}), indicating value destruction on the house basis."
            )
        else:
            tone = (
                f"ROIC−WACC mixed over {len(values)} years "
                f"({positive} value-creating, {negative} value-destroying; mean {mean:.1%})."
            )
        # Caveat when taxes missing
        if any((p.operating_taxes_workbook or 0) == 0 for p in periods) and any(
            (p.tax_rate_economic or 0) > 0.05 for p in periods
        ):
            tone += (
                " Caveat: house operating taxes are largely zero, so spreads are computed on a "
                "near-pretax NOPAT and overstate after-tax economic profit."
            )
        return tone

    def _overall_decision(
        self,
        periods: list[RoicPeriodResult],
        classifications: list[ClassificationJudgment],
    ) -> RoicDecision:
        statuses = [p.decision for p in periods] + [c.status for c in classifications]
        if any(s == RoicDecision.DISCREPANCY for s in statuses):
            return RoicDecision.DISCREPANCY
        if any(s == RoicDecision.MATERIAL_REVIEW for s in statuses):
            return RoicDecision.MATERIAL_REVIEW
        if any(s == RoicDecision.REVIEW_REQUIRED for s in statuses):
            return RoicDecision.REVIEW_REQUIRED
        if any(s == RoicDecision.WATCH for s in statuses):
            return RoicDecision.WATCH
        return RoicDecision.VALIDATED


# Pure helpers for unit tests without Excel
def house_nopat(
    *,
    revenue: float,
    operating_expenses: float,
    lease_expense: float = 0.0,
    lease_depreciation: float = 0.0,
    rd_expense: float = 0.0,
    rd_amortization: float = 0.0,
    operating_taxes: float = 0.0,
) -> float:
    return (
        revenue
        - operating_expenses
        + lease_expense
        - lease_depreciation
        + rd_expense
        - rd_amortization
        - operating_taxes
    )


def house_invested_capital(
    *,
    operating_assets: float,
    operating_liabilities: float,
    capitalized_leases: float = 0.0,
    capitalized_rd: float = 0.0,
) -> float:
    return operating_assets - operating_liabilities + capitalized_leases + capitalized_rd


def house_roic(*, nopat: float, invested_capital: float) -> float | None:
    return _safe_div(nopat, invested_capital)


def average_invested_capital(beginning: float, ending: float) -> float:
    return (beginning + ending) / 2.0


def classify_liability(label: str) -> tuple[str, RoicDecision]:
    """Classify a liability label; ambiguous → review, not guess."""
    text = label.lower()
    if any(k in text for k in ("debt", "borrowing", "notes payable", "bond")):
        return "financing", RoicDecision.VALIDATED
    if any(k in text for k in ("accounts payable", "deferred revenue", "accrued", "payable")):
        if "interest" in text or "dividend" in text:
            return "ambiguous", RoicDecision.REVIEW_REQUIRED
        return "operating_liability", RoicDecision.VALIDATED
    if "lease" in text:
        return "ambiguous", RoicDecision.REVIEW_REQUIRED
    return "ambiguous", RoicDecision.REVIEW_REQUIRED


def classify_asset(label: str) -> tuple[str, RoicDecision]:
    text = label.lower()
    if any(k in text for k in ("marketable", "investment", "st investment", "lt investment")):
        return "non_operating", RoicDecision.VALIDATED
    if any(
        k in text
        for k in (
            "receivable",
            "inventor",
            "prepaid",
            "ppe",
            "property",
            "intangib",
            "goodwill",
            "cash",
        )
    ):
        return "operating_asset", RoicDecision.VALIDATED
    return "ambiguous", RoicDecision.REVIEW_REQUIRED


def interpret_roic_wacc_spread(spread: float) -> str:
    return _spread_interpretation(spread)


def wacc_plausibility(wacc: float | None) -> RoicDecision:
    if wacc is None:
        return RoicDecision.SOURCE_MISSING
    if wacc < _WACC_MIN or wacc > _WACC_MAX:
        return RoicDecision.REVIEW_REQUIRED
    return RoicDecision.VALIDATED


def roic_within_tolerance(workbook: float, independent: float, tol: float = _ROIC_ABS_TOL) -> bool:
    return abs(workbook - independent) <= tol
