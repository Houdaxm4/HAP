"""Quarterly carry-forward / restatement / performance models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CarryForwardDecision(str, Enum):
    CARRY_FORWARD = "CARRY_FORWARD"
    CARRY_FORWARD_FORMAT = "CARRY_FORWARD_FORMAT"
    KEEP_NEW_FORMULA = "KEEP_NEW_FORMULA"
    RESTORE_FORMULA = "RESTORE_FORMULA"
    MATCH_ALREADY = "MATCH_ALREADY"
    REFRESH_CURRENT_DATA = "REFRESH_CURRENT_DATA"
    IGNORE_TEMPLATE_PRESERVE = "IGNORE_TEMPLATE_PRESERVE"
    LEAVE_AS_IS = "LEAVE_AS_IS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    MISSING_PREVIOUS_WORKBOOK = "MISSING_PREVIOUS_WORKBOOK"


class CarryForwardEntry(BaseModel):
    sheet: str
    cell: str
    previous_value: Any = None
    previous_type: str  # formula | value | blank
    new_template_value: Any = None
    new_template_type: str
    final_value: Any = None
    final_type: str | None = None
    final_action: CarryForwardDecision
    reason: str
    source_workbook: str


class QuarterlyCarryForwardReport(BaseModel):
    """Artifact: quarterly_carry_forward_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "simplified_quarterly_update"
    previous_workbook: str | None = None
    new_template: str | None = None
    entries: list[CarryForwardEntry] = Field(default_factory=list)
    carry_forward_count: int = 0
    keep_formula_count: int = 0
    refresh_current_count: int = 0
    summary: str = ""
    status: str = "ok"  # ok | MISSING_PREVIOUS_WORKBOOK


class RestatementFinding(BaseModel):
    statement: str
    metric: str
    period: str
    previous_value: float | None = None
    sec_value: float | None = None
    absolute_difference: float | None = None
    percentage_difference: float | None = None
    decision: str = "RESTATEMENT_REVIEW_REQUIRED"
    reason: str = ""


class RestatementCheckReport(BaseModel):
    """Artifact: restatement_check_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    material_restatement_detected: bool = False
    findings: list[RestatementFinding] = Field(default_factory=list)
    annual_validation_triggered: bool = False
    summary: str = ""


class QuarterlyComparisonEntry(BaseModel):
    statement: str
    metric: str
    baseline_period: str
    compare_period: str
    baseline_value: float | None = None
    compare_value: float | None = None
    absolute_change: float | None = None
    percentage_change: float | None = None
    comparison_type: str  # qoq | yoy_quarter | ytd
    note: str = ""


class QuarterlyReviewReport(BaseModel):
    """Artifact: quarterly_analyst_review.json (quarter-scoped)"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "simplified_quarterly_update"
    comparisons: list[QuarterlyComparisonEntry] = Field(default_factory=list)
    material_changes: list[str] = Field(default_factory=list)
    summary: str = ""


class StageTiming(BaseModel):
    stage: str
    elapsed_ms: float
    executed: bool = True
    skipped_reason: str | None = None


class CurrentDataRefreshEntry(BaseModel):
    """Provenance for one Inputs current-data cell (B63:B75)."""

    target_sheet: str = "Inputs"
    target_cell: str
    target_label: str | None = None
    source_kind: str  # yahoo_live | crf_label | skipped
    source_crf_sheet: str | None = None
    source_crf_cell: str | None = None
    source_crf_label: str | None = None
    source_value: Any = None
    written_value: Any = None
    transformation: str | None = None
    reason: str = ""


class CurrentDataRefreshReport(BaseModel):
    """Artifact: current_data_refresh_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    entries: list[CurrentDataRefreshEntry] = Field(default_factory=list)
    populated_count: int = 0
    missing_required: list[str] = Field(default_factory=list)
    summary: str = ""


class QuarterlyMarginEntry(BaseModel):
    metric: str  # gross_margin | operating_margin | net_margin
    period_kind: str  # yoy_quarter | ytd
    revenue: float | None = None
    numerator: float | None = None
    margin: float | None = None
    cell: str | None = None
    formula: str | None = None


class QuarterlyMarginReport(BaseModel):
    """Artifact: quarterly_margin_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    entries: list[QuarterlyMarginEntry] = Field(default_factory=list)
    summary: str = ""


