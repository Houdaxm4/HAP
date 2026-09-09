"""New Company initiation artifacts — ten-year coverage, gates, and analyst review."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NewCompanyWorkflowState(str, Enum):
    PROCESSING = "PROCESSING"
    AWAITING_ANALYST_REVIEW = "AWAITING_ANALYST_REVIEW"
    RECALCULATING = "RECALCULATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class CoverageStatus(str, Enum):
    COVERED_ORIGINAL = "covered_original"
    COVERED_RESTATED = "covered_restated"
    COVERED_COMPARATIVE = "covered_comparative"
    PARTIAL = "partial"
    MISSING = "missing"
    TRANSITION = "transition"
    AMENDED = "amended"


class BuybackAbsenceClass(str, Enum):
    REPORTED_ZERO = "reported_zero"
    NOT_DISCLOSED = "not_disclosed"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"


class ProjectionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRELIABLE = "unreliable"
    NOT_APPLICABLE = "not_applicable"


class TenYearPeriodReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_years: list[str] = Field(default_factory=list)
    year_columns: dict[str, int] = Field(default_factory=dict)
    start_year: str | None = None
    end_year: str | None = None
    latest_quarter: int | None = None
    latest_quarter_label: str | None = None
    latest_quarter_fiscal_year: str | None = None
    chronology_ok: bool = True
    duplicate_columns: list[str] = Field(default_factory=list)
    template_family: str | None = None
    template_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    status: str = "ok"
    summary: str = ""


class FilingYearCoverage(BaseModel):
    fiscal_year: str
    filing_used: str | None = None
    accession_number: str | None = None
    filing_url: str | None = None
    period_end: str | None = None
    form_type: str | None = None
    originally_reported_or_revised: str = "unknown"
    source_table_or_note: str | None = None
    coverage_status: CoverageStatus = CoverageStatus.MISSING
    restated: bool = False
    transition_report: bool = False
    amended: bool = False
    notes: list[str] = Field(default_factory=list)


class TenYearSourceCoverageReport(BaseModel):
    analysis_id: str
    ticker: str
    required_years: list[str] = Field(default_factory=list)
    displayed_years: list[str] = Field(default_factory=list)
    lookback_years: list[str] = Field(default_factory=list)
    filings_selected: list[dict[str, Any]] = Field(default_factory=list)
    years: list[FilingYearCoverage] = Field(default_factory=list)
    overlapping_years_deduped: list[str] = Field(default_factory=list)
    pattern: str | None = None
    complete: bool = False  # displayed ten-year window
    lookback_complete: bool = True
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class StatementDiscrepancy(BaseModel):
    fiscal_year: str
    statement: str
    concept: str
    sheet: str | None = None
    cell: str | None = None
    old_value: Any = None
    new_value: Any = None
    source: str | None = None
    reason: str = ""
    impact: str = ""
    action: str = "preserve"
    material: bool = False


class NewCompanyStatementValidationReport(BaseModel):
    analysis_id: str
    ticker: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    discrepancies: list[StatementDiscrepancy] = Field(default_factory=list)
    filled_missing: list[StatementDiscrepancy] = Field(default_factory=list)
    corrections: list[StatementDiscrepancy] = Field(default_factory=list)
    unresolved_material: list[str] = Field(default_factory=list)
    formulas_preserved: bool = True
    status: str = "ok"
    summary: str = ""


class Pe10Observation(BaseModel):
    fiscal_year: str | None = None
    field_role: str
    value: float | None = None
    stock_price: float | None = None
    as_of_date: str | None = None
    observation_date: str | None = None
    date_difference_days: int | None = None
    nearest_date_rule: str | None = None
    source_label: str | None = None
    target_cell: str | None = None
    warning: str | None = None
    missing: bool = False


class NewCompanyPe10Report(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year_pe10: list[Pe10Observation] = Field(default_factory=list)
    fiscal_year_e10: list[Pe10Observation] = Field(default_factory=list)
    current_pe10: Pe10Observation | None = None
    current_e10: Pe10Observation | None = None
    current_stock_price: Pe10Observation | None = None
    chronology_ok: bool = True
    duplicate_periods: list[str] = Field(default_factory=list)
    zero_as_missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    status: str = "ok"
    summary: str = ""


class TaxYearResult(BaseModel):
    fiscal_year: str
    reported_effective_rate: float | None = None
    computed_effective_rate: float | None = None
    statutory_federal: float | None = None
    state: float | None = None
    foreign: float | None = None
    rd_credit: float | None = None
    other: float | None = None
    residual_other: float | None = None
    component_sum: float | None = None
    reconciliation_delta: float | None = None
    reconciliation_status: str = "ok"
    pretax_income: float | None = None
    income_tax_expense: float | None = None
    units: str = "rate_fraction"
    signs_normalized: bool = True
    cells_written: list[str] = Field(default_factory=list)
    schedule_populated: bool = False
    raw_filing_lines: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None
    source_locations: list[str] = Field(default_factory=list)


class NewCompanyTaxReport(BaseModel):
    analysis_id: str
    ticker: str
    years: list[TaxYearResult] = Field(default_factory=list)
    complete: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class RdUsefulLifeDecision(BaseModel):
    analysis_id: str
    ticker: str
    selected_useful_life: int | None = None
    permitted_range: tuple[int, int] = (1, 10)
    company_evidence: list[str] = Field(default_factory=list)
    industry_evidence: list[str] = Field(default_factory=list)
    comparable_evidence: list[str] = Field(default_factory=list)
    alternatives_considered: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    filing_citations: list[str] = Field(default_factory=list)
    decision_timestamp: str | None = None
    model_version: str = "new_company_rd_useful_life_v1"
    provenance_class: str = "agent_selected_analyst_assumption"
    analyst_override: int | None = None
    analyst_override_reason: str | None = None
    original_agent_selection: int | None = None
    warning: str = (
        "R&D useful life is an agent-selected analyst assumption and has not been "
        "manually approved. Override it if the economic life of the company's R&D "
        "differs from this selection."
    )
    blocking: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    industry: str | None = None
    sic: str | None = None


class RdYearAmount(BaseModel):
    fiscal_year: str
    amount: float | None = None
    units: str = "USD_millions"
    source: str | None = None
    zero_vs_unavailable: str | None = None
    lookback: bool = False
    displayed: bool = True


class NewCompanyRdReport(BaseModel):
    analysis_id: str
    ticker: str
    useful_life: int | None = None
    first_displayed_year: str | None = None
    earliest_required_year: str | None = None
    lookback_years: list[str] = Field(default_factory=list)
    expenses: list[RdYearAmount] = Field(default_factory=list)
    lookback_complete: bool = False
    capitalization_ok: bool = False
    schedule_extended: bool = False
    cells_written: list[str] = Field(default_factory=list)
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    latest_asset: float | None = None
    latest_amortization: float | None = None
    formulas_preserved: bool = True
    warning_visible: bool = True
    summary: str = ""


class LeaseYearData(BaseModel):
    fiscal_year: str
    year_1: float | None = None
    year_2: float | None = None
    year_3: float | None = None
    year_4: float | None = None
    year_5: float | None = None
    thereafter: float | None = None
    total_undiscounted: float | None = None
    current_liability: float | None = None
    long_term_liability: float | None = None
    rou_asset: float | None = None
    lease_cost: float | None = None
    remaining_term: float | None = None
    reported_discount_rate: float | None = None
    regime: str = "unknown"  # pre_asc_842 | post_asc_842 | mixed
    raw_labels: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None


class LeaseRateProposal(BaseModel):
    proposed_rate: float | None = None
    methodology: str | None = None
    methodology_rank: int | None = None
    market_date: str | None = None
    estimated_lease_duration: float | None = None
    benchmark_rate: float | None = None
    credit_spread: float | None = None
    company_evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    hierarchy_attempts: list[dict[str, Any]] = Field(default_factory=list)


class LeaseRateReview(BaseModel):
    analysis_id: str
    ticker: str
    status: str = "LEASE_RATE_REVIEW_PENDING"
    proposed_rate: float | None = None
    approved_rate: float | None = None
    analyst_action: str | None = None  # approve | correct | request_more_evidence
    analyst_reason: str | None = None
    supporting_evidence: list[str] = Field(default_factory=list)
    prior_or_comparable_rates: list[float] = Field(default_factory=list)
    calculated_lease_asset: float | None = None
    calculated_lease_liability: float | None = None
    sensitivity: list[dict[str, Any]] = Field(default_factory=list)
    proposal: LeaseRateProposal | None = None
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    blocking: bool = True
    summary: str = ""


class NewCompanyLeaseReport(BaseModel):
    analysis_id: str
    ticker: str
    years: list[LeaseYearData] = Field(default_factory=list)
    complete: bool = False
    mixed_regimes: bool = False
    warnings: list[str] = Field(default_factory=list)
    proposal: LeaseRateProposal | None = None
    review: LeaseRateReview | None = None
    cells_written: list[str] = Field(default_factory=list)
    summary: str = ""


class BuybackYearResult(BaseModel):
    fiscal_year: str
    dollars: float | None = None
    shares: float | None = None
    average_price: float | None = None
    dollars_source: str | None = None
    shares_source: str | None = None
    shares_derived: bool = False
    derivation_formula: str | None = None
    dollars_definition: str | None = None
    exclusions: list[str] = Field(default_factory=list)
    beginning_shares: float | None = None
    issued_shares: float | None = None
    ending_shares: float | None = None
    other_share_changes: float | None = None
    absence_class: BuybackAbsenceClass | None = None
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class BuybackAnalysis(BaseModel):
    cumulative_dollars: float | None = None
    cumulative_shares: float | None = None
    diluted_share_count_change: float | None = None
    sbc_offset_material: bool | None = None
    funded_by: str | None = None
    value_created_or_destroyed: str | None = None
    notes: list[str] = Field(default_factory=list)


class NewCompanyBuybackReport(BaseModel):
    analysis_id: str
    ticker: str
    years: list[BuybackYearResult] = Field(default_factory=list)
    analysis: BuybackAnalysis | None = None
    complete: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class CurrentDataAsOf(BaseModel):
    field: str
    value: Any = None
    as_of_date: str | None = None
    source: str | None = None
    cell: str | None = None


class NewCompanyCurrentDataReport(BaseModel):
    analysis_id: str
    ticker: str
    fields: list[CurrentDataAsOf] = Field(default_factory=list)
    as_of_mismatch: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class SeasonalityComponent(BaseModel):
    metric: str
    ytd_value: float | None = None
    historical_ytd: dict[str, float] = Field(default_factory=dict)
    historical_full_year: dict[str, float] = Field(default_factory=dict)
    proportions: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    selected_factor: float | None = None
    unadjusted_annualized: float | None = None
    seasonality_adjusted: float | None = None
    exclusions: list[str] = Field(default_factory=list)
    unreliable: bool = False
    reason: str | None = None


class SeasonalityProjectionReport(BaseModel):
    analysis_id: str
    ticker: str
    latest_quarter: int | None = None
    ytd_period_length: str | None = None
    historical_comparison_years: list[str] = Field(default_factory=list)
    components: list[SeasonalityComponent] = Field(default_factory=list)
    confidence: ProjectionConfidence = ProjectionConfidence.LOW
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class ProjectionBacktestYear(BaseModel):
    fiscal_year: str
    quarter: int
    projected_roic: float | None = None
    actual_roic: float | None = None
    projected_roce: float | None = None
    actual_roce: float | None = None
    abs_error_roic: float | None = None
    pct_error_roic: float | None = None
    abs_error_roce: float | None = None
    pct_error_roce: float | None = None


class NewCompanyProjectionReport(BaseModel):
    analysis_id: str
    ticker: str
    latest_quarter: int | None = None
    latest_annual_roic: float | None = None
    ytd_unadjusted_annualized_roic: float | None = None
    seasonality_adjusted_roic: float | None = None
    wacc: float | None = None
    projected_roic_wacc: float | None = None
    latest_annual_roce: float | None = None
    ten_year_avg_roic: float | None = None
    ten_year_avg_roce: float | None = None
    ytd_unadjusted_annualized_roce: float | None = None
    seasonality_adjusted_roce: float | None = None
    confidence: ProjectionConfidence = ProjectionConfidence.NOT_APPLICABLE
    assumptions: list[str] = Field(default_factory=list)
    backtests: list[ProjectionBacktestYear] = Field(default_factory=list)
    status: str = "ok"
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class NewCompanyOutputGateReport(BaseModel):
    analysis_id: str
    ticker: str
    status: str = "NEEDS_REVIEW"
    gates: dict[str, str] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    report_authorized: bool = False
    summary: str = ""


class NewCompanyDeliverablesReport(BaseModel):
    analysis_id: str
    ticker: str
    fiscal_year: int | None = None
    excel_filename: str | None = None
    excel_path: str | None = None
    word_filename: str | None = None
    word_path: str | None = None
    authorized: bool = False
    summary: str = ""


class LeaseRateReviewRequest(BaseModel):
    action: str  # approve | correct | request_more_evidence
    rate: float | None = None
    reason: str | None = None


class RdUsefulLifeOverrideRequest(BaseModel):
    useful_life: int
    reason: str | None = None


class NewCompanyRunState(BaseModel):
    analysis_id: str
    ticker: str
    workflow_state: NewCompanyWorkflowState = NewCompanyWorkflowState.PROCESSING
    fiscal_years: list[str] = Field(default_factory=list)
    latest_quarter: int | None = None
    workbook_path: str | None = None
    custom_run_path: str | None = None
    lease_rate_approved: bool = False
    rd_life_overridden: bool = False
    phases_completed: list[str] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    summary: str = ""
