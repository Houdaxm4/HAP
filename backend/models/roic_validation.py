"""ROIC / NOPAT / Invested Capital validation models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RoicDecision(str, Enum):
    VALIDATED = "VALIDATED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DISCREPANCY = "DISCREPANCY"
    WATCH = "WATCH"
    MATERIAL_REVIEW = "MATERIAL_REVIEW"
    SOURCE_MISSING = "SOURCE_MISSING"


class ClassificationJudgment(BaseModel):
    workbook_line: str
    sheet: str
    row: int | None = None
    value: float | None = None
    period: str
    classification: str  # operating_asset | operating_liability | non_operating | financing | ambiguous
    reason: str
    confidence: float
    evidence: str
    status: RoicDecision = RoicDecision.VALIDATED


class RoicPeriodResult(BaseModel):
    period: str
    column: str

    operating_assets: float | None = None
    operating_liabilities: float | None = None
    capitalized_leases: float | None = None
    capitalized_rd: float | None = None
    invested_capital_workbook: float | None = None
    invested_capital_independent: float | None = None
    invested_capital_difference: float | None = None

    revenue: float | None = None
    operating_expenses: float | None = None
    operating_income: float | None = None
    lease_expense: float | None = None
    lease_depreciation: float | None = None
    rd_expense: float | None = None
    rd_amortization: float | None = None
    operating_taxes_workbook: float | None = None
    tax_rate_workbook: float | None = None
    tax_rate_economic: float | None = None
    nopat_workbook: float | None = None
    nopat_independent_house: float | None = None
    nopat_independent_economic: float | None = None
    nopat_difference_house: float | None = None
    nopat_decision: RoicDecision = RoicDecision.REVIEW_REQUIRED

    roic_workbook: float | None = None
    roic_independent: float | None = None
    roic_difference: float | None = None
    roic_decision: RoicDecision = RoicDecision.REVIEW_REQUIRED

    wacc: float | None = None
    wacc_status: RoicDecision = RoicDecision.VALIDATED
    roic_minus_wacc: float | None = None
    spread_interpretation: str | None = None

    decision: RoicDecision = RoicDecision.REVIEW_REQUIRED
    explanation: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class RoicValidationReport(BaseModel):
    """Machine-readable artifact: roic_validation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "roic_nopat_invested_capital_review"
    workbook_path: str | None = None

    methodology: dict[str, Any] = Field(default_factory=dict)
    periods: list[RoicPeriodResult] = Field(default_factory=list)
    classifications: list[ClassificationJudgment] = Field(default_factory=list)

    validated_count: int = 0
    review_required_count: int = 0
    discrepancy_count: int = 0
    watch_count: int = 0
    material_review_count: int = 0

    historical_spread_interpretation: str = ""
    summary: str = ""
    overall_decision: RoicDecision = RoicDecision.REVIEW_REQUIRED


class RoicAnalystItem(BaseModel):
    period: str | None = None
    topic: str
    status: RoicDecision
    observation: str
    quantitative_evidence: dict[str, Any] = Field(default_factory=dict)
    economic_interpretation: str
    recommendation: str = "analyst_review"


class RoicAnalystReview(BaseModel):
    """Machine-readable artifact: roic_analyst_review.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "roic_nopat_invested_capital_review"
    items: list[RoicAnalystItem] = Field(default_factory=list)
    material_count: int = 0
    watch_count: int = 0
    discrepancy_count: int = 0
    historical_spread_interpretation: str = ""
    summary: str = ""
