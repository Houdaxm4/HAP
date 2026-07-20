"""Analysis-engine result schemas conforming to FINANCIAL_ANALYSIS_SPEC.md.

Modules consume only ``CompanyFinancialModel`` and return structured
``AnalysisModuleResult`` objects — never narrative text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Spec score bands: 90–100 Exceptional … Below 40 Poor
ModuleStatus = Literal["ok", "skipped", "error"]
FindingSeverity = Literal["info", "positive", "warning", "critical", "low", "medium", "high"]
FindingDirection = Literal["positive", "negative", "neutral", "mixed"]
AdjustmentAction = Literal[
    "review_assumption",
    "override_input",
    "accept_as_is",
    "request_more_data",
    "adjust_forecast",
    "flag_for_committee",
    "capitalize_rd",
    "normalize_margins",
    "remove_one_time",
    # Growth module adjustments (docs/modules/GROWTH_MODULE_SPEC.md §9)
    "normalize_acquisition_growth",
    "separate_organic_growth",
    "remove_one_time_revenue",
    "normalize_covid_effects",
    "adjust_discontinued_operations",
    "normalize_share_count",
    "exclude_hypergrowth_base_year",
    "use_per_share_growth",
    # Enterprise Valuation adjustments (ENTERPRISE_VALUATION_MODULE_SPEC.md §10)
    "reconcile_inputs",
    "investigate_workbook_formula",
    "request_analyst_review",
]
AdjustmentPriority = Literal["low", "medium", "high"]
EvidenceKind = Literal[
    "financial_fact",
    "derived_metric",
    "period_comparison",
    "ratio",
    "missing_input",
    "rule_trigger",
]
MetricOrigin = Literal["workbook", "hap"]
ComparisonStatus = Literal[
    "match",
    "within_tolerance",
    "divergent",
    "workbook_only",
    "hap_only",
    "not_comparable",
]
ComparisonRecommendedAction = Literal[
    "no_action",
    "accept_hap_value",
    "accept_workbook_value",
    "reconcile_inputs",
    "investigate_workbook_formula",
    "request_analyst_review",
    "not_applicable",
]
ToleranceMode = Literal["absolute", "relative"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Evidence(BaseModel):
    """Evidence required for every finding (FINANCIAL_ANALYSIS_SPEC)."""

    kind: EvidenceKind
    label: str
    metric: str | None = None
    concept: str | None = None
    period: str | None = None
    value: float | None = None
    unit: str | None = None
    source: str | None = None
    cell_ref: str | None = None
    source_document: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class MetricResult(BaseModel):
    """Named quantitative output from a module (HAP Metric)."""

    name: str
    code: str
    value: float | None = None
    unit: str | None = None
    period: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None
    origin: MetricOrigin = "hap"


class HAPMetric(BaseModel):
    """A metric computed by HAP from canonical statement facts."""

    code: str
    name: str
    value: float | None = None
    unit: str | None = None
    period: str | None = None
    module_name: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    evidence: list[Evidence] = Field(default_factory=list)
    origin: MetricOrigin = "hap"


class MetricComparison(BaseModel):
    """
    Side-by-side comparison of an equivalent Workbook Metric and HAP Metric.

    Workbook Value, HAP Value, Difference, Tolerance, Status, Recommended Action.
    """

    comparison_id: str
    metric_code: str
    metric_name: str
    module_name: str
    period: str | None = None
    unit: str | None = None
    workbook_value: float | None = None
    hap_value: float | None = None
    difference: float | None = None
    relative_difference: float | None = None
    tolerance: float
    tolerance_mode: ToleranceMode = "absolute"
    status: ComparisonStatus
    recommended_action: ComparisonRecommendedAction
    workbook_metric: dict[str, Any] | None = None
    hap_metric: HAPMetric | None = None
    notes: str | None = None


class ModuleMetricComparisons(BaseModel):
    """Additive module extension stored under ``coverage[\"metric_comparisons\"]``."""

    comparisons: list[MetricComparison] = Field(default_factory=list)
    workbook_metric_count: int = 0
    hap_metric_count: int = 0
    divergent_count: int = 0


class Finding(BaseModel):
    """Structured finding produced by deterministic rules or module logic."""

    finding_id: str
    code: str
    rule_id: str | None = None
    severity: FindingSeverity
    direction: FindingDirection = "neutral"
    category: str
    summary: str
    periods: list[str] = Field(default_factory=list)
    metrics: dict[str, float | None] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_analyst_action: str | None = None

    @model_validator(mode="after")
    def _require_evidence(self) -> Finding:
        if not self.evidence:
            raise ValueError(f"Finding '{self.code}' is invalid without evidence.")
        return self


class RiskItem(BaseModel):
    """Structured risk surfaced by a module."""

    risk_id: str
    code: str
    severity: FindingSeverity
    summary: str
    related_finding_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class OpportunityItem(BaseModel):
    """Structured opportunity surfaced by a module."""

    opportunity_id: str
    code: str
    summary: str
    related_finding_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class AnalystAdjustmentProposal(BaseModel):
    """Optional analyst action candidate (never silently mutates statements)."""

    adjustment_id: str
    action: AdjustmentAction
    priority: AdjustmentPriority
    rationale_code: str
    target: str | None = None
    current_value: float | None = None
    proposed_value: float | None = None
    related_finding_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComponentScore(BaseModel):
    """One weighted component of a module score (SCORING_SYSTEM.md)."""

    code: str
    name: str
    weight: float = Field(ge=0.0, le=1.0)
    raw_value: float | None = None
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    available: bool = True
    evidence: list[Evidence] = Field(default_factory=list)


class AnalysisModuleResult(BaseModel):
    """
    Standard module contract from FINANCIAL_ANALYSIS_SPEC.md.

    Fields: module_name, score, confidence, metrics, findings, risks,
    opportunities, evidence, analyst_adjustments, status.
    """

    module_name: str
    module_version: str = "1.0.0"
    status: ModuleStatus = "ok"
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    metrics: list[MetricResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    opportunities: list[OpportunityItem] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    analyst_adjustments: list[AnalystAdjustmentProposal] = Field(default_factory=list)
    component_scores: list[ComponentScore] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    # Backward-compatible aliases used by earlier engine code.
    @property
    def module_id(self) -> str:
        return self.module_name

    @property
    def adjustment_proposals(self) -> list[AnalystAdjustmentProposal]:
        return self.analyst_adjustments

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "module_name" not in payload and "module_id" in payload:
            payload["module_name"] = payload.pop("module_id")
        if "analyst_adjustments" not in payload and "adjustment_proposals" in payload:
            payload["analyst_adjustments"] = payload.pop("adjustment_proposals")
        return payload

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)


class AnalysisEngineResult(BaseModel):
    """Aggregated output from running one or more analysis modules."""

    analysis_id: str
    ticker: str
    generated_at: str = Field(default_factory=utc_now_iso)
    modules: list[AnalysisModuleResult] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    metrics: list[MetricResult] = Field(default_factory=list)
    metric_comparisons: list[MetricComparison] = Field(
        default_factory=list,
        description="Aggregated Workbook vs HAP metric comparisons from module coverage extensions.",
    )
    risks: list[RiskItem] = Field(default_factory=list)
    opportunities: list[OpportunityItem] = Field(default_factory=list)
    analyst_adjustments: list[AnalystAdjustmentProposal] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
    business_quality: BusinessQualityResult | None = None
    investment_attractiveness: InvestmentAttractivenessResult | None = None
    recommendation: RecommendationResult | None = None


class BusinessQualityModuleContribution(BaseModel):
    """One Business Quality module's contribution to the roll-up score."""

    module_name: str
    weight: float = Field(ge=0.0, le=1.0)
    effective_weight: float = Field(ge=0.0, le=1.0, default=0.0)
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    status: ModuleStatus = "skipped"


class BusinessQualityResult(BaseModel):
    """
    Synthesized Business Quality assessment from completed module results.

    No financial calculations — only aggregation of upstream ``AnalysisModuleResult``
    objects per FINANCIAL_ANALYSIS_SPEC / SCORING_SYSTEM.md.
    """

    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    classification: str
    classification_label: str
    module_contributions: list[BusinessQualityModuleContribution] = Field(default_factory=list)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    strengths: list[Finding] = Field(default_factory=list)
    weaknesses: list[RiskItem] = Field(default_factory=list)
    opportunities: list[OpportunityItem] = Field(default_factory=list)
    analyst_adjustments: list[AnalystAdjustmentProposal] = Field(default_factory=list)
    skipped_modules: list[str] = Field(default_factory=list)
    low_confidence_modules: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)


