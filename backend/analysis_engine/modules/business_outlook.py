"""Business Outlook analysis module — FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM.

Evaluates forward prospects from ``CompanyFinancialModel.metadata`` (outlook
namespace). Unlike historical statement modules, outlook inputs are primarily
analyst-curated forward indicators with explicit evidence provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analysis_engine.base import AnalysisModule
from analysis_engine.schemas import (
    AnalysisModuleResult,
    AnalystAdjustmentProposal,
    Evidence,
    Finding,
    MetricResult,
    OpportunityItem,
    RiskItem,
)
from analysis_engine.utils import mean
from canonical_model import CompanyFinancialModel
from rule_library.business_outlook import (
    BusinessOutlookRuleInputs,
    evaluate_business_outlook_rules,
)
from scoring_engine.business_outlook import (
    OUTLOOK_CONFIDENCE_CAP,
    BusinessOutlookScoreInputs,
    score_business_outlook,
)

# Forward-looking fields consumed from metadata["outlook"] (or flat metadata keys).
OUTLOOK_FIELDS: tuple[str, ...] = (
    "industry_growth_rate",
    "industry_growth_trend",
    "market_share_trend",
    "competitive_moat_score",
    "competitive_advantage_trend",
    "pricing_power_score",
    "product_pipeline_strength",
    "geographic_expansion_potential",
    "customer_concentration",
    "supplier_concentration",
    "regulatory_exposure",
    "regulatory_trend",
    "technological_disruption_risk",
    "revenue_guidance_trend",
    "margin_guidance_trend",
    "guidance_accuracy_score",
    "cyclicality_exposure",
    "cycle_position_score",
    "capital_allocation_plan_score",
    "margin_expansion_potential",
    "structural_growth_catalyst",
    "structural_decline_risk",
)

_METRIC_CODES: dict[str, str] = {
    "industry_growth_rate": "INDUSTRY_GROWTH_RATE",
    "industry_growth_trend": "INDUSTRY_GROWTH_TREND",
    "market_share_trend": "MARKET_SHARE_TREND",
    "competitive_moat_score": "MOAT_SCORE",
    "competitive_advantage_trend": "ADVANTAGE_TREND",
    "pricing_power_score": "PRICING_POWER_SCORE",
    "product_pipeline_strength": "PRODUCT_PIPELINE_STRENGTH",
    "geographic_expansion_potential": "GEOGRAPHIC_EXPANSION_POTENTIAL",
    "customer_concentration": "CUSTOMER_CONCENTRATION",
    "supplier_concentration": "SUPPLIER_CONCENTRATION",
    "regulatory_exposure": "REGULATORY_EXPOSURE",
    "regulatory_trend": "REGULATORY_TREND",
    "technological_disruption_risk": "TECH_DISRUPTION_RISK",
    "revenue_guidance_trend": "REVENUE_GUIDANCE_TREND",
    "margin_guidance_trend": "MARGIN_GUIDANCE_TREND",
    "guidance_accuracy_score": "GUIDANCE_ACCURACY_SCORE",
    "cyclicality_exposure": "CYCLICALITY_EXPOSURE",
    "cycle_position_score": "CYCLE_POSITION_SCORE",
    "capital_allocation_plan_score": "CAPITAL_ALLOCATION_PLAN_SCORE",
    "margin_expansion_potential": "MARGIN_EXPANSION_POTENTIAL",
    "structural_growth_catalyst": "STRUCTURAL_GROWTH_CATALYST",
    "structural_decline_risk": "STRUCTURAL_DECLINE_RISK",
}

_METRIC_NAMES: dict[str, str] = {
    "industry_growth_rate": "Industry Growth Rate",
    "industry_growth_trend": "Industry Growth Trend",
    "market_share_trend": "Market Share Trend",
    "competitive_moat_score": "Competitive Moat Score",
    "competitive_advantage_trend": "Competitive Advantage Trend",
    "pricing_power_score": "Pricing Power Score",
    "product_pipeline_strength": "Product Pipeline Strength",
    "geographic_expansion_potential": "Geographic Expansion Potential",
    "customer_concentration": "Customer Concentration",
    "supplier_concentration": "Supplier Concentration",
    "regulatory_exposure": "Regulatory Exposure",
    "regulatory_trend": "Regulatory Trend",
    "technological_disruption_risk": "Technological Disruption Risk",
    "revenue_guidance_trend": "Revenue Guidance Trend",
    "margin_guidance_trend": "Margin Guidance Trend",
    "guidance_accuracy_score": "Guidance Accuracy Score",
    "cyclicality_exposure": "Cyclicality Exposure",
    "cycle_position_score": "Cycle Position Score",
    "capital_allocation_plan_score": "Capital Allocation Plan Score",
    "margin_expansion_potential": "Margin Expansion Potential",
    "structural_growth_catalyst": "Structural Growth Catalyst",
    "structural_decline_risk": "Structural Decline Risk",
}

_RISK_BY_RULE: dict[str, str] = {
    "OUT003": "REDUCED_GROWTH_EXPECTATIONS",
    "OUT005": "INDUSTRY_HEADWINDS",
    "OUT007": "COMPETITIVE_DETERIORATION",
    "OUT009": "PRICING_PRESSURE",
    "OUT011": "WEAK_PRODUCT_PIPELINE",
    "OUT013": "CUSTOMER_CONCENTRATION",
    "OUT014": "SUPPLIER_CONCENTRATION",
    "OUT015": "REGULATORY_HEADWINDS",
    "OUT017": "TECHNOLOGICAL_DISRUPTION",
    "OUT020": "LOW_GUIDANCE_CREDIBILITY",
    "OUT021": "CYCLICAL_DOWNTURN",
    "OUT024": "MARGIN_COMPRESSION_RISK",
    "OUT027": "STRUCTURAL_DECLINE",
    "OUT028": "INSUFFICIENT_OUTLOOK_DATA",
    "OUT030": "OUTLOOK_UNCERTAINTY",
}

_OPP_BY_RULE: dict[str, str] = {
    "OUT001": "POSITIVE_FORWARD_OUTLOOK",
    "OUT002": "IMPROVING_OPERATING_OUTLOOK",
    "OUT004": "INDUSTRY_TAILWINDS",
    "OUT006": "STRENGTHENING_MOAT",
    "OUT008": "STRONG_PRICING_POWER",
    "OUT010": "ROBUST_PIPELINE",
    "OUT012": "GEOGRAPHIC_EXPANSION",
    "OUT016": "FAVORABLE_REGULATION",
    "OUT018": "TECHNOLOGY_LEADERSHIP",
    "OUT019": "CREDIBLE_GUIDANCE",
    "OUT022": "CYCLICAL_RECOVERY",
    "OUT023": "MARGIN_EXPANSION_RUNWAY",
    "OUT025": "CONSTRUCTIVE_CAPITAL_PLANS",
    "OUT026": "STRUCTURAL_GROWTH_CATALYST",
    "OUT029": "BALANCED_OUTLOOK",
}


@dataclass
class OutlookSnapshot:
    """Normalized forward-looking inputs extracted from model metadata."""

    industry_growth_rate: float | None = None
    industry_growth_trend: float | None = None
    market_share_trend: float | None = None
    moat_score: float | None = None
    advantage_trend: float | None = None
    pricing_power_score: float | None = None
    product_pipeline_strength: float | None = None
    geographic_expansion_potential: float | None = None
    customer_concentration: float | None = None
    supplier_concentration: float | None = None
    regulatory_exposure: float | None = None
    regulatory_trend: float | None = None
    technological_disruption_risk: float | None = None
    revenue_guidance_trend: float | None = None
    margin_guidance_trend: float | None = None
    guidance_accuracy_score: float | None = None
    cyclicality_exposure: float | None = None
    cycle_position_score: float | None = None
    capital_allocation_plan_score: float | None = None
    margin_expansion_potential: float | None = None
    structural_growth_catalyst: float | None = None
    structural_decline_risk: float | None = None
    field_count: int = 0
    confidence_avg: float | None = None
    evidence_by_metric: dict[str, list[Evidence]] = field(default_factory=dict)
    field_confidence: dict[str, float] = field(default_factory=dict)


class BusinessOutlookModule(AnalysisModule):
    """Evaluate future business prospects and emit the Business Outlook Score."""

    module_id = "business_outlook"
    module_version = "1.0.0"

    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        metadata = dict(model.metadata or {})
        snapshot = _extract_outlook_snapshot(metadata, model)

        if snapshot.field_count == 0:
            return AnalysisModuleResult(
                module_name=self.module_id,
                module_version=self.module_version,
                status="skipped",
                score=None,
                confidence=0.0,
                coverage={"outlook_metadata": False},
                error="Insufficient outlook metadata (need forward-looking inputs in metadata.outlook).",
            )

        period = model.periods[-1] if model.periods else None

        confidence_penalty = 0.0
        if snapshot.field_count < 3:
            confidence_penalty += 0.12
        if snapshot.field_count < 6:
            confidence_penalty += 0.08
        if snapshot.confidence_avg is not None and snapshot.confidence_avg < 0.60:
            confidence_penalty += 0.10
        category_count = _category_coverage(snapshot)
        if category_count < 3:
            confidence_penalty += 0.08

        metrics: list[MetricResult] = []
        evidence_bag: list[Evidence] = []

        for field_name in OUTLOOK_FIELDS:
            value = getattr(snapshot, _snapshot_attr(field_name), None)
            if value is None:
                continue
            code = _METRIC_CODES[field_name]
            ev = list(snapshot.evidence_by_metric.get(code, []))
            evidence_bag.extend(ev)
            metrics.append(
                MetricResult(
                    name=_METRIC_NAMES[field_name],
                    code=code,
                    value=value,
                    unit=_metric_unit(field_name),
                    period=period,
                    confidence=snapshot.field_confidence.get(field_name, 0.65),
                    evidence=ev,
                )
            )

        score_result = score_business_outlook(
            BusinessOutlookScoreInputs(
                industry_growth_rate=snapshot.industry_growth_rate,
                industry_growth_trend=snapshot.industry_growth_trend,
                moat_score=snapshot.moat_score,
                market_share_trend=snapshot.market_share_trend,
                advantage_trend=snapshot.advantage_trend,
                pricing_power_score=snapshot.pricing_power_score,
                revenue_guidance_trend=snapshot.revenue_guidance_trend,
                margin_guidance_trend=snapshot.margin_guidance_trend,
                guidance_accuracy_score=snapshot.guidance_accuracy_score,
                product_pipeline_strength=snapshot.product_pipeline_strength,
                geographic_expansion_potential=snapshot.geographic_expansion_potential,
                margin_expansion_potential=snapshot.margin_expansion_potential,
                structural_growth_catalyst=snapshot.structural_growth_catalyst,
                regulatory_exposure=snapshot.regulatory_exposure,
                regulatory_trend=snapshot.regulatory_trend,
                technological_disruption_risk=snapshot.technological_disruption_risk,
                customer_concentration=snapshot.customer_concentration,
                supplier_concentration=snapshot.supplier_concentration,
                cyclicality_exposure=snapshot.cyclicality_exposure,
                structural_decline_risk=snapshot.structural_decline_risk,
                period=period,
                evidence={
                    "INDUSTRY_TRENDS": snapshot.evidence_by_metric.get("INDUSTRY_GROWTH_RATE", []),
                    "COMPETITIVE_POSITION": snapshot.evidence_by_metric.get("MOAT_SCORE", []),
                    "MANAGEMENT_GUIDANCE": snapshot.evidence_by_metric.get(
                        "REVENUE_GUIDANCE_TREND", []
                    ),
                    "MARKET_OPPORTUNITIES": snapshot.evidence_by_metric.get(
                        "PRODUCT_PIPELINE_STRENGTH", []
                    ),
                    "STRUCTURAL_RISK": snapshot.evidence_by_metric.get("REGULATORY_EXPOSURE", []),
                },
                input_confidence=_component_confidence(snapshot),
                confidence_penalty=confidence_penalty,
            )
        )

        rule_hits = evaluate_business_outlook_rules(
            BusinessOutlookRuleInputs(
                industry_growth_rate=snapshot.industry_growth_rate,
                industry_growth_trend=snapshot.industry_growth_trend,
                moat_score=snapshot.moat_score,
                market_share_trend=snapshot.market_share_trend,
                advantage_trend=snapshot.advantage_trend,
                pricing_power_score=snapshot.pricing_power_score,
                product_pipeline_strength=snapshot.product_pipeline_strength,
                geographic_expansion_potential=snapshot.geographic_expansion_potential,
                customer_concentration=snapshot.customer_concentration,
                supplier_concentration=snapshot.supplier_concentration,
                regulatory_exposure=snapshot.regulatory_exposure,
                regulatory_trend=snapshot.regulatory_trend,
                technological_disruption_risk=snapshot.technological_disruption_risk,
                revenue_guidance_trend=snapshot.revenue_guidance_trend,
                margin_guidance_trend=snapshot.margin_guidance_trend,
                guidance_accuracy_score=snapshot.guidance_accuracy_score,
                cyclicality_exposure=snapshot.cyclicality_exposure,
                cycle_position_score=snapshot.cycle_position_score,
                capital_allocation_plan_score=snapshot.capital_allocation_plan_score,
                margin_expansion_potential=snapshot.margin_expansion_potential,
                structural_growth_catalyst=snapshot.structural_growth_catalyst,
                structural_decline_risk=snapshot.structural_decline_risk,
                outlook_field_count=snapshot.field_count,
                outlook_confidence_avg=snapshot.confidence_avg,
                period=period,
                evidence_by_metric=snapshot.evidence_by_metric,
            )
        )
        findings = [hit.to_finding() for hit in rule_hits]
        for finding in findings:
            evidence_bag.extend(finding.evidence)

        risks, opportunities = self._risks_and_opportunities(findings)
        adjustments = self._adjustment_proposals(findings, snapshot=snapshot)

        coverage = {
            "outlook_metadata": True,
            "outlook_field_count": snapshot.field_count,
            "outlook_category_count": category_count,
            "outlook_confidence_avg": snapshot.confidence_avg,
            "outlook_confidence_cap": OUTLOOK_CONFIDENCE_CAP,
            "effective_weights": score_result.effective_weights,
            "periods_used": [period] if period else [],
        }

        return AnalysisModuleResult(
            module_name=self.module_id,
            module_version=self.module_version,
            status="ok",
            score=score_result.score,
            confidence=score_result.confidence,
            metrics=metrics,
            findings=findings,
            risks=risks,
            opportunities=opportunities,
            evidence=_unique_evidence(evidence_bag),
            analyst_adjustments=adjustments,
            component_scores=score_result.components,
            coverage=coverage,
        )

    def _risks_and_opportunities(
        self,
        findings: list[Finding],
    ) -> tuple[list[RiskItem], list[OpportunityItem]]:
        risks: list[RiskItem] = []
        opportunities: list[OpportunityItem] = []
        for finding in findings:
            rule_id = finding.rule_id or ""
            if finding.severity in {"warning", "critical", "high", "medium"} and finding.direction == "negative":
                risks.append(
                    RiskItem(
                        risk_id=f"risk:{finding.finding_id}",
                        code=_RISK_BY_RULE.get(rule_id, finding.code),
                        severity=finding.severity,
                        summary=finding.summary,
                        related_finding_ids=[finding.finding_id],
                        evidence=finding.evidence,
                        confidence=finding.confidence,
                    )
                )
            if finding.severity in {"positive", "info"} and finding.direction == "positive":
                opportunities.append(
                    OpportunityItem(
                        opportunity_id=f"opp:{finding.finding_id}",
                        code=_OPP_BY_RULE.get(rule_id, finding.code),
                        summary=finding.summary,
                        related_finding_ids=[finding.finding_id],
                        evidence=finding.evidence,
                        confidence=finding.confidence,
                    )
                )
        return risks, opportunities

    def _adjustment_proposals(
        self,
        findings: list[Finding],
        *,
        snapshot: OutlookSnapshot,
    ) -> list[AnalystAdjustmentProposal]:
        adjustments: list[AnalystAdjustmentProposal] = []
        finding_ids = {f.rule_id: f.finding_id for f in findings}

        def _add(
            rule_id: str,
            action: str,
            rationale: str,
            target: str,
            priority: str = "medium",
        ) -> None:
            if rule_id not in finding_ids:
                return
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id=f"business_outlook:adj:{action}:{rule_id.lower()}",
                    action=action,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale_code=rationale,
                    target=target,
                    related_finding_ids=[finding_ids[rule_id]],
                    confidence=0.70,
                )
            )

        _add("OUT003", "adjust_forecast", "CHALLENGE_GUIDANCE", "metadata.outlook.revenue_guidance_trend", "high")
        _add("OUT003", "review_assumption", "CHALLENGE_GUIDANCE", "metadata.outlook.revenue_guidance_trend")
        _add("OUT005", "request_more_data", "REQUEST_INDUSTRY_RESEARCH", "metadata.outlook.industry_growth_rate")
        _add("OUT007", "review_assumption", "UPDATE_COMPETITIVE_ASSUMPTIONS", "metadata.outlook.competitive_moat_score")
        _add("OUT009", "review_assumption", "PRICING_PRESSURE", "metadata.outlook.pricing_power_score")
        _add("OUT011", "request_more_data", "REQUEST_PRODUCT_ROADMAP", "metadata.outlook.product_pipeline_strength")
        _add("OUT015", "request_more_data", "MONITOR_REGULATORY", "metadata.outlook.regulatory_exposure", "high")
        _add("OUT017", "flag_for_committee", "TECH_DISRUPTION", "metadata.outlook.technological_disruption_risk", "high")
        _add("OUT020", "review_assumption", "CHALLENGE_GUIDANCE", "metadata.outlook.guidance_accuracy_score", "high")
        _add("OUT021", "adjust_forecast", "CYCLICAL_DOWNSIDE", "metadata.outlook.cyclicality_exposure")
        _add("OUT024", "adjust_forecast", "MARGIN_FORECAST", "metadata.outlook.margin_expansion_potential")
        _add("OUT027", "flag_for_committee", "STRUCTURAL_DECLINE", "metadata.outlook.structural_decline_risk", "high")
        _add("OUT028", "request_more_data", "INSUFFICIENT_OUTLOOK", "metadata.outlook", "high")
        _add("OUT030", "review_assumption", "OUTLOOK_UNCERTAINTY", "metadata.outlook")

        if snapshot.field_count < 6 and "OUT028" not in finding_ids:
            adjustments.append(
                AnalystAdjustmentProposal(
                    adjustment_id="business_outlook:adj:request-outlook-overlay",
                    action="request_more_data",
                    priority="medium",
                    rationale_code="INSUFFICIENT_OUTLOOK",
                    target="metadata.outlook",
                    confidence=0.80,
                )
            )
        return adjustments


def _extract_outlook_snapshot(
    metadata: dict[str, Any],
    model: CompanyFinancialModel,
) -> OutlookSnapshot:
    outlook_block = metadata.get("outlook")
    if not isinstance(outlook_block, dict):
        outlook_block = {}
    evidence_catalog = metadata.get("outlook_evidence")
    if not isinstance(evidence_catalog, dict):
        evidence_catalog = {}

    snapshot = OutlookSnapshot()
    confidences: list[float] = []

    for field_name in OUTLOOK_FIELDS:
        raw = outlook_block.get(field_name)
        if raw is None:
            raw = metadata.get(field_name)
        value = _coerce_float(raw)
        if value is None:
            continue
        attr = _snapshot_attr(field_name)
        setattr(snapshot, attr, value)
        snapshot.field_count += 1

        field_evidence = evidence_catalog.get(field_name)
        if not isinstance(field_evidence, dict):
            field_evidence = {}

        source = field_evidence.get("source") or "company_metadata"
        source_document = field_evidence.get("source_document")
        field_conf = _coerce_float(field_evidence.get("confidence"))
        if field_conf is None:
            field_conf = 0.65
        field_conf = min(OUTLOOK_CONFIDENCE_CAP, field_conf)
        snapshot.field_confidence[field_name] = field_conf
        confidences.append(field_conf)

        code = _METRIC_CODES[field_name]
        ev = Evidence(
            kind="financial_fact",
            label=_METRIC_NAMES[field_name],
            metric=code,
            concept=field_name,
            period=model.periods[-1] if model.periods else None,
            value=value,
            unit=_metric_unit(field_name),
            source=str(source),
            source_document=str(source_document) if source_document else None,
            confidence=field_conf,
            provenance={
                "namespace": "metadata.outlook",
                "field": field_name,
                **{k: v for k, v in field_evidence.items() if k not in {"source", "confidence"}},
            },
        )
        snapshot.evidence_by_metric.setdefault(code, []).append(ev)

    if snapshot.field_count == 0:
        terminal = model.valuation_inputs.terminal_growth_rate
        if terminal is not None:
            snapshot.industry_growth_rate = terminal
            snapshot.field_count = 1
            snapshot.field_confidence["industry_growth_rate"] = 0.55
            confidences.append(0.55)
            ev = Evidence(
                kind="derived_metric",
                label="Terminal Growth Assumption",
                metric="INDUSTRY_GROWTH_RATE",
                concept="terminal_growth_rate",
                period=model.periods[-1] if model.periods else None,
                value=terminal,
                unit="ratio",
                source="valuation_inputs",
                confidence=0.55,
                provenance={"field": "valuation_inputs.terminal_growth_rate"},
                details={"note": "fallback_from_valuation_inputs"},
            )
            snapshot.evidence_by_metric["INDUSTRY_GROWTH_RATE"] = [ev]

    snapshot.confidence_avg = mean(confidences) if confidences else None
    return snapshot


def _snapshot_attr(field_name: str) -> str:
    mapping = {
        "competitive_moat_score": "moat_score",
        "competitive_advantage_trend": "advantage_trend",
    }
    return mapping.get(field_name, field_name)


def _coerce_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _metric_unit(field_name: str) -> str:
    if field_name.endswith("_rate") or field_name.endswith("_score") or "trend" in field_name:
        return "ratio"
    if "concentration" in field_name or "exposure" in field_name or "risk" in field_name:
        return "ratio"
    if "potential" in field_name or "catalyst" in field_name or "strength" in field_name:
        return "score"
    return "ratio"


def _category_coverage(snapshot: OutlookSnapshot) -> int:
    categories = 0
    if snapshot.industry_growth_rate is not None or snapshot.industry_growth_trend is not None:
        categories += 1
    if (
        snapshot.moat_score is not None
        or snapshot.market_share_trend is not None
        or snapshot.advantage_trend is not None
    ):
        categories += 1
    if (
        snapshot.revenue_guidance_trend is not None
        or snapshot.margin_guidance_trend is not None
        or snapshot.guidance_accuracy_score is not None
    ):
        categories += 1
    if (
        snapshot.product_pipeline_strength is not None
        or snapshot.geographic_expansion_potential is not None
        or snapshot.structural_growth_catalyst is not None
    ):
        categories += 1
    if (
        snapshot.regulatory_exposure is not None
        or snapshot.technological_disruption_risk is not None
        or snapshot.customer_concentration is not None
    ):
        categories += 1
    return categories


def _component_confidence(snapshot: OutlookSnapshot) -> dict[str, float]:
    def _avg(fields: tuple[str, ...]) -> float | None:
        values = [snapshot.field_confidence[f] for f in fields if f in snapshot.field_confidence]
        return mean(values) if values else None

    mapping = {
        "INDUSTRY_TRENDS": _avg(("industry_growth_rate", "industry_growth_trend")),
        "COMPETITIVE_POSITION": _avg(
            ("competitive_moat_score", "market_share_trend", "competitive_advantage_trend", "pricing_power_score")
        ),
        "MANAGEMENT_GUIDANCE": _avg(
            ("revenue_guidance_trend", "margin_guidance_trend", "guidance_accuracy_score")
        ),
        "MARKET_OPPORTUNITIES": _avg(
            (
                "product_pipeline_strength",
                "geographic_expansion_potential",
                "margin_expansion_potential",
                "structural_growth_catalyst",
            )
        ),
        "STRUCTURAL_RISK": _avg(
            (
                "regulatory_exposure",
                "technological_disruption_risk",
                "customer_concentration",
                "supplier_concentration",
                "cyclicality_exposure",
                "structural_decline_risk",
            )
        ),
    }
    return {
        code: min(OUTLOOK_CONFIDENCE_CAP, value)
        for code, value in mapping.items()
        if value is not None
    }


def _unique_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str | None, str | None, str | None, float | None]] = set()
    unique: list[Evidence] = []
    for item in items:
        key = (item.label, item.metric or item.concept, item.period, item.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
