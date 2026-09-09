"""Analyst review findings after statement validation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    MATERIAL = "MATERIAL"


class ExplanationStatus(str, Enum):
    EXPLAINED_BY_FILING = "EXPLAINED_BY_FILING"
    LIKELY_EXPLANATION = "LIKELY_EXPLANATION"
    UNEXPLAINED_REVIEW_REQUIRED = "UNEXPLAINED_REVIEW_REQUIRED"


class AnalystFinding(BaseModel):
    statement: str
    metric: str
    period: str
    severity: FindingSeverity
    observation: str
    quantitative_evidence: dict[str, Any] = Field(default_factory=dict)
    sec_explanation: str | None = None
    explanation_status: ExplanationStatus = ExplanationStatus.UNEXPLAINED_REVIEW_REQUIRED
    source_references: list[str] = Field(default_factory=list)
    analyst_relevance: str
    status: str = "open"
    is_data_discrepancy: bool = False


class AnalystReviewReport(BaseModel):
    """Machine-readable artifact: analyst_review_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "financial_statement_validation_analyst_review"
    findings: list[AnalystFinding] = Field(default_factory=list)
    material_count: int = 0
    watch_count: int = 0
    info_count: int = 0
    summary: str = ""
