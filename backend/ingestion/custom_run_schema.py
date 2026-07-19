"""Canonical Bloomberg-derived Custom_Run_Filter workbook structure (HAP v1)."""

from __future__ import annotations

# Standardized worksheet names used across all companies (AAPL, MSFT, AMZN, TJX, …).
SHEET_METADATA = "Metadata"
SHEET_MARKET_DATA = "Market Data"
SHEET_HISTORICAL_METRICS = "Historical Metrics"
SHEET_PROPRIETARY_METRICS = "Proprietary Metrics"
SHEET_VALUATION_METRICS = "Valuation Metrics"
SHEET_QUALITY_METRICS = "Quality Metrics"
SHEET_ASSUMPTIONS = "Assumptions"

REQUIRED_WORKSHEETS: tuple[str, ...] = (
    SHEET_METADATA,
    SHEET_MARKET_DATA,
    SHEET_HISTORICAL_METRICS,
    SHEET_PROPRIETARY_METRICS,
    SHEET_VALUATION_METRICS,
    SHEET_QUALITY_METRICS,
    SHEET_ASSUMPTIONS,
)

# Aliases tolerate minor Bloomberg export naming differences.
WORKSHEET_ALIASES: dict[str, str] = {
    "metadata": SHEET_METADATA,
    "company metadata": SHEET_METADATA,
    "market data": SHEET_MARKET_DATA,
    "marketdata": SHEET_MARKET_DATA,
    "historical metrics": SHEET_HISTORICAL_METRICS,
    "historical": SHEET_HISTORICAL_METRICS,
    "historical_metrics": SHEET_HISTORICAL_METRICS,
    "proprietary metrics": SHEET_PROPRIETARY_METRICS,
    "proprietary": SHEET_PROPRIETARY_METRICS,
    "proprietary_metrics": SHEET_PROPRIETARY_METRICS,
    "valuation metrics": SHEET_VALUATION_METRICS,
    "valuation": SHEET_VALUATION_METRICS,
    "valuation_metrics": SHEET_VALUATION_METRICS,
    "quality metrics": SHEET_QUALITY_METRICS,
    "quality": SHEET_QUALITY_METRICS,
    "quality_metrics": SHEET_QUALITY_METRICS,
    "assumptions": SHEET_ASSUMPTIONS,
    "assumption": SHEET_ASSUMPTIONS,
}

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

# Time-series sheets: row 1 = period headers from column B; column A = metric name.
TIME_SERIES_SHEETS: frozenset[str] = frozenset(
    {SHEET_HISTORICAL_METRICS, SHEET_PROPRIETARY_METRICS, SHEET_VALUATION_METRICS}
)

# Key-value sheets: column A = field, column B = value.
KEY_VALUE_SHEETS: frozenset[str] = frozenset(
    {SHEET_METADATA, SHEET_MARKET_DATA, SHEET_QUALITY_METRICS, SHEET_ASSUMPTIONS}
)