class QuarterlyProjectionReport(BaseModel):
    """Artifact: quarterly_projection_report.json (Q2/Q3 only)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    status: str = "ok"  # ok | NOT_APPLICABLE | REVIEW_REQUIRED | BLOCKED
    fiscal_quarter: int | None = None
    fiscal_year: int | None = None
    next_fiscal_year: int | None = None
    latest_bs_date: str | None = None
    annualization_factor: float | None = None
    operating_assets: float | None = None
    operating_liabilities: float | None = None
    ytd_revenue: float | None = None
    ytd_operating_income: float | None = None
    projected_revenue: float | None = None
    projected_operating_income: float | None = None
    prior_fy_operating_income: float | None = None
    prior_fy_operating_taxes: float | None = None
    projected_operating_taxes: float | None = None
    lease_expense: float | None = None
    lease_depreciation: float | None = None
    rd_expense: float | None = None
    rd_depreciation: float | None = None
    capitalized_leases: float | None = None
    capitalized_rd: float | None = None
    projected_nopat: float | None = None
    projected_invested_capital: float | None = None
    projected_roic: float | None = None
    prior_fy_wacc: float | None = None
    projected_roic_wacc: float | None = None
    ytd_cfo: float | None = None
    projected_cfo: float | None = None
    total_assets: float | None = None
    projected_roce: float | None = None
    prior_fy_roic: float | None = None
    prior_fy_roce: float | None = None
    source_cells: dict[str, str] = Field(default_factory=dict)
    formulas_written: dict[str, str] = Field(default_factory=dict)
    summary: str = ""


class QuarterlyDeliverablesReport(BaseModel):
    """Primary Excel FA + Word quarterly update deliverables."""

    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    excel_filename: str | None = None
    excel_path: str | None = None
    word_filename: str | None = None
    word_path: str | None = None
    summary: str = ""


class ModelContinuityEntry(BaseModel):
    """One meaningful persistent-cell reconciliation decision."""

    sheet: str
    cell: str
    previous_value: Any = None
    previous_type: str = ""
    current_template_value: Any = None
    current_template_type: str = ""
    final_value: Any = None
    final_type: str = ""
    previous_formula: str | None = None
    current_formula: str | None = None
    formatting_changed: bool = False
    final_action: CarryForwardDecision
    reason: str = ""


class QuarterlyModelContinuityReport(BaseModel):
    """Artifact: quarterly_model_continuity_report.json (final deliverable state)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    phase: str = "final"  # apply | final
    entries: list[ModelContinuityEntry] = Field(default_factory=list)
    ignored_sheets_verified: list[str] = Field(default_factory=list)
    ignored_sheet_mismatches: list[str] = Field(default_factory=list)
    summary: str = ""
    status: str = "ok"


class QuarterlyModelContinuityApplyReport(BaseModel):
    """Intermediate persistent-tab reconciliation during carry-forward (pre-fill)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    entries: list[ModelContinuityEntry] = Field(default_factory=list)
    carry_forward_count: int = 0
    restore_formula_count: int = 0
    format_count: int = 0
    summary: str = ""


class ResearchSourceEntry(BaseModel):
    source_kind: str  # sec_8k | sec_10q | yahoo_news | earnings_call | ir_release
    title: str = ""
    url: str | None = None
    snippet: str = ""
    reliability: str = "official"  # official | secondary | unavailable


class QuarterlyResearchReport(BaseModel):
    """External research gathered for Word Financial Highlights."""

    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    sources: list[ResearchSourceEntry] = Field(default_factory=list)
    reported_facts: list[str] = Field(default_factory=list)
    management_explanations: list[str] = Field(default_factory=list)
    hap_interpretations: list[str] = Field(default_factory=list)
    earnings_call_status: str = "EARNINGS_CALL_SOURCE_UNAVAILABLE"
    official_release_used: bool = False
    ir_page_url: str | None = None
    earnings_call_url: str | None = None
    summary: str = ""


class QuarterlyPerformanceReport(BaseModel):
    """Artifact: quarterly_performance_report.json"""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    total_elapsed_ms: float = 0.0
    stages: list[StageTiming] = Field(default_factory=list)
    annual_only_stages_skipped: list[str] = Field(default_factory=list)
    summary: str = ""
