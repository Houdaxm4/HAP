"""Apply the corrections for Expected Return, Enterprise Value and Graham inputs that the review finds unrealistic.

Used by annual updates, quarter updates and new company analyses, before the valuation judgment step. The rule everywhere: when a model
gives a value that looks inaccurate because of noise in the data, look at the model's INPUTS first, and change the model only when the
inputs cannot be repaired.

Expected Return (tab "Expected Returns & Buybacks")
  The template projects ten years of earnings from book value growth (retention x ROE). When its return (price plus dividends, F14) is
  unrealistic (above 20% or negative):
  1. Look at the two inputs: the average ROE (A14) and the average retained earnings (C5, from the Inputs tab). When some years of one of
     them are clearly off, it is recalculated without those years. If that makes the return realistic, it stays.
  2. When the whole history is off (a severely cyclical business) the analyst's second model is used: ten years of EPS projected from the
     EPS growth rate (A14 becomes current EPS / book value per share, A11 the EPS growth rate). That is done only when EPS itself follows a
     steady trend. The EPS growth rate is the robust one when extraordinary years skew the first-to-last-year rate.
  3. When EPS is cyclical too, the model is kept as it is and every observation is written as a red flag.
Enterprise Value (tab "Enterprise Value")
  The annualized owner's earnings growth (C6) is checked. When it is off, two corrected rates are computed and compared in the notes: the
  average of the first three and last three years (Final Metrics M10) and the log-linear model through all years (N10). The one that looks
  more accurate is recommended in a comment; C6 is never replaced (log-linear if more conservative with a high R2, the ratio model, or neither).
Graham entry price (tab "Enterprise Value", EPS 10 Year CAGR in B41, from Final Metrics L31)
  The EPS growth rate is checked for being skewed by extraordinary EPS years. B41 is kept; a comment gives the Graham entry price under the rate of the other years.

The original formula or value of every replaced cell is kept in the HAP Adjustments tab. Notes are plain language (see tab_notes).
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.adjustment_ledger_service import AdjustmentLedger
from services.annual_period_service import detect_year_columns
from services.tab_notes import note
from services.valuation_history import (
    MAX_OFF_SHARE,
    MIN_YEARS,
    TREND_R2,
    eps_trend,
    loglinear,
    off_years,
    review_eps_growth,
    trimmed_mean,
)
from services.valuation_inputs_review_service import (
    EV_SHEET,
    ER_SHEET,
    FM_SHEET,
    ER_HIGH,
    ER_LOW,
    OE_HIGH,
    OE_LOW,
    AppliedCorrection,
    ReviewFinding,
    ValuationInputsReview,
    ValuationInputsReviewService,
    _pct,
)

EPS_GROWTH_LIMIT = 0.25       # an EPS growth rate beyond this (either way) is not projected for ten years
OE_CLEARLY_OFF = 0.25         # annualized owner's earnings growth at or above this is clearly off
OE_MATERIAL = 0.005           # a corrected growth rate must differ by at least half a point to matter
OE_AGREE = 0.01               # two corrected growth rates within a point of each other agree
ER_SOURCE = "the company's EPS history (Final Metrics tab)"
ER_INPUTS_SOURCE = "the Final Metrics and Inputs tab history"
EV_SOURCE = "the Final Metrics history (owner's earnings) of the company"
GRAHAM_SOURCE = "the company's EPS history (Final Metrics tab)"
INPUTS_SHEET = "Inputs"
RETENTION_LABEL = "change in retained earnings per share/ep"


_pct_of_number = _pct


def _pct(x: float) -> str:                                    # noqa: F811 - a model return that is an error (#NUM!) is shown as such
    return "#NUM! (no meaningful number)" if x != x else _pct_of_number(x)


def _cell(ws, addr: str) -> float | None:
    v = ws[addr].value
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _years_text(years: list[str]) -> str:
    return ", ".join(years)


class ValuationCorrectionService:
    def apply(self, workbook_path: Path, company_facts: dict[str, Any] | None = None, review: ValuationInputsReview | None = None) -> ValuationInputsReview:
        path = Path(workbook_path)
        review = review or ValuationInputsReviewService().review(path, company_facts)
        wb = load_workbook(path, data_only=False)
        values = load_workbook(path, data_only=True)
        changed = False
        try:
            ledger = AdjustmentLedger(wb)
            hist = self._histories(wb, values)
            if ER_SHEET in wb.sheetnames and ER_SHEET in values.sheetnames:
                changed |= self._expected_return(wb[ER_SHEET], values[ER_SHEET], ledger, review, hist)
            if EV_SHEET in wb.sheetnames:
                changed |= self._owner_earnings(wb[EV_SHEET], ledger, review)
                if EV_SHEET in values.sheetnames:
                    changed |= self._graham(wb[EV_SHEET], values[EV_SHEET], ledger, review, hist)
            if changed:
                wb.save(path)
        finally:
            wb.close()
            values.close()
        return review

    # ------------------------------------------------------------------ the histories behind the inputs
    @staticmethod
    def _series(wb, values, sheet: str, match) -> dict[str, float]:
        """A yearly row of a tab, found by its label, as {FY label: value} in year order."""
        if sheet not in wb.sheetnames or sheet not in values.sheetnames:
            return {}
        ws = values[sheet]
        row = next((r for r in range(1, min(ws.max_row or 1, 200) + 1) if match(str(ws.cell(r, 1).value or "").strip().lower())), None)
        if not row:
            return {}
        try:
            cols = {k: c for k, c in detect_year_columns(wb[sheet], wb).items() if str(k).startswith("FY")}
        except Exception:  # noqa: BLE001 - a workbook without readable year headers simply has no history here
            return {}
        out: dict[str, float] = {}
        for fy, col in sorted(cols.items(), key=lambda kv: kv[1]):
            v = ws.cell(row, col).value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[fy] = float(v)
        return out

    def _histories(self, wb, values) -> dict[str, dict[str, float]]:
        return {
            "roe": self._series(wb, values, FM_SHEET, lambda s: s == "roe"),
            "eps": self._series(wb, values, FM_SHEET, lambda s: s == "eps"),
            "retention": self._series(wb, values, INPUTS_SHEET, lambda s: s.startswith(RETENTION_LABEL)),
        }

    # ------------------------------------------------------------------ expected return
    @staticmethod
    def _model_return(price, pe, bv0, growth, roe, payout) -> float | None:
        """The template's price-plus-dividends return for given growth (A11) and ROE (A14): the same arithmetic as cells B11 to F14."""
        if not price or price <= 0 or None in (pe, bv0, growth, roe):
            return None
        eps = [bv0 * (1 + growth) ** t * roe for t in range(1, 11)]
        total = eps[-1] * pe + (payout or 0.0) * sum(eps)
        return (total / price) ** 0.1 - 1 if total > 0 else None

    def _expected_return(self, ws, ws_values, ledger, review, hist) -> bool:
        review.findings = [f for f in review.findings if f.topic != "expected_return"]         # the earlier ROE reading is replaced by this check
        review.alternatives.pop("expected_return", None)
        model = _cell(ws_values, "F14") if _cell(ws_values, "F14") is not None else _cell(ws_values, "E14")
        if model is None:
            shown = [ws_values["F14"].value, ws_values["E14"].value]
            if any(isinstance(x, str) and x.startswith("#") for x in shown):
                model = float("nan")                          # the template's own formula fails (for example a negative average ROE): treated as unusable
            else:
                review.skipped.append("Expected return: the model's return is not calculated in this workbook.")
                return False
        if ER_LOW <= model <= ER_HIGH:
            review.findings.append(ReviewFinding(
                "expected_return", "model_return", "reasonable",
                f"The expected return of {_pct(model)} is within a realistic range of {_pct(ER_LOW)} to {_pct(ER_HIGH)}.", {"model": model},
            ))
            return False
        side = "not meaningful" if model != model else "too high" if model > ER_HIGH else "negative"
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

        # 1. the inputs of the model: the average ROE (A14) and the average retained earnings (C5)
        repaired, tried = self._repair_inputs(ws, ws_values, ledger, review, hist, model=model, side=side, price=price, pe=pe, bv0=bv0, payout=payout)
        if repaired:
            return True

        # 2. the other model, only when EPS follows a steady trend; 3. otherwise the model stays and the observations are red flags
        eps_hist = hist.get("eps") or {}
        trend = eps_trend(eps_hist) if eps_hist else None
        if trend is not None and not trend.reasonable and len(eps_hist) >= MIN_YEARS:
            return self._red_flags(ws, ledger, review, hist, model=model, side=side, trend_reason=trend.reason, tried=tried)

        if abs(growth) > EPS_GROWTH_LIMIT and not (eps_hist and review_eps_growth(eps_hist, growth).skewed):
            return keep(f"the EPS growth rate of {_pct(growth)} a year is too extreme to project for ten years")
        used_growth, growth_note = growth, ""
        if eps_hist:
            rg = review_eps_growth(eps_hist, growth)
            if rg.skewed and rg.robust is not None:
                used_growth = rg.robust
                growth_note = (f" (the rate of the years without extraordinary EPS: {_years_text(rg.extraordinary)} are left out; "
                               f"the first-to-last-year rate was {_pct(growth)})")
        if abs(used_growth) > EPS_GROWTH_LIMIT:
            return keep(f"the EPS growth rate of {_pct(used_growth)} a year is too extreme to project for ten years")
        new_roe = round(eps0 / bv0, 4)
        new_growth = round(used_growth, 4)
        new_return = self._model_return(price, pe, bv0, new_growth, new_roe, payout)
        if new_return is None:
            return keep("it gives no meaningful result")
        why = (
            f"the original model, which grows book value by retention times return on equity, gave {_pct(model)}, which is {side} to rely on "
            f"(a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)})"
        )
        extras = review.extra_notes.setdefault("expected_return", [])           # separate short notes: one note holds at most 400 characters
        if tried:
            extras.append(note(tried[0].upper() + tried[1:].rstrip("."), None, ER_INPUTS_SOURCE, because=False))
        if trend is not None and trend.reasonable:
            extras.append(note(f"The EPS-growth model was chosen because {trend.reason}", None, ER_SOURCE, because=False))
        # The ratios in A14 and A11 are never replaced: the alternative scenario is described in the notes and the HAP Adjustments tab.
        scenario = (f"Alternative scenario (not applied): the EPS-growth model with EPS growth of {_pct(used_growth)} a year{growth_note} "
                    f"from current EPS of ${eps0:,.2f} (return on equity {_pct(new_roe)}) would give {_pct(new_return)} instead of {_pct(model)}")
        extras.append(note(scenario, None, ER_SOURCE, because=False))
        extras.append(note(f"The ratios in the model were kept as they are: {_pct(model)} is {side} to rely on (a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)})", None, None, because=False))
        review.left_as_is["expected_return"] = "the ratios were kept; the alternative EPS-growth scenario is in the notes"
        ledger.record(sheet=ER_SHEET, cell="F14", fiscal_year=None, category="Expected return input", what="Expected return: alternative scenario (ratios not changed)",
                      original=_pct(model), new="unchanged", amount=new_return, reason=f"{scenario}; {why}.", source=ER_SOURCE, method="flag_only",
                      confidence="medium", mark_cell=False, status="Red flag")
        review.findings.append(ReviewFinding("expected_return", "model_return", "flag", why[0].upper() + why[1:] + ".", {"model": model, "alternative": new_return}))
        return True

    def _repair_inputs(self, ws, ws_values, ledger, review, hist, *, model, side, price, pe, bv0, payout) -> tuple[bool, str]:
        """Recalculate A14 and/or C5 without the years that are clearly off. Returns (done, a sentence about what was tried)."""
        roe_h, ret_h = hist.get("roe") or {}, hist.get("retention") or {}
        avg_roe, retention = _cell(ws_values, "A14"), _cell(ws_values, "C5")
        if avg_roe is None or retention is None or str(ws["A11"].value or "").replace(" ", "").upper() != "=C5*A14":
            return False, ""
        bad_roe, bad_ret = off_years(roe_h), off_years(ret_h)
        if not bad_roe and not bad_ret:
            return False, ""
        if len(bad_roe) > MAX_OFF_SHARE * len(roe_h) or len(bad_ret) > MAX_OFF_SHARE * len(ret_h):
            return False, ""                       # not a few years: the whole history is noisy
        new_roe = trimmed_mean(roe_h, bad_roe) if bad_roe else avg_roe
        new_ret = trimmed_mean(ret_h, bad_ret) if bad_ret else retention
        if new_roe is None or new_ret is None:
            return False, ""
        new_return = self._model_return(price, pe, bv0, new_ret * new_roe, new_roe, payout)
        parts = []
        if bad_roe:
            parts.append(f"the average return on equity without {_years_text(bad_roe)} is {_pct(new_roe)} (it was {_pct(avg_roe)})")
        if bad_ret:
            parts.append(f"the average retained earnings without {_years_text(bad_ret)} is {_pct(new_ret)} (it was {_pct(retention)})")
        recalculated = " and ".join(parts)
        if new_return is None or not (ER_LOW <= new_return <= ER_HIGH):
            outcome = "no meaningful result" if new_return is None else f"a return of {_pct(new_return)}, still {'too high' if new_return > ER_HIGH else 'negative'}"
            return False, f"the model's own inputs were recalculated first ({recalculated}), but that still gives {outcome}"
        why = (
            f"the return of {_pct(model)} was {side} to rely on (a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)}), and it rested on "
            f"{'return on equity' if bad_roe else ''}{' and ' if bad_roe and bad_ret else ''}{'retained earnings' if bad_ret else ''} "
            f"distorted by a few unusual years, so the model itself was kept"
        )
        # The inputs are never replaced: the recalculated averages and the return they give are described as an alternative scenario.
        scenario = f"Alternative scenario (not applied): {recalculated}, which would give a return of {_pct(new_return)} instead of {_pct(model)}"
        review.extra_notes.setdefault("expected_return", []).extend([
            note(scenario, None, ER_INPUTS_SOURCE, because=False),
            note(f"The ratios in the model were kept as they are: {_pct(model)} is {side} to rely on (a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)})", None, None, because=False),
        ])
        review.left_as_is["expected_return"] = "the ratios were kept; the alternative with the unusual years left out is in the notes"
        ledger.record(sheet=ER_SHEET, cell="F14", fiscal_year=None, category="Expected return input", what="Expected return: alternative scenario (ratios not changed)",
                      original=_pct(model), new="unchanged", amount=new_return, reason=f"{scenario}; {why}.", source=ER_INPUTS_SOURCE, method="flag_only",
                      confidence="medium", mark_cell=False, status="Red flag")
        review.findings.append(ReviewFinding("expected_return", "model_return", "flag", why[0].upper() + why[1:] + ".", {"model": model, "alternative": new_return}))
        return True, ""

    def _red_flags(self, ws, ledger, review, hist, *, model, side, trend_reason, tried) -> bool:
        """The history is cyclical and EPS is too: keep the model as it is and write every observation as a red flag."""
        roe_h, ret_h = hist.get("roe") or {}, hist.get("retention") or {}
        flags = [f"The expected return of {_pct(model)} is {side} to rely on (a realistic range is {_pct(ER_LOW)} to {_pct(ER_HIGH)})"]
        if roe_h:
            flags.append(f"Return on equity ranged from {_pct(min(roe_h.values()))} to {_pct(max(roe_h.values()))} over {len(roe_h)} years, so its average is not a stable base")
        if ret_h:
            flags.append(f"Retained earnings ranged from {_pct(min(ret_h.values()))} to {_pct(max(ret_h.values()))} of EPS, so growth from retention is not stable either")
        flags.append(f"The EPS-growth model is not a better base because {trend_reason}")
        if tried:
            flags.append(tried[0].upper() + tried[1:])
        text = ". ".join(f.rstrip(".") for f in flags) + "."
        for f in flags:
            review.findings.append(ReviewFinding("expected_return", "red_flag", "flag", f.rstrip(".") + ".", {"model": model}))
        review.left_as_is["expected_return"] = "the business looks cyclical in return on equity, retention and EPS, so no other model is better; the red flags are for your judgment"
        ledger.record(sheet=ER_SHEET, cell="F14", fiscal_year=None, category="Expected return input", what="Expected return left as the model gives it (red flags)",
                      original=_pct(model), new="unchanged", amount=None, reason=text, source=ER_INPUTS_SOURCE, method="flag_only",
                      confidence="low", mark_cell=False, status="Red flag")
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
        # The rate in C6 is never replaced. Three outcomes are discussed: the log-linear model (Final Metrics N10) when it is more
        # conservative and fits well, the ratio model already in the cell, or neither when the history is too irregular for any model.
        fit = loglinear(series)
        g3 = alt
        gll = fit.growth if fit else None
        numbers = (
            f"The ratio model in the cell (first three against last three years of owner's earnings) gives {_pct(annual)} a year"
            f" and the 3-year-average rate (Final Metrics M10) gives {_pct(g3)}"
            + (f"; the log-linear model through all {len(series)} years (Final Metrics N10) gives {_pct(gll)} a year and explains {fit.r2:.0%} of the movement (R2)"
               if fit else "; the log-linear model cannot be fitted because owner's earnings include zero or negative years")
        )
        if fit is not None and fit.r2 >= TREND_R2 and gll < annual:
            verdict = "log-linear"
            conclusion = (f"We recommend the log-linear model at {_pct(gll)}: it is more conservative than the ratio model's {_pct(annual)} and its R2 of {fit.r2:.0%} "
                          "is high enough for the trend to be reliable")
        elif fit is not None and fit.r2 >= TREND_R2:
            verdict = "ratio"
            conclusion = (f"We stay with the ratio model in the cell at {_pct(annual)}: the log-linear model fits well (R2 {fit.r2:.0%}) "
                          f"but is not more conservative at {_pct(gll)}")
        else:
            verdict = "none"
            conclusion = ("Neither model describes the company's dynamics: "
                          + (f"a straight-line fit explains only {fit.r2:.0%} of the movement in owner's earnings, " if fit else "owner's earnings include zero or negative years, ")
                          + "which points to strong seasonality, cyclicality or one-off items, so any single growth rate should be treated with caution")
        years = list(series)
        typical = statistics.median(series.values())
        if annual > OE_HIGH:
            reason = f"{_pct(annual)} a year is very high to project forward"
        elif annual < 0:
            reason = f"{_pct(annual)} a year is negative"
        else:
            reason = f"{_pct(annual)} a year looks unrealistically low"
        if series[years[0]] < 0.6 * typical and annual > OE_HIGH:
            reason += f", and it rests on {years[0]}, when owner's earnings were only {series[years[0]]:,.0f} against a typical {typical:,.0f}"
        review.extra_notes.setdefault("owner_earnings", []).extend([
            note(numbers, None, EV_SOURCE, because=False),
            note(conclusion, None, None, because=False),
        ])
        review.left_as_is["owner_earnings"] = f"The growth rate in the cell was kept as it is ({reason}); {conclusion[0].lower() + conclusion[1:]}"
        ledger.record(sheet=EV_SHEET, cell="C6", fiscal_year=None, category="Enterprise value input", what="Owner's earnings growth: model discussion (cell not changed)",
                      original=_pct(annual), new="unchanged", amount=None, reason=f"{reason}. {numbers}. {conclusion}.", source=EV_SOURCE,
                      method="flag_only", confidence="medium", mark_cell=False, status="Discussion")
        return True

    # ------------------------------------------------------------------ Graham: the EPS growth rate (EV tab B41)
    def _graham(self, ws, ws_values, ledger, review, hist) -> bool:
        eps_hist = hist.get("eps") or {}
        endpoint = _cell(ws_values, "B41")
        if endpoint is None or len(eps_hist) < MIN_YEARS:
            return False
        rg = review_eps_growth(eps_hist, endpoint)
        if not rg.skewed or rg.robust is None:
            review.findings.append(ReviewFinding("graham", "eps_growth", "reasonable",
                                                 f"The EPS growth rate of {_pct(endpoint)} a year used for the Graham entry price is not skewed by extraordinary years.",
                                                 {"endpoint": endpoint, "robust": rg.robust}))
            return False
        corrected = round(rg.robust, 4)
        # The rate in B41 is kept. What the Graham entry price would be with the adjusted rate is written as a comment only.
        current_entry = self._graham_entry(ws_values, endpoint)
        adjusted_entry = self._graham_entry(ws_values, corrected)
        why = (f"EPS was extraordinary in {_years_text(rg.extraordinary)}, which skews the first-to-last-year rate; "
               f"the steady growth of the other years is {_pct(corrected)}"
               + (f" (the fit explains {rg.r2:.0%} of their movement)" if rg.r2 is not None else ""))
        price = (f"Graham entry price would move from ${current_entry:,.2f} to ${adjusted_entry:,.2f} with the adjusted EPS growth model"
                 if current_entry is not None and adjusted_entry is not None else "The Graham entry price under the adjusted rate could not be computed")
        text = f"The EPS growth rate of {_pct(endpoint)} used for the Graham entry price was kept. {why[0].upper() + why[1:]}. {price}."
        ledger.record(sheet=EV_SHEET, cell="B41", fiscal_year=None, category="Enterprise value input", what="EPS growth for the Graham entry price: adjusted alternative (cell not changed)",
                      original=_pct(endpoint), new="unchanged", amount=adjusted_entry, reason=text, source=GRAHAM_SOURCE,
                      method="flag_only", confidence="medium", mark_cell=False, status="Discussion")
        review.left_as_is["graham"] = text
        review.extra_notes.setdefault("graham", []).append(note(price, None, GRAHAM_SOURCE, because=False))
        review.findings.append(ReviewFinding("graham", "eps_growth", "flag", text, {"endpoint": endpoint, "robust": rg.robust,
                                                                                    "entry_current": current_entry, "entry_adjusted": adjusted_entry}))
        return True

    @staticmethod
    def _graham_entry(ws_values, growth: float) -> float | None:
        """Entry target price (EV tab B48) recomputed for a given EPS growth rate, with the sheet's own formulas."""
        eps, pe, mult, req = (_cell(ws_values, a) for a in ("B40", "B51", "B52", "B53"))
        if None in (eps, pe, mult, req) or (1 + req) <= 0:
            return None
        g7 = min(growth, 0.07)
        value_7 = eps * (1 + growth) ** 7 * ((g7 * 100) * mult + pe)
        return value_7 / (1 + req) ** 7
