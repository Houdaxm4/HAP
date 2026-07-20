"""Custom_Run_Filter domain model — Bloomberg proprietary analytics (HAP v1).

Per the Master Specification, custom_run_filter.xlsx contains internal proprietary
analytics. HAP imports and validates these metrics; it never recalculates them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CustomRunPeriods(BaseModel):
    """Aligned period axes for historical series on the ticker sheet."""

    dates: list[str] = Field(default_factory=list)
    fiscal_quarters: list[str] = Field(default_factory=list)
    fiscal_years: list[str] = Field(default_factory=list)


class CustomRunSeries(BaseModel):
    """One historical metric aligned to ``CustomRunPeriods``."""

    label: str
    values: list[float | None] = Field(default_factory=list)
    kind: str = "quarterly"  # quarterly | annual_aligned | other


class CustomRunData(BaseModel):
    """
    Strongly typed import of a Bloomberg-derived Custom_Run_Filter workbook.

    Logical sections keep workbook-specific layout out of the rest of HAP.
    """

    source_filename: str
    ticker: str
    company: str | None = None
    ticker_sheet_name: str

    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    market_data: dict[str, Any] = Field(default_factory=dict)
    historical_metrics: dict[str, CustomRunSeries] = Field(default_factory=dict)
    proprietary_metrics: dict[str, Any] = Field(default_factory=dict)
    valuation_metrics: dict[str, Any] = Field(default_factory=dict)
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    scalars: dict[str, Any] = Field(default_factory=dict)
    periods: CustomRunPeriods = Field(default_factory=CustomRunPeriods)

    period_count: int = 0
    series_count: int = 0
    summary_field_count: int = 0

    def series_for(self, label: str) -> CustomRunSeries | None:
        return self.historical_metrics.get(label)

    def scalar(self, *keys: str) -> Any | None:
        """Return the first non-None value found across summary / scalars / metadata / sections."""
        pools = (
            self.summary,
            self.scalars,
            self.metadata,
            self.market_data,
            self.valuation_metrics,
            self.quality_metrics,
            self.proprietary_metrics,
            self.assumptions,
        )
        for key in keys:
            for pool in pools:
                if key in pool and pool[key] is not None:
                    return pool[key]
        return None
