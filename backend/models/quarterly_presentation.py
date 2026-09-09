"""Quarterly Bloomberg vs SEC 10-Q presentation authority models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PresentationDecision(str, Enum):
    BLOOMBERG_PRESERVE = "BLOOMBERG_PRESERVE"
    BLOOMBERG_FILL_GAPS = "BLOOMBERG_FILL_GAPS"
    YAHOO_BASIC_TEMPLATE_REQUIRED = "YAHOO_BASIC_TEMPLATE_REQUIRED"
    SEC_10Q_PRESENTATION_REQUIRED = "SEC_10Q_PRESENTATION_REQUIRED"  # secondary fallback
    BLOCKED = "BLOCKED"


class QuarterlyStatementKind(str, Enum):
    INCOME = "quarterly_income_statement"
    BALANCE_SHEET = "quarterly_balance_sheet"
    CASH_FLOW = "quarterly_cash_flow"


STATEMENT_SHEETS: dict[QuarterlyStatementKind, str] = {
    QuarterlyStatementKind.INCOME: "Last Quarter IS Standardized",
    QuarterlyStatementKind.BALANCE_SHEET: "Last Quarter BS Standardized",
    QuarterlyStatementKind.CASH_FLOW: "Last Quarter CF Standardized",
}


class BloombergHealthAssessment(BaseModel):
    statement: QuarterlyStatementKind
    sheet: str
    present: bool = True
    expected_mapped_rows: int = 0
    populated_rows: int = 0
    missing_required_rows: int = 0
    missing_ratio: float = 0.0
    major_totals_present: bool = False
    major_totals_missing: list[str] = Field(default_factory=list)
    structural_failure: bool = False
    isolated_gaps: bool = False
    coherence_notes: list[str] = Field(default_factory=list)
    reason: str = ""


class SecLineItem(BaseModel):
    """One SEC-presented line for quarterly reconstruction."""

    statement: str
    label: str
    xbrl_concept: str | None = None
    value: float | None = None
    period_start: str | None = None
    period_end: str | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filing_date: str | None = None
    accession_number: str | None = None
    source_url: str | None = None
    duration_kind: str = "unknown"  # standalone_quarter | ytd | instant | unknown
    unit: str = "USD"


class QuarterlyStatementPresentation(BaseModel):
    statement: QuarterlyStatementKind
    sheet: str
    health: BloombergHealthAssessment
    decision: PresentationDecision
    reason: str
    bloomberg_populated: int = 0
    bloomberg_missing: int = 0
    sec_filing_form: str | None = None
    sec_filing_period: str | None = None
    sec_accession: str | None = None
    rows_preserved: list[str] = Field(default_factory=list)
    rows_filled: list[str] = Field(default_factory=list)
    rows_superseded: list[str] = Field(default_factory=list)
    sec_rows_introduced: list[str] = Field(default_factory=list)
    blocked_or_ambiguous: list[str] = Field(default_factory=list)
    sec_line_items: list[SecLineItem] = Field(default_factory=list)
    yahoo_rows_introduced: list[str] = Field(default_factory=list)
    ytd_provenance: dict[str, Any] = Field(default_factory=dict)
    data_source_primary: str | None = None  # bloomberg | yahoo | sec
    data_source_secondary: str | None = None


class QuarterlyPresentationReport(BaseModel):
    """Machine-readable artifact: quarterly_presentation_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "quarterly_sec_10q_presentation_authority"
    statements: list[QuarterlyStatementPresentation] = Field(default_factory=list)
    summary: str = ""
