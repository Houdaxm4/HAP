"""Apply the corrections for Expected Return and Enterprise Value inputs that the review finds unrealistic.

Used by annual updates, quarter updates and new company analyses, before the valuation judgment step.

Expected Return (tab "Expected Returns & Buybacks")
  The template projects ten years of earnings from book value growth (retention x ROE). When the return it gives (price plus dividends, F14) is
  unrealistic, too high (above 12%) or negative, HAP switches to the analyst's second model: ten years of EPS projected from the company's own EPS
  growth rate. The same cells carry it: A11 (growth) becomes the EPS growth rate and A14 becomes current EPS divided by current book value per
  share, so every projection, dividend and return formula below keeps working. The email then marks the return "(adjusted)".
Enterprise Value (tab "Enterprise Value")
  The annualized owner's earnings growth (C6) is checked. When it is too high, negative or too low, a corrected rate is computed from the
  average of the first three and last three years. If the original is clearly off (25% or more, negative, or very high because the start year
  is unusually low) C6 is REPLACED; otherwise a parallel corrected calculation is written next to the original.

The original formula or value of every replaced cell is kept in the HAP Adjustments tab. Notes are plain language (see tab_notes).
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.adjustment_ledger_service import AdjustmentLedger
from services.valuation_inputs_review_service import (
    EV_SHEET,
    ER_SHEET,
    OE_HIGH,
    OE_LOW,
    AppliedCorrection,
    ReviewFinding,
    ValuationInputsReview,
    ValuationInputsReviewService,
    _pct,
)

ER_HIGH = 0.12                # a ten-year return above this is too high to rely on
ER_LOW = 0.0                  # a negative return is too low to rely on
EPS_GROWTH_LIMIT = 0.25       # an EPS growth rate beyond this (either way) is not projected for ten years
OE_CLEARLY_OFF = 0.25         # annualized owner's earnings growth at or above this is clearly off
OE_MATERIAL = 0.005           # a corrected growth rate must differ by at least half a point to matter
ER_SOURCE = "the company's EPS history (Final Metrics tab)"
EV_SOURCE = "the Final Metrics history (owner's earnings) of the company"


def _cell(ws, addr: str) -> float | None:
    v = ws[addr].value
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class ValuationCorrectionService:
    def apply(self, workbook_path: Path, company_facts: dict[str, Any] | None = None, review: ValuationInputsReview | None = None) -> ValuationInputsReview:
        path = Path(workbook_path)
        review = review or ValuationInputsReviewService().review(path, company_facts)
        wb = load_workbook(path, data_only=False)
        values = load_workbook(path, data_only=True)
        changed = False
        try:
            ledger = AdjustmentLedger(wb)
            if ER_SHEET in wb.sheetnames and ER_SHEET in values.sheetnames:
                changed |= self._expected_return(wb[ER_SHEET], values[ER_SHEET], ledger, review)
            if EV_SHEET in wb.sheetnames:
                changed |= self._owner_earnings(wb[EV_SHEET], ledger, review)
            if changed:
                wb.save(path)
        finally:
            wb.close()
            values.close()
        return review

    # ------------------------------------------------------------------ expected return
    @staticmethod
    def _model_return(price, pe, bv0, growth, roe, payout) -> float | None:
        """The template's price-plus-dividends return for given growth (A11) and ROE (A14): the same arithmetic as cells B11 to F14."""
        if not price or price <= 0 or None in (pe, bv0, growth, roe):
            return None
        eps = [bv0 * (1 + growth) ** t * roe for t in range(1, 11)]
        total = eps[-1] * pe + (payout or 0.0) * sum(eps)
        return (total / price) ** 0.1 - 1 if total > 0 else None

    def _expected_return(self, ws, ws_values, ledger, review) -> bool:
        review.findings = [f for f in review.findings if f.topic != "expected_return"]         # the earlier ROE reading is replaced by this check
        review.alternatives.pop("expected_return", None)
        model = _cell(ws_values, "F14") if _cell(ws_values, "F14") is not None else _cell(ws_values, "E14")
        if model is None:
            review.skipped.append("Expected return: the model's return is not calculated in this workbook.")
            return False
        if ER_LOW <= model <= ER_HIGH:
            review.findings.append(ReviewFinding(
                "expected_return", "model_return", "reasonable",
                f"The expected return of {_pct(model)} is within a realistic range of {_pct(ER_LOW)} to {_pct(ER_HIGH)}.", {"model": model},
            ))
            return False
        side = "too high" if model > ER_HIGH else "negative"
        price, pe, bv0 = _cell(ws_values, "A2"), _cell(ws_values, "E2"), _cell(ws_values, "B8")
        growth, eps0 = _cell(ws_values, "B5"), _cell(ws_values, "C30")
        d17, e17 = _cell(ws_values, "D17"), _cell(ws_values, "E17")
        payout = (e17 / d17) if d17 and e17 is not None else 0.0

        def keep(reason: str) -> bool:
            review.findings.append(ReviewFinding("expected_return", "model_return", "flag", f"The expected return of {_pct(model)} is {side}, but {reason}.", {"model": model}))
            review.left_as_is["expected_return"] = f"the EPS-growth model could not be used because {reason}"
            return False

        if None in (price, pe, bv0, growth, eps0) or not bv0 or bv0 <= 0:
            return keep("the EPS history and book value needed for it are not in the workbook")
        if eps0 <= 0:
            return keep("current EPS is not positive")
        if abs(growth) > EPS_GROWTH_LIMIT:
            return keep(f"the EPS growth rate of {_pct(growth)} a year is too extreme to project for ten years")
        new_roe = round(eps0 / bv0, 4)
        new_growth = round(growth, 4)
        new_return = self._model_return(price, pe, bv0, new_growth, new_roe, payout)
        if new_return is None:
            return keep("it gives no meaningful result")
        what = (
            f"The expected return model was switched to ten years of EPS projected from EPS growth of {_pct(growth)} a year, "
            f"starting from ${eps0:,.2f}; the return is now {_pct(new_return)} (it was {_pct(model)})"
        )
        why = (
            f"the original model, which grows book value by retention times return on equity, gave {_pct(model)}, which is {side} to rely on "
            f"(a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)})"
        )
        for cell, label, new_value, orig in (
            ("A14", "Average return on equity (now current EPS / book value per share)", new_roe, ws["A14"].value),
            ("A11", "Book value per share growth (now the EPS growth rate)", new_growth, ws["A11"].value),
        ):
            ws[cell].value = new_value
            ws[cell].number_format = "0.0%"
            ledger.record(sheet=ER_SHEET, cell=cell, fiscal_year=None, category="Expected return input", what=label, original=orig, new=new_value,
                          amount=None, reason=f"{what}, because {why}.", source=ER_SOURCE, method="eps_growth_model", confidence="medium")
            review.applied.append(AppliedCorrection("expected_return", f"{ER_SHEET}!{cell}", orig, new_value, "replaced", what, why, ER_SOURCE))
        review.findings.append(ReviewFinding("expected_return", "model_return", "flag", why[0].upper() + why[1:] + ".", {"model": model, "adjusted": new_return}))
        return True

    # ------------------------------------------------------------------ owner's earnings
    def _owner_earnings(self, ws, ledger, review) -> bool:
        finding = next((f for f in review.findings if f.topic == "owner_earnings"), None)
        if finding is None or finding.verdict != "flag":
            return False
        annual = finding.values.get("annualized_growth")
        series: dict[str, float] = finding.values.get("series") or {}
        alt = finding.values.get("three_year_average_cagr")
        if annual is None or alt is None or len(series) < 6:
            review.left_as_is["owner_earnings"] = "The flagged rate was left as it is because there is not enough history to compute a corrected one"
            return False
        corrected = round(min(max(alt, OE_LOW), OE_HIGH), 4)
        if abs(corrected - annual) < OE_MATERIAL:
            review.left_as_is["owner_earnings"] = "The flagged rate was left as it is because the corrected rate is almost the same"
            return False
        years = list(series)
        typical = statistics.median(series.values())
        base_low = series[years[0]] < 0.6 * typical
        clearly_off = annual >= OE_CLEARLY_OFF or annual < 0 or (annual > OE_HIGH and base_low)
        if annual > OE_HIGH:
            reason = f"{_pct(annual)} a year is very high to project forward"
        elif annual < 0:
            reason = f"{_pct(annual)} a year is negative"
        else:
            reason = f"{_pct(annual)} a year is unrealistically low"
        if base_low and annual > OE_HIGH:
            reason += f", and it rests on {years[0]}, when owner's earnings were only {series[years[0]]:,.0f} against a typical {typical:,.0f}"
        if clearly_off:
            original = ws["C6"].value
            what = f"Owner's earnings growth was replaced with {_pct(corrected)} a year (it was {_pct(annual)})"
            why = f"{reason}; the corrected rate uses the average of the first three and last three years"
            ws["C6"].value = corrected
            ws["C6"].number_format = "0.0%"
            ledger.record(sheet=EV_SHEET, cell="C6", fiscal_year=None, category="Enterprise value input", what="Owner's earnings growth (annualized)",
                          original=original, new=corrected, amount=None, reason=f"{what}, because {why}.", source=EV_SOURCE,
                          method="normalized_input", confidence="medium")
            review.applied.append(AppliedCorrection("owner_earnings", f"{EV_SHEET}!C6", original, corrected, "replaced", what, why, EV_SOURCE))
            return True
        from services.annual_judgment_service import AnnualJudgmentService

        written = AnnualJudgmentService._clone_ev_projections(ws, corrected)
        if not written:
            return False
        what = f"A parallel calculation with owner's earnings growth of {_pct(corrected)} a year was added below the original (rows 54 to 57)"
        why = f"{reason}, but the original is not clearly wrong, so both are shown"
        ledger.record(sheet=EV_SHEET, cell="A54", fiscal_year=None, category="Enterprise value input", what="Parallel owner's earnings projection",
                      original="not present", new=f"{_pct(corrected)} growth", amount=None, reason=f"{what}, because {why}.", source=EV_SOURCE,
                      method="normalized_input", confidence="medium", mark_cell=False)
        review.applied.append(AppliedCorrection("owner_earnings", f"{EV_SHEET}!A54", None, corrected, "parallel", what, why, EV_SOURCE))
        return True
