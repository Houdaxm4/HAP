"""Recommendation engine tests."""

from __future__ import annotations

from analysis_engine import (
    BUSINESS_QUALITY_MODULE_NAMES,
    RecommendationEngine,
    aggregate_business_quality,
    aggregate_investment_attractiveness,
    generate_recommendation,
)
from analysis_engine.modules.recommendation import wrap_recommendation
from analysis_engine.schemas import (
    AnalysisModuleResult,
    Evidence,
    Finding,
    InvestmentAttractivenessResult,
    RiskItem,
)


def _evidence() -> list[Evidence]:
    return [
        Evidence(
            kind="rule_trigger",
            label="test",
            metric="TEST",
            value=1.0,
            confidence=0.85,
            source="unit_test",
        )
    ]


def _module(name: str, *, score: float | None, confidence: float = 0.85) -> AnalysisModuleResult:
    return AnalysisModuleResult(
        module_name=name,
        status="ok" if score is not None else "skipped",
        score=score,
        confidence=confidence,
    )


def _bq_modules(score: float) -> list[AnalysisModuleResult]:
    return [_module(name, score=score) for name in BUSINESS_QUALITY_MODULE_NAMES]


def _ia_modules(valuation: float, expected_return: float) -> list[AnalysisModuleResult]:
    return [
        _module("valuation", score=valuation),
        _module("expected_return", score=expected_return),
    ]


def _all_modules(bq: float, valuation: float, expected_return: float) -> list[AnalysisModuleResult]:
    return _bq_modules(bq) + _ia_modules(valuation, expected_return)


def test_strong_buy_when_high_bq_and_high_ia() -> None:
    modules = _all_modules(95.0, 95.0, 92.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "STRONG_BUY"
    assert result.recommendation_label == "Strong Buy"
    assert any(reason.code == "HIGH_QUALITY_ATTRACTIVE_PRICE" for reason in result.reasons)


def test_buy_when_high_bq_and_good_ia() -> None:
    modules = _all_modules(92.0, 75.0, 72.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "BUY"


def test_watch_when_high_bq_and_fair_ia() -> None:
    modules = _all_modules(92.0, 62.0, 60.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "WATCH"
    assert any(reason.code == "QUALITY_WITHOUT_ATTRACTIVE_PRICE" for reason in result.reasons)


def test_wait_for_better_price_when_high_bq_and_poor_ia() -> None:
    modules = _all_modules(92.0, 55.0, 52.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "WAIT_FOR_BETTER_PRICE"


def test_avoid_when_weak_business_quality() -> None:
    modules = _all_modules(45.0, 90.0, 90.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "AVOID"
    assert any(reason.code == "WEAK_BUSINESS_QUALITY" for reason in result.reasons)


def test_avoid_when_poor_investment_attractiveness() -> None:
    modules = _all_modules(75.0, 40.0, 35.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "AVOID"
    assert any(reason.code == "POOR_INVESTMENT_ATTRACTIVENESS" for reason in result.reasons)


def test_hold_when_good_bq_and_fair_ia() -> None:
    modules = _all_modules(75.0, 65.0, 62.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "HOLD"


def test_speculative_value_trap_reason_when_attractive_price_weak_business() -> None:
    modules = _all_modules(65.0, 85.0, 82.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.recommendation == "HOLD"
    assert any(reason.code == "SPECULATIVE_VALUE_TRAP" for reason in result.reasons)


def test_insufficient_data_when_scores_missing() -> None:
    bq = aggregate_business_quality(
        [_module(name, score=None, confidence=0.0) for name in BUSINESS_QUALITY_MODULE_NAMES]
    )
    ia = InvestmentAttractivenessResult(
        score=None,
        confidence=0.0,
        classification="INSUFFICIENT_DATA",
        classification_label="Insufficient Data",
    )
    result = generate_recommendation(bq, ia, [])
    assert result.recommendation == "INSUFFICIENT_DATA"
    assert result.confidence == 0.0


def test_reasons_are_structured_not_narrative() -> None:
    modules = _all_modules(92.0, 95.0, 92.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert result.reasons
    for reason in result.reasons:
        assert reason.reason_id
        assert reason.code
        assert reason.category in {"business_quality", "investment_attractiveness", "synthesis"}
        assert reason.summary
        dumped = reason.model_dump()
        assert "report" not in dumped
        assert "narrative" not in dumped


def test_strengths_and_weaknesses_merged_from_bq_and_ia() -> None:
    strength = Finding(
        finding_id="f1",
        code="STRONG_ROIC",
        rule_id="PR001",
        severity="positive",
        direction="positive",
        category="profitability",
        summary="Strong ROIC",
        evidence=_evidence(),
        confidence=0.90,
    )
    risk = RiskItem(
        risk_id="r1",
        code="POTENTIAL_OVERVALUATION",
        severity="warning",
        summary="Overvalued",
        evidence=_evidence(),
        confidence=0.80,
    )
    modules = _all_modules(92.0, 95.0, 92.0)
    modules[0] = AnalysisModuleResult(
        module_name="profitability",
        status="ok",
        score=92.0,
        confidence=0.90,
        findings=[strength],
    )
    modules[-2] = AnalysisModuleResult(
        module_name="valuation",
        status="ok",
        score=95.0,
        confidence=0.90,
        risks=[risk],
    )
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    result = generate_recommendation(bq, ia, modules)
    assert any(item.finding_id == "f1" for item in result.strengths)
    assert any(item.risk_id == "r1" for item in result.weaknesses)


def test_recommendation_confidence_penalizes_skipped_modules() -> None:
    modules = _all_modules(92.0, 95.0, 92.0)
    modules[-1] = _module("expected_return", score=None, confidence=0.0)
    modules[-1] = AnalysisModuleResult(
        module_name="expected_return",
        status="skipped",
        score=None,
        confidence=0.0,
    )
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    full_ia_modules = _all_modules(92.0, 95.0, 92.0)
    full_bq = aggregate_business_quality(full_ia_modules)
    full_ia = aggregate_investment_attractiveness(full_ia_modules)
    full = generate_recommendation(full_bq, full_ia, full_ia_modules)
    partial = generate_recommendation(bq, ia, modules)
    assert partial.confidence < full.confidence


def test_deterministic_output() -> None:
    modules = _all_modules(82.0, 78.0, 76.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    first = RecommendationEngine().recommend(bq, ia, modules)
    second = RecommendationEngine().recommend(bq, ia, modules)
    assert first.recommendation == second.recommendation
    assert first.confidence == second.confidence
    assert [item.reason_id for item in first.reasons] == [
        item.reason_id for item in second.reasons
    ]


def test_wrap_recommendation_module_result() -> None:
    modules = _all_modules(92.0, 95.0, 92.0)
    bq = aggregate_business_quality(modules)
    ia = aggregate_investment_attractiveness(modules)
    recommendation = generate_recommendation(bq, ia, modules)
    result = wrap_recommendation(recommendation, bq, ia)
    assert result.module_name == "recommendation"
    assert result.status == "ok"
    assert result.coverage["recommendation_code"] == "STRONG_BUY"
    assert result.coverage["business_quality_classification"] == "EXCEPTIONAL_BUSINESS"
    assert result.coverage["investment_attractiveness_classification"] == "EXCEPTIONAL_OPPORTUNITY"
    assert result.findings
    assert all(finding.category == "recommendation" for finding in result.findings)
