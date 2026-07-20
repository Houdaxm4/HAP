"""Business Outlook module tests per FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, BusinessOutlookModule
from canonical_model import CompanyFinancialModel, build_company_financial_model
from rule_library import evaluate_business_outlook_rules
from rule_library.business_outlook import BusinessOutlookRuleInputs
from scoring_engine import BUSINESS_OUTLOOK_WEIGHTS, score_business_outlook
from scoring_engine.business_outlook import OUTLOOK_CONFIDENCE_CAP, BusinessOutlookScoreInputs


def _outlook(**fields: float) -> dict:
    return {"outlook": dict(fields)}


def _evidence(**fields: dict) -> dict:
    return {"outlook_evidence": dict(fields)}


def _build(
    *,
    outlook: dict | None = None,
    outlook_evidence: dict | None = None,
    extra_metadata: dict | None = None,
) -> CompanyFinancialModel:
    metadata: dict = {}
    if outlook:
        metadata["outlook"] = outlook
    if outlook_evidence:
        metadata["outlook_evidence"] = outlook_evidence
    if extra_metadata:
        metadata.update(extra_metadata)
    return build_company_financial_model(
        analysis_id="outlook-test",
        ticker="OUT",
        company="Outlook Co",
        workbook_cells=[],
        metadata=metadata,
    )


def _rule_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings if f.rule_id}


def test_business_outlook_weights() -> None:
    assert BUSINESS_OUTLOOK_WEIGHTS["INDUSTRY_TRENDS"] == 0.20
    assert BUSINESS_OUTLOOK_WEIGHTS["COMPETITIVE_POSITION"] == 0.25
    assert BUSINESS_OUTLOOK_WEIGHTS["MANAGEMENT_GUIDANCE"] == 0.20
    assert BUSINESS_OUTLOOK_WEIGHTS["MARKET_OPPORTUNITIES"] == 0.20
    assert BUSINESS_OUTLOOK_WEIGHTS["STRUCTURAL_RISK"] == 0.15
    assert abs(sum(BUSINESS_OUTLOOK_WEIGHTS.values()) - 1.0) < 1e-9


def test_mature_stable_company() -> None:
    """Low growth industry, strong moat, credible guidance, balanced risks."""
    model = _build(
        outlook={
            "industry_growth_rate": 0.025,
            "industry_growth_trend": 0.05,
            "competitive_moat_score": 0.82,
            "competitive_advantage_trend": 0.08,
            "pricing_power_score": 0.78,
            "revenue_guidance_trend": 0.20,
            "margin_guidance_trend": 0.15,
            "guidance_accuracy_score": 0.88,
            "customer_concentration": 0.12,
            "regulatory_exposure": 0.20,
            "technological_disruption_risk": 0.18,
            "cyclicality_exposure": 0.25,
        },
        outlook_evidence={
            "competitive_moat_score": {
                "source": "sec_filing",
                "source_document": "10-K Item 1A Competition",
                "confidence": 0.80,
            },
            "revenue_guidance_trend": {
                "source": "management_guidance",
                "source_document": "Q4 2024 Earnings Release",
                "confidence": 0.85,
            },
        },
    )
    result = BusinessOutlookModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and result.score >= 65
    rules = _rule_ids(result)
    assert "OUT006" in rules or "OUT019" in rules
    assert result.confidence <= OUTLOOK_CONFIDENCE_CAP
    assert all(m.evidence for m in result.metrics)
    for finding in result.findings:
        assert finding.evidence


def test_high_growth_technology_company() -> None:
    model = _build(
        outlook={
            "industry_growth_rate": 0.12,
            "industry_growth_trend": 0.25,
            "competitive_moat_score": 0.75,
            "product_pipeline_strength": 0.85,
            "geographic_expansion_potential": 0.70,
            "revenue_guidance_trend": 1.0,
            "margin_guidance_trend": 0.50,
            "structural_growth_catalyst": 0.80,
            "technological_disruption_risk": 0.20,
            "customer_concentration": 0.18,
        },
        outlook_evidence={
            "product_pipeline_strength": {
                "source": "company_metadata",
                "source_document": "Investor Day 2025",
                "confidence": 0.75,
            },
        },
    )
    result = BusinessOutlookModule().analyze(model)
    assert result.status == "ok"
    rules = _rule_ids(result)
    assert "OUT001" in rules
    assert "OUT004" in rules or "OUT010" in rules
    assert "OUT026" in rules
    assert result.score is not None and result.score >= 70


def test_company_facing_disruption() -> None:
    model = _build(
        outlook={
            "competitive_moat_score": 0.35,
            "competitive_advantage_trend": -0.15,
            "market_share_trend": -0.20,
            "technological_disruption_risk": 0.85,
            "structural_decline_risk": 0.75,
            "pricing_power_score": 0.25,
            "product_pipeline_strength": 0.20,
            "revenue_guidance_trend": -0.50,
        },
        outlook_evidence={
            "technological_disruption_risk": {
                "source": "industry_metadata",
                "source_document": "Sector disruption analysis",
                "confidence": 0.70,
            },
        },
    )
    result = BusinessOutlookModule().analyze(model)
    rules = _rule_ids(result)
    assert "OUT003" in rules
    assert "OUT007" in rules
    assert "OUT017" in rules
    assert "OUT027" in rules
    assert any(r.code == "TECHNOLOGICAL_DISRUPTION" for r in result.risks)
    assert result.score is not None and result.score < 55


def test_cyclical_company() -> None:
    model = _build(
        outlook={
            "cyclicality_exposure": 0.80,
            "cycle_position_score": -0.30,
            "industry_growth_rate": -0.02,
            "industry_growth_trend": -0.25,
            "margin_guidance_trend": -0.40,
            "customer_concentration": 0.22,
        },
    )
    result = BusinessOutlookModule().analyze(model)
    rules = _rule_ids(result)
    assert "OUT005" in rules or "OUT021" in rules
    assert "OUT024" in rules


def test_cyclical_recovery() -> None:
    model = _build(
        outlook={
            "cyclicality_exposure": 0.70,
            "cycle_position_score": 0.65,
            "industry_growth_trend": 0.15,
            "margin_expansion_potential": 0.30,
        },
    )
    result = BusinessOutlookModule().analyze(model)
    assert "OUT022" in _rule_ids(result)


def test_regulatory_headwinds() -> None:
    model = _build(
        outlook={
            "regulatory_exposure": 0.75,
            "regulatory_trend": -0.30,
            "competitive_moat_score": 0.55,
            "margin_guidance_trend": -0.20,
            "industry_growth_rate": 0.02,
        },
        outlook_evidence={
            "regulatory_exposure": {
                "source": "sec_filing",
                "source_document": "10-K Risk Factors",
                "confidence": 0.82,
            },
        },
    )
    result = BusinessOutlookModule().analyze(model)
    assert "OUT015" in _rule_ids(result)
    assert any(a.action == "request_more_data" for a in result.analyst_adjustments)


def test_strong_competitive_moat() -> None:
    model = _build(
        outlook={
            "competitive_moat_score": 0.90,
            "competitive_advantage_trend": 0.12,
            "market_share_trend": 0.18,
            "pricing_power_score": 0.88,
            "technological_disruption_risk": 0.15,
            "guidance_accuracy_score": 0.85,
            "regulatory_exposure": 0.15,
        },
    )
    result = BusinessOutlookModule().analyze(model)
    rules = _rule_ids(result)
    assert "OUT006" in rules
    assert "OUT008" in rules
    assert "OUT018" in rules
    assert result.score is not None and result.score >= 75


def test_insufficient_outlook_data() -> None:
    model = _build(outlook={"industry_growth_rate": 0.03})
    result = BusinessOutlookModule().analyze(model)
    assert "OUT028" in _rule_ids(result)
    assert result.confidence < 0.65


def test_module_skips_without_outlook() -> None:
    model = CompanyFinancialModel(analysis_id="empty", ticker="NONE")
    result = BusinessOutlookModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None


def test_deterministic_scoring() -> None:
    inputs = BusinessOutlookScoreInputs(
        industry_growth_rate=0.05,
        industry_growth_trend=0.10,
        moat_score=0.75,
        revenue_guidance_trend=0.50,
        product_pipeline_strength=0.70,
        regulatory_exposure=0.25,
        technological_disruption_risk=0.20,
    )
    first = score_business_outlook(inputs)
    second = score_business_outlook(inputs)
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert first.confidence <= OUTLOOK_CONFIDENCE_CAP


def test_rules_emit_evidence() -> None:
    hits = evaluate_business_outlook_rules(
        BusinessOutlookRuleInputs(
            revenue_guidance_trend=1.0,
            margin_guidance_trend=0.5,
            outlook_field_count=6,
            period="FY2024",
        )
    )
    assert hits
    for hit in hits:
        finding = hit.to_finding()
        assert finding.evidence
        assert finding.rule_id is not None


def test_evidence_provenance_from_metadata() -> None:
    model = _build(
        outlook={"revenue_guidance_trend": 1.0},
        outlook_evidence={
            "revenue_guidance_trend": {
                "source": "management_guidance",
                "source_document": "Q1 2025 Earnings Call",
                "confidence": 0.88,
            },
        },
    )
    result = BusinessOutlookModule().analyze(model)
    metric = next(m for m in result.metrics if m.code == "REVENUE_GUIDANCE_TREND")
    assert metric.evidence
    assert metric.evidence[0].source == "management_guidance"
    assert metric.evidence[0].source_document == "Q1 2025 Earnings Call"


def test_engine_includes_business_outlook() -> None:
    model = _build(
        outlook={
            "industry_growth_rate": 0.04,
            "competitive_moat_score": 0.70,
            "revenue_guidance_trend": 0.5,
            "product_pipeline_strength": 0.65,
            "regulatory_exposure": 0.30,
        },
    )
    engine_result = AnalysisEngine().run(model)
    outlook = next(m for m in engine_result.modules if m.module_name == "business_outlook")
    assert outlook.status == "ok"
    assert outlook.score is not None
