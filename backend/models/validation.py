"""Workbook validation and discrepancy report models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ValidationCheck(BaseModel):
    """Single validation result for a populated or expected cell."""

    cell_ref: str
    worksheet: str
    cell: str
    concept: str
    period: str
    check_type: Literal[
        "value_match",
        "missing_value",
        "formula_preserved",
        "impossible_value",
        "inconsistency",
        "unfilled",
    ]
    status: Literal["pass", "warn", "fail"]
    expected_value: Any | None = None
    actual_value: Any | None = None
    message: str
    source_document: str | None = None
    xbrl_tag: str | None = None


class DiscrepancyReport(BaseModel):
    """Output of the validate_workbook stage."""

    analysis_id: str
    ticker: str
    checks: list[ValidationCheck] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    summary: str = ""
