"""Expected Return / EPS growth validation models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExpectedReturnDecision(str, Enum):
    VALIDATED = "VALIDATED"
    WATCH = "WATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DISCREPANCY = "DISCREPANCY"
    SOURCE_MISSING = "SOURCE_MISSING"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class AdjustmentNecessity(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    NOT_JUSTIFIED = "NOT_JUSTIFIED"


class EpsHistoryPoint(BaseModel):
    period: str
    workbook_eps: float | None = None
    sec_eps: float | None = None
    workbook_cell: str | None = None
    decision: ExpectedReturnDecision = ExpectedReturnDecision.REVIEW_REQUIRED
    reason: str = ""
    yoy_growth: float | None = None
    split_adjusted_comparable: bool = True


class EpsOutlierJudgment(BaseModel):
    period: str
    reported_eps: float | None = None
    proposed_normalized_eps: float | None = None
    yoy_growth: float | None = None
    quantitative_impact: dict[str, Any] = Field(default_factory=dict)
    reason: str
    sec_evidence: str | None = None
    confidence: float
    necessity: AdjustmentNecessity
    decision: ExpectedReturnDecision = ExpectedReturnDecision.WATCH


class ExpectedReturnPeriodAssumptions(BaseModel):
    workbook_eps_cagr: float | None = None
    independent_eps_cagr: float | None = None
    recent_5y_cagr: float | None = None
    workbook_growth_assumption: float | None = None
    independent_growth_low: float | None = None
    independent_growth_high: float | None = None
    growth_decision: ExpectedReturnDecision = ExpectedReturnDecision.REVIEW_REQUIRED
    growth_explanation: str = ""


class ExpectedReturnValidationReport(BaseModel):
    """Machine-readable artifact: expected_return_validation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "expected_return_review"
    workbook_path: str | None = None
    methodology: dict[str, Any] = Field(default_factory=dict)
    eps_history: list[EpsHistoryPoint] = Field(default_factory=list)
    outliers: list[EpsOutlierJudgment] = Field(default_factory=list)
    growth: ExpectedReturnPeriodAssumptions = Field(
        default_factory=ExpectedReturnPeriodAssumptions
    )
    current_price: float | None = None
    max_pe10: float | None = None
    workbook_expected_return: float | None = None
    independent_expected_return: float | None = None
    expected_return_difference: float | None = None
    expected_return_decision: ExpectedReturnDecision = ExpectedReturnDecision.REVIEW_REQUIRED
    expected_return_explanation: str = ""
    attractiveness: str | None = None
    overall_decision: ExpectedReturnDecision = ExpectedReturnDecision.REVIEW_REQUIRED
    summary: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ExpectedReturnAnalystItem(BaseModel):
    topic: str
    period: str | None = None
    status: ExpectedReturnDecision
    observation: str
    quantitative_evidence: dict[str, Any] = Field(default_factory=dict)
    interpretation: str
    recommendation: str = "analyst_review"


class ExpectedReturnAnalystReview(BaseModel):
    """Machine-readable artifact: expected_return_analyst_review.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "expected_return_review"
    items: list[ExpectedReturnAnalystItem] = Field(default_factory=list)
    attractiveness: str | None = None
    summary: str = ""