class InvestmentAttractivenessModuleContribution(BaseModel):
    """One Investment Attractiveness module's contribution to the roll-up score."""

    module_name: str
    weight: float = Field(ge=0.0, le=1.0)
    effective_weight: float = Field(ge=0.0, le=1.0, default=0.0)
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    status: ModuleStatus = "skipped"


class InvestmentAttractivenessResult(BaseModel):
    """
    Synthesized Investment Attractiveness from completed valuation and expected return modules.

    No financial calculations — only aggregation of upstream ``AnalysisModuleResult`` objects.
    """

    score: float | None = Field(default=None, ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    classification: str
    classification_label: str
    module_contributions: list[InvestmentAttractivenessModuleContribution] = Field(
        default_factory=list
    )
    effective_weights: dict[str, float] = Field(default_factory=dict)
    strengths: list[Finding] = Field(default_factory=list)
    weaknesses: list[RiskItem] = Field(default_factory=list)
    opportunities: list[OpportunityItem] = Field(default_factory=list)
    analyst_adjustments: list[AnalystAdjustmentProposal] = Field(default_factory=list)
    skipped_modules: list[str] = Field(default_factory=list)
    low_confidence_modules: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def _score_bounds(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)


RecommendationCode = Literal[
    "STRONG_BUY",
    "BUY",
    "HOLD",
    "WATCH",
    "WAIT_FOR_BETTER_PRICE",
    "AVOID",
    "INSUFFICIENT_DATA",
]


class RecommendationReason(BaseModel):
    """Structured, deterministic reason supporting a final recommendation."""

    reason_id: str
    code: str
    category: Literal["business_quality", "investment_attractiveness", "synthesis"]
    summary: str
    business_quality_score: float | None = None
    investment_attractiveness_score: float | None = None
    supporting_module: str | None = None
    supporting_rule_id: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)


class RecommendationResult(BaseModel):
    """
    Final HAP recommendation synthesized from Business Quality and Investment Attractiveness.

    Deterministic synthesis only — no narrative reports or AI reasoning.
    """

    recommendation: RecommendationCode
    recommendation_label: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    business_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    investment_attractiveness_score: float | None = Field(default=None, ge=0.0, le=100.0)
    business_quality_classification: str
    investment_attractiveness_classification: str
    reasons: list[RecommendationReason] = Field(default_factory=list)
    strengths: list[Finding] = Field(default_factory=list)
    weaknesses: list[RiskItem] = Field(default_factory=list)
    opportunities: list[OpportunityItem] = Field(default_factory=list)
    analyst_adjustments: list[AnalystAdjustmentProposal] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
