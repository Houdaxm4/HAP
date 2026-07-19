"""Domain model for parsed Bloomberg Custom_Run_Filter proprietary data."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricSeries(BaseModel):
    """One proprietary or historical metric with values across reporting periods."""

    metric: str
    unit: str | None = None
    values: dict[str, float | str | None] = Field(default_factory=dict)


class CustomRunValidationIssue(BaseModel):
    """Single validation finding for a Custom_Run workbook."""

    check: str
    status: str  # pass | warn | fail
    message: str
    worksheet: str | None = None
    field: str | None = None


class CustomRunValidationReport(BaseModel):
    """Output of Custom_Run workbook validation."""

    source_filename: str
    ticker: str
    is_valid: bool
    checks: list[CustomRunValidationIssue] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    summary: str = ""


class CustomRunData(BaseModel):
    """
    Strongly typed representation of imported Bloomberg Custom_Run_Filter data.

    This is the canonical ingestion output. Downstream stages must consume
    CustomRunData — never raw workbook cells or user mapping tables.
    """

    source_filename: str
    metadata: dict[str, str] = Field(default_factory=dict)
    market_data: dict[str, float | str | None] = Field(default_factory=dict)
    historical_metrics: list[MetricSeries] = Field(default_factory=list)
    proprietary_metrics: list[MetricSeries] = Field(default_factory=list)
    valuation_metrics: list[MetricSeries] = Field(default_factory=list)
    quality_metrics: list[MetricSeries] = Field(default_factory=list)
    assumptions: dict[str, float | str | None] = Field(default_factory=dict)
    worksheets_found: list[str] = Field(default_factory=list)
    raw_sections: dict[str, Any] = Field(default_factory=dict)

    @property
    def ticker(self) -> str:
        return self.metadata.get("Ticker", "").upper()

    @property
    def company_name(self) -> str:
        return self.metadata.get("Company Name", "")

    def all_metric_series(self) -> list[MetricSeries]:
        """Return every time-series metric across proprietary sections."""
        return [
            *self.historical_metrics,
            *self.proprietary_metrics,
            *self.valuation_metrics,
        ]
