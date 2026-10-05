"""Realism review of the inputs behind Expected Return and Enterprise Value. Flags only: no model value is changed.

Expected Return (tab "Expected Returns & Buybacks") grows book value per share by retention x average ROE for ten years, then
prices the earnings. Both drivers can be distorted by extraordinary items, buybacks that shrink equity, or a few unusual years.
  - Average ROE: compared with the typical (median) year, with the range, and with one-time items that moved net income.
  - Book value per share growth: compared with the growth book value per share actually delivered, with ROE, and with sensible limits.

Enterprise Value (tab "Enterprise Value") extrapolates owner's earnings (OE) with the annualized change between the first and last year.
That rate is checked when it is very high, negative or unrealistically low, and when it depends on one unusual end-point year.

Every finding is a short sentence in plain language. Where something is flagged, an alternative is computed so it can be discussed.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.annual_period_service import detect_year_columns

ER_SHEET = "Expected Returns & Buybacks"
EV_SHEET = "Enterprise Value"
FM_SHEET = "Final Metrics"

ROE_HIGH, ROE_LOW = 0.30, 0.05
ROE_OUTLIER_SHARE = 0.25          # average ROE this far from the median year
BV_GROWTH_HIGH = 0.15
BV_GROWTH_GAP = 0.05              # vs the growth book value per share actually delivered
BVPS_DROP = 0.10                  # a year-on-year fall in book value per share
OE_HIGH, OE_LOW = 0.15, 0.02      # annualized owner's earnings growth
ONE_TIME_SHARE = 0.10             # one-time items as a share of net income

ONE_TIME_TAGS = ("GoodwillImpairmentLoss", "AssetImpairmentCharges", "RestructuringCharges", "LitigationSettlementExpense",
                 "BusinessCombinationAcquisitionRelatedCosts", "GainLossOnSaleOfPropertyPlantEquipment", "GainLossOnDispositionOfAssets")


@dataclass
class ReviewFinding:
    topic: str                  # expected_return | owner_earnings
    metric: str
    verdict: str                # reasonable | flag
    text: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppliedCorrection:
    topic: str                  # expected_return | owner_earnings
    cell: str                   # e.g. "Expected Returns & Buybacks!A14"
    original: Any
    new: Any
    kind: str                   # replaced | parallel
    what: str                   # what was done, plain language
    why: str                    # why, plain language
    source: str


@dataclass
class ValuationInputsReview:
    findings: list[ReviewFinding] = field(default_factory=list)
    alternatives: dict[str, Any] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    applied: list[AppliedCorrection] = field(default_factory=list)
    left_as_is: dict[str, str] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        """The review as plain data (saved next to the other reports)."""
        return {
            "flagged_for_discussion": [f.text for f in self.flagged],
            "findings": [{"topic": f.topic, "metric": f.metric, "verdict": f.verdict, "text": f.text} for f in self.findings],
            "alternatives": self.alternatives,
            "corrections_applied": [
                {"topic": a.topic, "cell": a.cell, "original": str(a.original), "new": a.new, "kind": a.kind, "what": a.what, "why": a.why}
                for a in self.applied
            ],
            "left_as_is": self.left_as_is,
            "skipped": self.skipped,
        }

    @property
    def flagged(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.verdict == "flag"]

    def notes(self, topic: str) -> list[str]:
        """Plain-language notes for the tab: what was checked, why, and the source."""
        from services.tab_notes import note

        items = [f for f in self.findings if f.topic == topic]
        if not items:
            return []
        if topic == "expected_return":
            checked = "the average return on equity and the book value growth used in the expected return"
            risk = "one-time items or a few unusual years can distort both"
            source = "the Final Metrics and Balance Sheet history"
        else:
            checked = "the owner's earnings growth rate used to project enterprise value"
            risk = "a very high, negative or very low rate, or one unusual start year, can distort the whole valuation"
            source = "the Final Metrics tab history"
        applied = [a for a in self.applied if a.topic == topic]
        if applied:
            out = [note(a.what, a.why, a.source) for a in applied]
            out.append(note("The original formulas and values are kept in the HAP Adjustments tab", "so any correction can be undone by hand", because=False))
            return out
        flagged = [f for f in items if f.verdict == "flag"]
        if not flagged:
            return [note(f"Reviewed {checked}, and they look realistic", "They are close to what the company actually delivered", source, because=False)]
        count = len(flagged)
        out = [note(f"Reviewed {checked} and flagged {count} point{'s' if count != 1 else ''}", risk, source)]
        out += [f.text.rstrip(".") + "." for f in flagged]
        alt = self.alternatives.get(topic)
        if alt:
            out.append(note(alt, "This shows the result on a more typical basis", source, because=False))
        reason = self.left_as_is.get(topic)
        out.append(note("No model value was changed", reason or "The flagged inputs are for your decision", because=False))
        return out


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _cagr(first: float | None, last: float | None, years: int) -> float | None:
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def _row_by_label(ws, label: str) -> int | None:
    for row in range(1, min(ws.max_row or 1, 80) + 1):
        if str(ws.cell(row, 1).value or "").strip().lower() == label:
            return row
    return None


class ValuationInputsReviewService:
    def review(self, workbook_path: Path, company_facts: dict[str, Any] | None = None) -> ValuationInputsReview:
        result = ValuationInputsReview()
        wb = load_workbook(workbook_path, data_only=True)
        wf = load_workbook(workbook_path, data_only=False)
        try:
            if FM_SHEET not in wb.sheetnames:
                result.skipped.append("Final Metrics tab missing.")
                return result
            fm = wb[FM_SHEET]
            cols = {k: c for k, c in detect_year_columns(wf[FM_SHEET], wf).items() if str(k).startswith("FY")}
            ordered = sorted(cols.items(), key=lambda kv: kv[1])
            if ER_SHEET in wb.sheetnames:
                self._expected_return(wb, wf, fm, ordered, result, company_facts)
            if EV_SHEET in wb.sheetnames:
                self._owner_earnings(wb, fm, ordered, result)
        finally:
            wb.close()
            wf.close()
        return result

    # ------------------------------------------------------------------ expected return
    def _expected_return(self, wb, wf, fm, ordered, result, facts) -> None:
        er = wb[ER_SHEET]
        g, avg_roe, retention = _num(er["A11"].value), _num(er["A14"].value), _num(er["C5"].value)
        roe_row = _row_by_label(fm, "roe")
        roes = {fy: _num(fm.cell(roe_row, col).value) for fy, col in ordered} if roe_row else {}
        roes = {fy: v for fy, v in roes.items() if v is not None}
        if avg_roe is None or g is None or not roes:
            result.skipped.append("Expected return inputs (A11, A14 or the ROE history) are not available.")
            return
        median = statistics.median(roes.values())
        spread = f"{_pct(min(roes.values()))} to {_pct(max(roes.values()))}"
        problems: list[str] = []
        extreme = [fy for fy, v in roes.items() if v < 0 or (median and (v > 2 * median or v < 0.3 * median))]
        if avg_roe > ROE_HIGH:
            problems.append(f"The average return on equity of {_pct(avg_roe)} is very high")
        elif avg_roe < ROE_LOW:
            problems.append(f"The average return on equity of {_pct(avg_roe)} is very low")
        if median and abs(avg_roe - median) / abs(median) > ROE_OUTLIER_SHARE:
            problems.append(f"The average return on equity of {_pct(avg_roe)} is pulled away from the typical year ({_pct(median)}) by a few unusual years ({', '.join(extreme) + '; ' if extreme else ''}range {spread})")
        if extreme and not any("pulled away" in p for p in problems):
            problems.append(f"Return on equity in {', '.join(extreme)} is far from the typical year ({_pct(median)})")
        one_time = self._one_time_years(wb, wf, ordered, facts)
        if one_time:
            problems.append("One-time items moved net income by more than 10% in " + ", ".join(f"{fy} ({share:.0%})" for fy, share in one_time))
        result.findings.append(ReviewFinding(
            "expected_return", "average_roe", "flag" if problems else "reasonable",
            ". ".join(p.rstrip(".") for p in problems) if problems else f"The average return on equity of {_pct(avg_roe)} is in line with the typical year ({_pct(median)})",
            {"average_roe": avg_roe, "median_roe": median, "roe_by_year": roes, "one_time_years": one_time}))

        bvps = self._bvps_series(wb, wf, er, ordered)
        hist = _cagr(next(iter(bvps.values()), None), next(reversed(bvps.values()), None), len(bvps) - 1) if len(bvps) > 1 else None
        problems = []
        if g > BV_GROWTH_HIGH:
            problems.append(f"Book value per share growth of {_pct(g)} a year for ten years is aggressive")
        if g < 0:
            problems.append(f"Book value per share growth of {_pct(g)} a year is negative")
        if g > avg_roe + 1e-9:
            problems.append(f"Book value per share growth of {_pct(g)} is higher than the return on equity of {_pct(avg_roe)}, which cannot last")
        if hist is not None and abs(g - hist) > BV_GROWTH_GAP:
            problems.append(f"Book value per share growth used ({_pct(g)}) differs from what the company delivered ({_pct(hist)} a year)")
        drops = [fy2 for (fy1, a), (fy2, b) in zip(list(bvps.items()), list(bvps.items())[1:]) if a and b < a * (1 - BVPS_DROP)]
        if drops:
            problems.append(f"Book value per share fell by more than 10% in {', '.join(drops)} (buybacks or write-offs), which weakens it as a growth base")
        result.findings.append(ReviewFinding(
            "expected_return", "book_value_growth", "flag" if problems else "reasonable",
            ". ".join(p.rstrip(".") for p in problems) if problems else f"Book value per share growth of {_pct(g)} a year is in line with what the company delivered",
            {"growth_used": g, "delivered_cagr": hist, "retention": retention, "bvps": bvps}))
        if any(f.verdict == "flag" for f in result.findings if f.topic == "expected_return"):
            alt = self._alternative_expected_return(er, median, retention)
            if alt:
                result.alternatives["expected_return"] = alt

    def _alternative_expected_return(self, er, median_roe: float, retention: float | None) -> str | None:
        bv, price, current = _num(er["B8"].value), _num(er["E2"].value), _num(er["A2"].value)
        if None in (bv, price, current, retention) or not current:
            return None
        g_alt = retention * median_roe
        bv10 = bv * (1 + g_alt) ** 10
        eps10 = bv10 * median_roe
        price10 = eps10 * price
        alt_er = (price10 / current) ** 0.1 - 1 if price10 > 0 else None
        used = _num(er["E14"].value)
        if alt_er is None or used is None:
            return None
        return (f"With the typical return on equity ({_pct(median_roe)}) the growth would be {_pct(g_alt)} a year and the expected return "
                f"{_pct(alt_er)} instead of {_pct(used)}")

    def _bvps_series(self, wb, wf, er, ordered) -> dict[str, float]:
        import re

        formula = str(wf[ER_SHEET]["B8"].value or "")
        bs_ref = re.search(r"'([^']+)'!\$?[A-Z]+\$?(\d+)", formula)
        sh_refs = re.findall(r"'([^']+)'!\$?[A-Z]+\$?(\d+)", formula)
        if len(sh_refs) < 2:
            return {}
        (bs_sheet, bs_row), (sh_sheet, sh_row) = sh_refs[0], sh_refs[1]
        if bs_sheet not in wb.sheetnames or sh_sheet not in wb.sheetnames:
            return {}
        bs_cols = {k: c for k, c in detect_year_columns(wf[bs_sheet], wf).items() if str(k).startswith("FY")}
        sh_cols = {k: c for k, c in detect_year_columns(wf[sh_sheet], wf).items() if str(k).startswith("FY")}
        out: dict[str, float] = {}
        for fy, _c in ordered:
            equity = _num(wb[bs_sheet].cell(int(bs_row), bs_cols[fy]).value) if fy in bs_cols else None
            shares = _num(wb[sh_sheet].cell(int(sh_row), sh_cols[fy]).value) if fy in sh_cols else None
            if equity is not None and shares:
                out[fy] = equity / shares
        return out

    @staticmethod
    def _one_time_years(wb, wf, ordered, facts) -> list[tuple[str, float]]:
        """Years where one-time SEC items (impairments, restructuring, gains) are 10% or more of net income."""
        if not facts:
            return []
        from services.roic_adjustment_service import facts_for_year
        from services.new_company_cumulative_service import _as_date

        income = "Income - GAAP"
        if income not in wb.sheetnames:
            return []
        ws, wsf = wb[income], wf[income]
        cols = {k: c for k, c in detect_year_columns(wsf, wf).items() if str(k).startswith("FY")}
        ni_row = None
        for row in range(1, min(ws.max_row or 1, 90) + 1):
            if str(ws.cell(row, 2).value or "").strip() == "NET_INCOME":
                ni_row = row
                break
        if not ni_row:
            return []
        flagged: list[tuple[str, float]] = []
        for fy, _c in ordered:
            col = cols.get(fy)
            if not col:
                continue
            ni = _num(ws.cell(ni_row, col).value)
            end = None
            for r in range(5, 12):
                end = _as_date(ws.cell(r, col).value)
                if end:
                    break
            if not ni or not end:
                continue
            total = 0.0
            for tag in ONE_TIME_TAGS:
                value = facts_for_year(facts, tag, end)
                if value:
                    total += abs(value) / 1_000_000.0
            if total / abs(ni) >= ONE_TIME_SHARE:
                flagged.append((fy, total / abs(ni)))
        return flagged

    # ------------------------------------------------------------------ owner's earnings
    def _owner_earnings(self, wb, fm, ordered, result) -> None:
        ev = wb[EV_SHEET]
        annual = _num(ev["C6"].value)
        oe_row = _row_by_label(fm, "owners earnings")
        if annual is None or not oe_row:
            result.skipped.append("Owner's earnings growth (Enterprise Value C6) or the owner's earnings history is not available.")
            return
        series = {fy: _num(fm.cell(oe_row, col).value) for fy, col in ordered}
        series = {fy: v for fy, v in series.items() if v is not None}
        years = list(series)
        problems: list[str] = []
        if annual > OE_HIGH:
            problems.append(f"Owner's earnings growth of {_pct(annual)} a year is very high to project forward")
        elif annual < 0:
            problems.append(f"Owner's earnings growth of {_pct(annual)} a year is negative")
        elif annual < OE_LOW:
            problems.append(f"Owner's earnings growth of {_pct(annual)} a year is unrealistically low")
        alt = None
        if len(years) >= 6:
            first3, last3 = statistics.mean(series[y] for y in years[:3]), statistics.mean(series[y] for y in years[-3:])
            alt = _cagr(first3, last3, len(years) - 3)
            typical = statistics.median(series.values())
            if series[years[0]] < 0.6 * typical and annual > OE_HIGH:
                problems.append(f"The rate depends on {years[0]}, when owner's earnings were only {series[years[0]]:,.0f} against a typical {typical:,.0f}")
            negatives = [y for y in years if series[y] < 0]
            if negatives:
                problems.append(f"Owner's earnings were negative in {', '.join(negatives)}")
        result.findings.append(ReviewFinding(
            "owner_earnings", "owner_earnings_growth", "flag" if problems else "reasonable",
            ". ".join(p.rstrip(".") for p in problems) if problems else f"Owner's earnings growth of {_pct(annual)} a year is in line with the company's history",
            {"annualized_growth": annual, "series": series, "three_year_average_cagr": alt}))
        if problems and alt is not None:
            discount, book, company_value, per_share = _num(ev["B2"].value), _num(ev["B17"].value), _num(ev["B19"].value), _num(ev["B20"].value)
            last = series[years[-1]]
            if None not in (discount, book, company_value, per_share) and per_share:
                shares = company_value / per_share
                pv = sum(last * (1 + alt) ** k / (1 + discount) ** k for k in range(1, 12))
                value_per_share = (pv + book) / shares
                result.alternatives["owner_earnings"] = (
                    f"Using the growth between the average of the first three and last three years ({_pct(alt)} a year) company value per share would be "
                    f"{value_per_share:,.0f} instead of {per_share:,.0f}"
                )
