"""Current market price lookup for Inputs!Current Price (live)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class MarketPriceService:
    """
    Fetch a live share price for Inputs current-data completion.

    Never substitutes Bloomberg CRF stale price as live current, except in a point-in-time back-test, where the batch registers the
    quarter's price from the custom run filter history (a live quote would be today's price, not the period's).
    """

    _point_in_time: dict[str, tuple[float, str]] = {}

    @classmethod
    def set_point_in_time(cls, ticker: str, price: float, source: str) -> None:
        cls._point_in_time[ticker.strip().upper()] = (float(price), source)

    @classmethod
    def clear_point_in_time(cls, ticker: str | None = None) -> None:
        if ticker is None:
            cls._point_in_time.clear()
        else:
            cls._point_in_time.pop(ticker.strip().upper(), None)

    def get_price(self, ticker: str) -> tuple[float | None, str | None]:
        """
        Return (price, source_label). Both None when unavailable.
        """
        symbol = (ticker or "").strip().upper()
        if not symbol:
            return None, None
        if symbol in self._point_in_time:
            return self._point_in_time[symbol]
        price = self._yahoo_chart(symbol)
        if price is not None:
            return price, "market_internet:yahoo_chart"
        return None, None

    @staticmethod
    def _yahoo_chart(symbol: str) -> float | None:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?range=1d&interval=1m"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "HAP2-ModeA/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
        try:
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                return None
            meta = result[0].get("meta") or {}
            for key in ("regularMarketPrice", "postMarketPrice", "previousClose"):
                val = meta.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
        except (TypeError, IndexError, KeyError, AttributeError):
            return None
        return None
