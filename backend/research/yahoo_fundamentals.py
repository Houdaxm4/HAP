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
