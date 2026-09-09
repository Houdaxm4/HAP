"""Annual Update artifacts — continuity, restatement, tax, judgment, Word research."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContinuityAction(str, Enum):
    MATCH_ALREADY = "MATCH_ALREADY"
    CARRY_FORWARD_VALUE = "CARRY_FORWARD_VALUE"
    CARRY_FORWARD_FORMAT = "CARRY_FORWARD_FORMAT"
    RESTORE_FORMULA = "RESTORE_FORMULA"
    KEEP_NEW_FORMULA = "KEEP_NEW_FORMULA"
    EXPLICIT_RESTATEMENT_UPDATE = "EXPLICIT_RESTATEMENT_UPDATE"
    RESTATEMENT_REVIEW_REQUIRED = "RESTATEMENT_REVIEW_REQUIRED"
    NEW_FY_REFRESH = "NEW_FY_REFRESH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


# Service-facing aliases
ContinuityAction = ContinuityAction


class ContinuityEntry(BaseModel):
    sheet: str
    cell: str
    fiscal_year: str | None = None
    previous_value: Any = None
    previous_type: str = "blank"
    template_value: Any = None
    template_type: str = "blank"
    template_value: Any = None
    template_type: str = "blank"
    final_value: Any = None
    final_type: str | None = None
    action: ContinuityAction
    reason: str
    formatting_copied: bool = False


class AnnualModelContinuityReport(BaseModel):
    analysis_id: str
    ticker: str
    phase: str = "final"
    new_fiscal_year: str | None = None
    entries: list[ContinuityEntry] = Field(default_factory=list)
    action_counts: dict[str, int] = Field(default_factory=dict)
    unauthorized_historical_rewrites: int = 0
    status: str = "ok"
    summary: str = ""


class RestatementChange(BaseModel):
    sheet: str
    cell: str
    fiscal_year: str
    old_workbook_value: Any = None
    revised_reported_value: Any = None
    accounting_concept: str
    annual_report_source: str | None = None
    page_or_section: str | None = None
    reason: str
    confidence: float = 0.0
    automatic_change: bool = False
    action: ContinuityAction


class AnnualRestatementReport(BaseModel):
    analysis_id: str
    ticker: str
    automatic_changes: list[RestatementChange] = Field(default_factory=list)
    review_required: list[RestatementChange] = Field(default_factory=list)
    status: str = "ok"
    summary: str = ""


class StatementValidationItem(BaseModel):
    statement: str
    concept: str
    fiscal_year: str
    bloomberg_value: float | None = None
    filing_value: float | None = None
    units: str = "USD_millions"
    status: str = "VALIDATED"
    reason: str = ""


class AnnualStatementValidationReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: str | None = None
    items: list[StatementValidationItem] = Field(default_factory=list)
    bloomberg_preserved: bool = True
    discrepancies: int = 0
    summary: str = ""


class Pe10Provenance(BaseModel):
    target_cell: str
    source_workbook: str | None = None
    source_sheet: str | None = None
    source_cell: str | None = None
    source_label: str | None = None
    source_value: Any = None
    transformation: str | None = None
    field_role: str = "pe10_fiscal_year"  # pe10_fiscal_year | e10_fiscal_year | pe10_current | e10_current
    fiscal_year: str | None = None
    as_of_date: str | None = None


class AnnualInputsReport(BaseModel):
    analysis_id: str
    ticker: str
    historical_carried: int = 0
    pe10: Pe10Provenance | None = None
    e10: Pe10Provenance | None = None
    pe10_current: Pe10Provenance | None = None
    pe10_mismatch: str | None = None
    current_data_refreshed: int = 0
    summary: str = ""


class TaxComponent(BaseModel):
    house_category: str
    rate: float | None = None
    source_label: str | None = None
    residual: bool = False


class AnnualTaxReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: str | None = None
    annual_report_source: str | None = None
    reported_effective_tax_rate: float | None = None
    mapped_components: list[TaxComponent] = Field(default_factory=list)
    residual_other: float | None = None
    reconciliation_delta: float | None = None
    reconciliation_status: str = "ok"
    source_locations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""
    cells_written: list[str] = Field(default_factory=list)
    schedule_populated: bool = False
    pretax_income: float | None = None
    income_tax_expense: float | None = None
    tax_sheet_effective_rate: float | None = None
    tax_sheet_total_operating_taxes: float | None = None
    tax_sheet_verified: bool = False


class AnnualRdReport(BaseModel):
    analysis_id: str
    ticker: str
    useful_life_unchanged: bool = True
    useful_life: float | None = None
    bloomberg_rd_used: bool = True
    filled_from_filing: bool = False
    rd_expense: float | None = None
    rd_asset: float | None = None
    rd_amortization: float | None = None
    formulas_preserved: bool = True
    schedule_extended: bool = False
    lookback_years: list[str] = Field(default_factory=list)
    lookback_complete: bool = True
    cells_written: list[str] = Field(default_factory=list)
    summary: str = ""


class AnnualLeasesReport(BaseModel):
    analysis_id: str
    ticker: str
    original_rate: float | None = None
    selected_rate: float | None = None
    historical_rates: list[float] = Field(default_factory=list)
    outlier: bool = False
    extraordinary_event: bool = False
    normalized_to_prior: bool = False
    analyst_note: str | None = None
    evidence: list[str] = Field(default_factory=list)
    summary: str = ""


class AnnualRoicReport(BaseModel):
    analysis_id: str
    ticker: str
    ic_formulas_preserved: bool = True
    nopat_formulas_preserved: bool = True
    roic_formulas_preserved: bool = True
    roic_wacc_formulas_preserved: bool = True
    lease_adjustment_present: bool = False
    rd_adjustment_present: bool = False
    operating_tax_present: bool = False
    ic_formulas_preserved: bool = True
    nopat_formulas_preserved: bool = True
    roic_formulas_preserved: bool = True
    roic_wacc_formulas_preserved: bool = True
    lease_adjustment_present: bool = False
    rd_adjustment_present: bool = False
    operating_tax_present: bool = False
    summary: str = ""


class JudgmentRecord(BaseModel):
    metric: str
    original_value: Any = None
    selected_value: Any = None
    original_methodology: str | None = None
    selected_methodology: str | None = None
    reasonableness_classification: str | None = None
    historical_evidence: dict[str, Any] = Field(default_factory=dict)
    qualitative_evidence: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rationale: str = ""
    workbook_impact: str | None = None
    model_impact: str | None = None
    change_type: str | None = None  # ACCEPTED | NORMALIZED | METHODOLOGY_SWITCH
    source_references: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    adjusted: bool = False


class AnnualAnalystJudgmentReport(BaseModel):
    analysis_id: str
    ticker: str
    lease_rate: JudgmentRecord | None = None
    expected_return: JudgmentRecord | None = None
    owner_earnings_growth: JudgmentRecord | None = None
    graham_eps_growth: JudgmentRecord | None = None
    summary: str = ""


class AnnualExpectedReturnReport(BaseModel):
    analysis_id: str
    ticker: str
    default_methodology: str = "BOOK_VALUE_GROWTH"
    original_growth_rate: float | None = None
    original_expected_return: float | None = None
    reasonableness: str = "reasonable"
    selected_methodology: str = "BOOK_VALUE_GROWTH"
    selected_growth_rate: float | None = None
    final_expected_return: float | None = None
    growth_3y: float | None = None
    growth_5y: float | None = None
    growth_10y: float | None = None
    alternative_windows: dict[str, float | None] = Field(default_factory=dict)
    distortions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0
    summary: str = ""


class FormulaGuardReport(BaseModel):
    analysis_id: str
    ticker: str
    ratios_formulas_preserved: bool = True
    final_metrics_formulas_preserved: bool = True
    hardcoded_outputs: int = 0
    summary: str = ""


class ResearchSource(BaseModel):
    source_kind: str | None = None
    title: str
    url: str | None = None
    snippet: str | None = None
    reliability: str = "secondary"


class ResearchQuestion(BaseModel):
    question: str
    concept: str
    sources_searched: list[str] = Field(default_factory=list)
    extracted_value: Any = None
    source_selected: str | None = None
    unsuccessful: bool = False
    confidence: float = 0.0
    rationale: str | None = None


class CompletenessItem(BaseModel):
    concept: str
    status: str  # POPULATED | MISSING_REQUIRED_INPUT | RESEARCHED | SOURCE_DATA_UNAVAILABLE
    workbook_location: str | None = None
    value: Any = None
    attempted_sources: list[str] = Field(default_factory=list)
    reason: str | None = None


class AnnualCompletenessReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: str | None = None
    items: list[CompletenessItem] = Field(default_factory=list)
    all_required_populated: bool = False
    summary: str = ""


class AnnualResearchReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    sources: list[ResearchSource] = Field(default_factory=list)
    research_questions: list[ResearchQuestion] = Field(default_factory=list)
    reported_facts: list[str] = Field(default_factory=list)
    management_explanations: list[str] = Field(default_factory=list)
    hap_interpretations: list[str] = Field(default_factory=list)
    source_conflicts: list[str] = Field(default_factory=list)
    unsuccessful_searches: list[str] = Field(default_factory=list)
    earnings_call_status: str = "EARNINGS_CALL_SOURCE_UNAVAILABLE"
    official_release_used: bool = False
    ir_page_url: str | None = None
    earnings_call_url: str | None = None
    summary: str = ""


class YoYMetric(BaseModel):
    metric: str
    current: float | None = None
    prior: float | None = None
    pct_change: float | None = None
    units: str | None = None


class AnnualValuationOutputs(BaseModel):
    """Semantic extraction from Expected Returns / Enterprise Value / Inputs."""

    current_price: float | None = None
    current_pe10: float | None = None
    current_pe10_as_of: str | None = None
    pe10_fiscal_year: float | None = None
    pe10_fiscal_year_label: str | None = None
    pe10_fiscal_as_of: str | None = None
    max_pe10: float | None = None
    # Workbook Expected Returns sheet (NOT Inputs!B69)
    expected_annual_return: float | None = None  # E14
    expected_return_with_dividends: float | None = None  # F14
    # Bloomberg CRF proprietary alternate — distinct metric
    bloomberg_expected_return_at_current_price: float | None = None  # Inputs!B69
    bloomberg_expected_return_with_dividends_at_current_price: float | None = None  # B70
    company_value_per_share: float | None = None
    price_at_mos: float | None = None
    enterprise_mos: float | None = None
    max_buy: float | None = None
    owner_earnings_growth: float | None = None
    owner_earnings_growth_annualized: float | None = None
    # Graham family — keep concepts separate
    current_graham_intrinsic_value: float | None = None
    graham_margin_of_safety_entry_price: float | None = None
    graham_target_return_entry_price: float | None = None
    graham_expected_annualized_return: float | None = None
    graham_target_annualized_return: float | None = None
    graham_projection_horizon_years: int | None = 7
    nopat: float | None = None
    invested_capital: float | None = None
    roic: float | None = None
    roic_wacc: float | None = None
    roce: float | None = None
    sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    recalculation_complete: bool = False
    # Legacy aliases for older callers
    graham_intrinsic: float | None = None
    graham_entry: float | None = None
    graham_expected_return: float | None = None


class AnnualOutputGateReport(BaseModel):
    analysis_id: str
    ticker: str
    status: str = "ok"  # ok | NEEDS_REVIEW | BLOCKED
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gates: dict[str, str] = Field(default_factory=dict)
    summary: str = ""


class AnnualPerformanceReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    year_highlights: list[str] = Field(default_factory=list)
    yoy: list[YoYMetric] = Field(default_factory=list)
    debt_to_assets: float | None = None
    interest_coverage: float | None = None
    roic_wacc_current: float | None = None
    roic_wacc_prior: float | None = None
    roic_wacc_10y: float | None = None
    roce_current: float | None = None
    roce_prior: float | None = None
    roce_10y: float | None = None
    current_price: float | None = None
    current_pe10: float | None = None
    current_max_buy: float | None = None
    current_margin_of_safety: float | None = None
    current_expected_return: float | None = None
    current_expected_return_with_div: float | None = None
    current_graham_entry: float | None = None
    graham_intrinsic: float | None = None
    company_value_per_share: float | None = None
    owner_earnings_growth: float | None = None
    investment_conclusion: str | None = None
    company_quality: str | None = None
    valuation_attractiveness: str | None = None
    confidence: float | None = None
    open_issues: list[str] = Field(default_factory=list)
    valuation: AnnualValuationOutputs | None = None
    management_commentary: list[str] = Field(default_factory=list)
    material_risks: list[str] = Field(default_factory=list)
    summary: str = ""


class AnnualDeliverablesReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    excel_filename: str | None = None
    excel_path: str | None = None
    word_filename: str | None = None
    word_path: str | None = None
    summary: str = ""


class StageTiming(BaseModel):
    stage: str
    elapsed_ms: float
    executed: bool = True
    skipped_reason: str | None = None


class AnnualPerformanceTimingReport(BaseModel):
    analysis_id: str
    ticker: str
    total_elapsed_ms: float = 0.0
    stages: list[StageTiming] = Field(default_factory=list)
    summary: str = ""


class AnnualWorkbookLineageReport(BaseModel):
    analysis_id: str
    ticker: str
    declared_base: str = "CURRENT_TEMPLATE"
    current_template_filename: str
    current_template_sha256: str
    previous_completed_filename: str
    previous_completed_sha256: str
    working_workbook_initial_sha256: str
    final_workbook_sha256: str
    template_years: list[str] = Field(default_factory=list)
    previous_years: list[str] = Field(default_factory=list)
    overlap_years: list[str] = Field(default_factory=list)
    dropped_years: list[str] = Field(default_factory=list)
    new_fiscal_year: str | None = None
    template_end_year: str | None = None
    previous_end_year: str | None = None
    continuity_summary: str = ""
    summary: str = ""


class AnnualBaseWorkbookGuardReport(BaseModel):
    analysis_id: str
    ticker: str
    status: str = "ok"
    template_sha256: str
    previous_sha256: str
    final_sha256: str
    new_fiscal_year: str | None = None
    template_new_year_revenue: Any = None
    previous_new_year_revenue: Any = None
    final_new_year_revenue: Any = None
    violations: list[str] = Field(default_factory=list)
    summary: str = ""


# Service-facing aliases (do not change persisted JSON tokens).
ContinuityAction = ContinuityAction
ResearchSource = ResearchSource
JudgmentRecord = JudgmentRecord
TaxComponent = TaxComponent
