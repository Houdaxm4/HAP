"""Completion-phase decision models (fill only what is genuinely missing)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CompletionDecision(str, Enum):
    FILL = "FILL"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    MISSING_SOURCE = "MISSING_SOURCE"
    BLOCKED = "BLOCKED"
    SEC_QUARTERLY_FALLBACK_REQUIRED = "SEC_QUARTERLY_FALLBACK_REQUIRED"
    YAHOO_QUARTERLY_FALLBACK_REQUIRED = "YAHOO_QUARTERLY_FALLBACK_REQUIRED"


class CompletionEntry(BaseModel):
    """One completion decision for a mapped Industrial Template cell."""

    intent_id: str
    mapping_id: str
    sheet: str
    cell: str
    cell_ref: str
    metric: str
    period: str
    analysis_type: str | None = None
    workbook_section: str | None = None
    required_for_mode: bool = False
    source_authority: str | None = None
    decision: CompletionDecision
    reason: str
    workbook_value: Any | None = None
    proposed_value: Any | None = None
    source: str | None = None


class CompletionReport(BaseModel):
    """Machine-readable completion artifact (`completion_report.json`)."""

    analysis_id: str
    ticker: str
    analysis_type: str
    normalized_analysis_type: str | None = None
    target_fiscal_year: str | None = None
    schema_version: str = "1.1.0"
    milestone: str = "analysis_type_scoped_completion"
    entries: list[CompletionEntry] = Field(default_factory=list)
    fill_count: int = 0
    already_present_count: int = 0
    out_of_scope_count: int = 0
    missing_source_count: int = 0
    blocked_count: int = 0
    sec_quarterly_fallback_count: int = 0
    sections_in_scope: list[str] = Field(default_factory=list)
    sections_out_of_scope: list[str] = Field(default_factory=list)
    sec_quarterly_fallback_required: bool = False
    quarterly_health: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
