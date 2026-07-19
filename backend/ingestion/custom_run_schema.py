"""Semantic sections consumed by CustomRunData (not invented worksheet names)."""

from __future__ import annotations

REQUIRED_SECTIONS: tuple[str, ...] = (
    "metadata",
    "market_data",
    "historical_metrics",
    "proprietary_metrics",
    "valuation_metrics",
    "quality_metrics",
    "assumptions",
)

REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "Ticker",
    "Company Name",
    "Currency",
    "Fiscal Year End",
)

REQUIRED_MARKET_DATA_FIELDS: tuple[str, ...] = (
    "Share Price",
    "Market Cap",
    "Shares Outstanding",
)
