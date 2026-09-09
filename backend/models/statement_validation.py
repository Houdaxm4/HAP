"""Post-completion financial statement validation models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StatementValidationDecision(str, Enum):
    VALIDATED = "VALIDATED"
    DISCREPANCY = "DISCREPANCY"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    SOURCE_MISSING = "SOURCE_MISSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class StatementValidationEntry(BaseModel):
    statement: str
    metric: str
    workbook_cell: str
    workbook_label: str | None = None
    fiscal_period: str
    workbook_value: float | None = None
    sec_value: float | None = None
    absolute_difference: float | None = None
    percentage_difference: float | None = None
    sec_concept: str | None = None
    filing_form: str | None = None
    accession_number: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    decision: StatementValidationDecision
    reason: str
    scale: str = "USD_millions"


class StatementValidationReport(BaseModel):
    """Machine-readable artifact: statement_validation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "financial_statement_validation_analyst_review"
    entries: list[StatementValidationEntry] = Field(default_factory=list)
    validated_count: int = 0
    discrepancy_count: int = 0
    not_comparable_count: int = 0
    source_missing_count: int = 0
    review_required_count: int = 0
    materiality_rules: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
