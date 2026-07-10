"""custom_run filter mapping and validation models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CustomRunEntry(BaseModel):
    """
    One row from the custom_run filter file.

    Tells HAP exactly which workbook cell to populate and which financial
    concept / reporting period to source from SEC filings.
    """

    workbook: str = "prefilled_workbook"
    worksheet: str
    cell: str
    concept: str
    period: str
    xbrl_tag: str | None = None
    unit: str | None = None
    notes: str | None = None
    ticker: str | None = None
    fiscal_date: str | None = None
    value: float | None = None
    row_number: int | None = None
    # Parsed period components (populated during validation).
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    is_annual: bool = False
    period_alias: str | None = None


class CustomRunMapping(BaseModel):
    """Parsed custom_run filter for an analysis."""

    source_filename: str
    entry_count: int
    columns_found: list[str] = Field(default_factory=list)
    entries: list[CustomRunEntry] = Field(default_factory=list)


class CustomRunValidationIssue(BaseModel):
    """One check result in the custom_run_filter validation report."""

    check_type: Literal[
        "required_columns",
        "ticker",
        "fiscal_dates",
        "quarter_sequence",
        "duplicate_periods",
        "missing_quarters",
        "numeric_consistency",
        "workbook_reference",
    ]
    status: Literal["pass", "warn", "fail"]
    message: str
    row_number: int | None = None
    concept: str | None = None
    period: str | None = None
    cell_ref: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CustomRunValidationReport(BaseModel):
    """
    Validation report for an uploaded custom_run_filter.

    Produced before any template population. Does not modify workbooks.
    """

    analysis_id: str
    ticker: str
    source_filename: str
    entry_count: int
    columns_found: list[str] = Field(default_factory=list)
    checks: list[CustomRunValidationIssue] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    is_valid: bool = False
    summary: str = ""
