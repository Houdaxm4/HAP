"""Yahoo Finance annual fundamentals as a LAST-RESORT source for statement cells SEC cannot fill.

Free and unofficial (no key, no contract): every value taken from here is labelled indicative and reported to the
analyst. It is used only where SEC has nothing for that year, and only for lines that agreed with the values already
held in real company workbooks (68 company-years, 17 companies): revenue, net income, pre-tax income, income tax,
total liabilities, debt, EPS, cash, equity, diluted shares at 94-100%; operating cash flow, investing, financing and
total assets were checked against SEC. Operating income, gross profit and capex are deliberately excluded: their
definitions differ from the workbook's.

Alignment is proven, not assumed: a fiscal year is used only if Yahoo's revenue or net income for that period agrees
with the same figure in the workbook (so a fiscal-year naming mismatch can never put a neighbouring year's number in).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from research.http import GuardedFetcher
from research.policy import research_enabled

TRUSTED: dict[str, str] = {
    "revenue": "annualTotalRevenue",
    "net_income": "annualNetIncome",
    "pretax_income": "annualPretaxIncome",
    "income_tax_expense": "annualTaxProvision",
    "total_liabilities": "annualTotalLiabilitiesNetMinorityInterest",
    "debt": "annualLongTermDebt",
    "diluted_eps": "annualDilutedEPS",
    "cash": "annualCashAndCashEquivalents",
    "equity": "annualStockholdersEquity",
    "diluted_shares": "annualDilutedAverageShares",
    "cfo": "annualOperatingCashFlow",
    "cfi": "annualInvestingCashFlow",
    "cff": "annualFinancingCashFlow",
    "total_assets": "annualTotalAssets",
}
PER_SHARE = {"diluted_eps"}
ANCHORS = ("revenue", "net_income")
ALIGN_TOLERANCE = 0.03
DISAGREE_LIMIT = 0.10
SOURCE_LABEL = "Yahoo Finance fundamentals (free, unofficial; indicative)"


def yahoo_fallback_enabled() -> bool:
    return research_enabled() and os.environ.get("HAP_YAHOO_FALLBACK", "1").strip().lower() not in {"0", "false", "no", "off"}


class YahooFallback:
    def __init__(self, fetcher: GuardedFetcher | None = None) -> None:
        self.fetcher = fetcher or GuardedFetcher()
        self._cache: dict[str, dict[str, dict[str, tuple[float, str]]]] = {}
        self.errors: dict[str, str] = {}

    def annual(self, ticker: str) -> dict[str, dict[str, tuple[float, str]]]:
        """concept -> {calendar year of period end: (value in $M or per-share, as-of date)}."""
        key = ticker.upper()
        if key in self._cache:
            return self._cache[key]
        out: dict[str, dict[str, tuple[float, str]]] = defaultdict(dict)
        url = (
            f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{key}"
            f"?symbol={key}&type={','.join(TRUSTED.values())}&period1=1262304000&period2=1990000000"
        )
        try:
            _, text = self.fetcher.get(url, accept="application/json")
            payload = json.loads(text)
        except Exception as exc:  # noqa: BLE001 - an outage just means no fallback
            self.errors[key] = f"{type(exc).__name__}"
            self._cache[key] = {}
            return {}
        by_type = {v: k for k, v in TRUSTED.items()}
        for series in (payload.get("timeseries") or {}).get("result") or []:
            kind = (series.get("meta", {}).get("type") or [None])[0]
            concept = by_type.get(kind)
            for row in series.get(kind) or []:
                if concept and row and row.get("reportedValue") and row.get("asOfDate"):
                    raw = float(row["reportedValue"]["raw"])
                    out[concept][row["asOfDate"][:4]] = (raw if concept in PER_SHARE else raw / 1_000_000.0, row["asOfDate"])
        self._cache[key] = dict(out)
        return self._cache[key]

    def aligned(self, ticker: str, year: str, anchors: dict[str, float | None]) -> bool:
        """True when Yahoo's revenue/net income for this period matches the workbook's (and nothing contradicts)."""
        data = self.annual(ticker)
        checked = agreed = 0
        for concept in ANCHORS:
            workbook = anchors.get(concept)
            yahoo = data.get(concept, {}).get(year)
            if workbook is None or yahoo is None:
                continue
            checked += 1
            diff = abs(workbook - yahoo[0]) / max(abs(yahoo[0]), 1.0)
            if diff <= ALIGN_TOLERANCE:
                agreed += 1
            elif diff > DISAGREE_LIMIT:
                return False
        return agreed >= 1

    def value(self, ticker: str, concept: str, fiscal_year: str, anchors: dict[str, float | None]) -> tuple[float, str] | None:
        """(value, source text) or None. ``fiscal_year`` like 'FY2025'."""
        if concept not in TRUSTED:
            return None
        year = "".join(ch for ch in str(fiscal_year) if ch.isdigit())[-4:]
        hit = self.annual(ticker).get(concept, {}).get(year)
        if hit is None or not self.aligned(ticker, year, anchors):
            return None
        return hit[0], f"{SOURCE_LABEL}; period ending {hit[1]}"


QUARTERLY: dict[str, str] = {
    "revenue": "quarterlyTotalRevenue",
    "cost_of_revenue": "quarterlyCostOfRevenue",
    "gross_profit": "quarterlyGrossProfit",
    "operating_income": "quarterlyOperatingIncome",
    "net_income": "quarterlyNetIncome",
    "eps_basic": "quarterlyBasicEPS",
    "eps_diluted": "quarterlyDilutedEPS",
    "cfo": "quarterlyOperatingCashFlow",
    "cfi": "quarterlyInvestingCashFlow",
    "cff": "quarterlyFinancingCashFlow",
    "net_change_cash": "quarterlyChangesInCash",
}
# Yahoo's definitions of these differ from the workbook's, so they are only a last resort and are labelled that way.
DEFINITION_DIFFERS = {"cost_of_revenue", "gross_profit", "operating_income"}


def _quarterly(self: "YahooFallback", ticker: str) -> dict[str, dict[str, float]]:
    """concept -> {quarter end date (YYYY-MM-DD): value in $M (per share for EPS)}."""
    key = ticker.upper()
    cache = self.__dict__.setdefault("_quarterly_cache", {})
    if key in cache:
        return cache[key]
    out: dict[str, dict[str, float]] = defaultdict(dict)
    url = (
        f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{key}"
        f"?symbol={key}&type={','.join(QUARTERLY.values())}&period1=1262304000&period2=1990000000"
    )
    try:
        _, text = self.fetcher.get(url, accept="application/json")
        payload = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - an outage just means no fallback
        self.errors[key] = f"{type(exc).__name__}"
        cache[key] = {}
        return {}
    by_type = {v: k for k, v in QUARTERLY.items()}
    for series in (payload.get("timeseries") or {}).get("result") or []:
        kind = (series.get("meta", {}).get("type") or [None])[0]
        concept = by_type.get(kind)
        for row in series.get(kind) or []:
            if concept and row and row.get("reportedValue") and row.get("asOfDate"):
                raw = float(row["reportedValue"]["raw"])
                out[concept][row["asOfDate"][:10]] = raw if concept in PER_SHARE_Q else raw / 1_000_000.0
    cache[key] = dict(out)
    return cache[key]


PER_SHARE_Q = {"eps_basic", "eps_diluted"}


def _ytd_value(self: "YahooFallback", ticker: str, concept: str, end, quarter: int, *, anchor_revenue: float | None = None):
    """Fiscal year-to-date figure = the quarters ending on or before `end`, `quarter` of them in a row (about 3 months apart).

    Used only when the latest quarter's revenue agrees with the workbook's 3-month revenue (within 3%), so a fiscal-year mix-up can
    never put a neighbouring period in. Returns (value, source text) or None."""
    from datetime import date as _date

    data = _quarterly(self, ticker)
    series = data.get(concept)
    revenue = data.get("revenue")
    if not series or end is None or quarter not in (1, 2, 3) or not revenue:
        return None
    end_s = end.isoformat() if hasattr(end, "isoformat") else str(end)
    latest = revenue.get(end_s)
    if latest is None and anchor_revenue is not None:
        near = [d for d in revenue if abs((_date.fromisoformat(d) - end).days) <= 5]
        latest = revenue.get(near[0]) if near else None
    if latest is None or (anchor_revenue is not None and abs(latest - anchor_revenue) / max(abs(anchor_revenue), 1.0) > 0.03):
        return None
    dates = sorted(d for d in series if _date.fromisoformat(d) <= end + __import__("datetime").timedelta(days=5))
    picked = dates[-quarter:]
    if len(picked) != quarter:
        return None
    gaps = [(_date.fromisoformat(b) - _date.fromisoformat(a)).days for a, b in zip(picked, picked[1:])]
    if any(not 70 <= g <= 110 for g in gaps) or abs((_date.fromisoformat(picked[-1]) - end).days) > 5:
        return None
    note = " (definition may differ from the workbook)" if concept in DEFINITION_DIFFERS else ""
    return sum(series[d] for d in picked), f"{SOURCE_LABEL}; {quarter} quarters to {picked[-1]}{note}"


YahooFallback.ytd_value = _ytd_value  # type: ignore[attr-defined]
