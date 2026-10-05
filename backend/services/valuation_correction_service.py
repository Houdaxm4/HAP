"""Apply the corrections for Expected Return and Enterprise Value inputs that the review finds unrealistic.

Used by annual updates, quarter updates and new company analyses, before the valuation judgment step.

Expected Return (tab "Expected Returns & Buybacks")
  Book value per share growth (A11 = retention x A14) and the average return on equity (A14) are checked. When the average ROE is
  excessively high, negative, below a realistic floor, or distorted by extraordinary years, A14 is REPLACED with a normalized ROE
  (the average of the normal years; the median when too few years remain). A11 follows, because it is a formula on A14. When the
  resulting growth is still above 15% a year or negative, A11 itself is replaced by the limit.
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
    BV_GROWTH_HIGH,
    EV_SHEET,
    ER_SHEET,
    OE_HIGH,
    OE_LOW,
    ROE_HIGH,
    ROE_LOW,
    AppliedCorrection,
    ValuationInputsReview,
    ValuationInputsReviewService,
    _pct,
)

ROE_MATERIAL = 0.015          # a normalized ROE this far (1.5 points) from the average is worth replacing
OE_CLEARLY_OFF = 0.25         # annualized owner's earnings growth at or above this is clearly off
OE_MATERIAL = 0.005           # a corrected growth rate must differ by at least half a point to matter
ER_SOURCE = "the Final Metrics history of the company"
EV_SOURCE = "the Final Metrics history (owner's earnings) of the company"


class ValuationCorrectionService:
    def apply(self, workbook_path: Path, company_facts: dict[str, Any] | None = None, review: ValuationInputsReview | None = None) -> ValuationInputsReview:
        path = Path(workbook_path)
        review = review or ValuationInputsReviewService().review(path, company_facts)
        wb = load_workbook(path, data_only=False)
        changed = False
        try:
            ledger = AdjustmentLedger(wb)
            if ER_SHEET in wb.sheetnames:
                changed |= self._expected_return(wb[ER_SHEET], ledger, review)
            if EV_SHEET in wb.sheetnames:
                changed |= self._owner_earnings(wb[EV_SHEET], ledger, review)
            if changed:
                wb.save(path)
        finally:
            wb.close()
        return review

    # ------------------------------------------------------------------ expected return
    def _expected_return(self, ws, ledger, review) -> bool:
        by = {f.metric: f for f in review.findings if f.topic == "expected_return"}
        roe_f, bv_f = by.get("average_roe"), by.get("book_value_growth")
        if roe_f is None or bv_f is None or (roe_f.verdict != "flag" and bv_f.verdict != "flag"):
            return False
        roes: dict[str, float] = roe_f.values.get("roe_by_year") or {}
        avg, median = roe_f.values.get("average_roe"), roe_f.values.get("median_roe")
        retention = bv_f.values.get("retention")
        if not roes or avg is None or median is None:
            return False
        one_time = {fy for fy, _share in roe_f.values.get("one_time_years") or []}
        distorted = {fy for fy, v in roes.items() if v < 0 or v > 2 * median or v < 0.3 * median} | one_time
        normal = [v for fy, v in roes.items() if fy not in distorted]
        normalized = statistics.mean(normal) if len(normal) >= 5 else median
        normalized = min(max(normalized, ROE_LOW), ROE_HIGH)
        changed = False
        roe_used = avg
        out_of_range = avg > ROE_HIGH or avg < ROE_LOW or avg < 0
        if out_of_range or abs(avg - normalized) >= ROE_MATERIAL:
            years = ", ".join(sorted(distorted)) or "a few unusual years"
            what = f"The average return on equity used in the expected return was replaced with {_pct(normalized)} (it was {_pct(avg)})"
            if out_of_range and not distorted:
                why = f"{_pct(avg)} is outside a realistic range of {_pct(ROE_LOW)} to {_pct(ROE_HIGH)}"
            else:
                why = f"extraordinary or unusual years ({years}) pushed it away from the normal years"
            original = ws["A14"].value
            ws["A14"].value = round(normalized, 4)
            ws["A14"].number_format = "0.0%"
            ledger.record(sheet=ER_SHEET, cell="A14", fiscal_year=None, category="Expected return input", what="Average return on equity",
                          original=original, new=round(normalized, 4), amount=None, reason=f"{what}, because {why}.", source=ER_SOURCE,
                          method="normalized_input", confidence="medium")
            review.applied.append(AppliedCorrection("expected_return", f"{ER_SHEET}!A14", original, normalized, "replaced", what, why, ER_SOURCE))
            roe_used, changed = normalized, True
        if retention is not None:
            growth = retention * roe_used
            limit = None
            if growth > BV_GROWTH_HIGH:
                limit, why = BV_GROWTH_HIGH, f"{_pct(growth)} a year for ten years is aggressive; it is capped at {_pct(BV_GROWTH_HIGH)}"
            elif growth < 0:
                limit, why = 0.0, "a negative growth rate cannot be projected for ten years; it is set to zero"
            if limit is not None:
                original = ws["A11"].value
                what = f"Book value per share growth in the expected return was replaced with {_pct(limit)} a year (it was {_pct(growth)})"
                ws["A11"].value = limit
                ws["A11"].number_format = "0.0%"
                ledger.record(sheet=ER_SHEET, cell="A11", fiscal_year=None, category="Expected return input", what="Book value per share growth",
                              original=original, new=limit, amount=None, reason=f"{what}, because {why}.", source=ER_SOURCE,
                              method="normalized_input", confidence="medium")
                review.applied.append(AppliedCorrection("expected_return", f"{ER_SHEET}!A11", original, limit, "replaced", what, why, ER_SOURCE))
                changed = True
        if not changed:
            move = review.alternatives.get("expected_return")
            review.left_as_is["expected_return"] = (
                "The flagged inputs were left as they are because correcting them would change the expected return very little"
                if move else "The flagged inputs were left as they are because the difference is too small to matter"
            )
        return changed

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
