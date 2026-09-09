"""Final investment recommendation artifact models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntryCondition(BaseModel):
    current_price: float | None = None
    intrinsic_value: float | None = None
    required_entry_price: float | None = None
    margin_of_safety: float | None = None
    required_mos_threshold: float = 0.25
    pct_decline_to_entry: float | None = None
    note: str = ""


class FinalRecommendationReport(BaseModel):
    """Machine-readable artifact: final_recommendation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "final_investment_recommendation"

    business_quality_score: float | None = None
    business_quality_classification: str | None = None
    investment_attractiveness_score: float | None = None
    investment_attractiveness_classification: str | None = None

    valuation_status: str | None = None
    expected_return_status: str | None = None
    roic_wacc_assessment: str | None = None

    current_price: float | None = None
    intrinsic_value: float | None = None
    margin_of_safety: float | None = None
    entry_price: float | None = None

    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    entry_condition: EntryCondition | None = None

    confidence: float = 0.0
    final_recommendation: str
    recommendation_label: str
    recommendation_rationale: str = ""
    evidence_references: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
