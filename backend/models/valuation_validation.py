"""Valuation / margin-of-safety / entry-price validation models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ValuationDecision(str, Enum):
    VALIDATED = "VALIDATED"
    WATCH = "WATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DISCREPANCY = "DISCREPANCY"
    SOURCE_MISSING = "SOURCE_MISSING"


class ValuationAttractiveness(str, Enum):
    ATTRACTIVE = "ATTRACTIVE"
    NEAR_ENTRY = "NEAR_ENTRY"
    WAIT = "WAIT"
    EXPENSIVE = "EXPENSIVE"
    INDETERMINATE = "INDETERMINATE"


class ValuationInputStatus(BaseModel):
    name: str
    value: float | None = None
    cell: str | None = None
    status: ValuationDecision
    reason: str = ""
    source: str | None = None


class ValuationValidationReport(BaseModel):
    """Machine-readable artifact: valuation_validation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "valuation_margin_of_safety_entry_price_review"
    workbook_path: str | None = None

    methodology: dict[str, Any] = Field(default_factory=dict)
    inputs: list[ValuationInputStatus] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)

    workbook_intrinsic_value: float | None = None
    independent_intrinsic_value: float | None = None
    intrinsic_difference: float | None = None
    intrinsic_decision: ValuationDecision = ValuationDecision.REVIEW_REQUIRED

    current_price: float | None = None
    current_price_source: str | None = None
    current_price_decision: ValuationDecision = ValuationDecision.SOURCE_MISSING

    margin_of_safety: float | None = None
    required_mos_threshold: float = 0.25
    meets_mos_threshold: bool | None = None
    required_entry_price: float | None = None
    price_gap_to_entry: float | None = None
    pct_decline_to_entry: float | None = None

    workbook_max_price_to_buy: float | None = None
    attractiveness: ValuationAttractiveness = ValuationAttractiveness.INDETERMINATE
    sensitivity: dict[str, Any] = Field(default_factory=dict)

    decision: ValuationDecision = ValuationDecision.REVIEW_REQUIRED
    explanation: str = ""
    summary: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValuationAnalystItem(BaseModel):
    topic: str
    status: ValuationDecision
    observation: str
    quantitative_evidence: dict[str, Any] = Field(default_factory=dict)
    interpretation: str


class ValuationAnalystReview(BaseModel):
    """Machine-readable artifact: valuation_analyst_review.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "valuation_margin_of_safety_entry_price_review"
    attractiveness: ValuationAttractiveness = ValuationAttractiveness.INDETERMINATE
    items: list[ValuationAnalystItem] = Field(default_factory=list)
    summary: str = ""
