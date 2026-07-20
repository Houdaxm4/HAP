"""Business Quality aggregator tests."""

from __future__ import annotations

from analysis_engine import (
    BUSINESS_QUALITY_MODULE_NAMES,
    BusinessQualityAggregator,
    aggregate_business_quality,
)
from analysis_engine.schemas import (
    AnalysisModuleResult,
    AnalystAdjustmentProposal,
    Evidence,
    Finding,
    OpportunityItem,
    RiskItem,
)
from scoring_engine import BUSINESS_QUALITY_WEIGHTS


def _evidence(label: str = "test") -> list[Evidence]:
    return [
        Evidence(
            kind="rule_trigger",
            label=label,
            metric="TEST",
            value=1.0,
            confidence=0.85,
            source="unit_test",
        )
    ]


def _module(
    name: str,
    *,
    score: float | None,
    confidence: float = 0.85,
    status: str = "ok",
    findings: list[Finding] | None = None,
    risks: list[RiskItem] | None = None,
    opportunities: list[OpportunityItem] | None = None,
    adjustments: list[AnalystAdjustmentProposal] | None = None,
) -> AnalysisModuleResult:
    return AnalysisModuleResult(
        module_name=name,
        status=status,  # type: ignore[arg-type]
        score=score,
        confidence=confidence,
        findings=findings or [],
        risks=risks or [],
        opportunities=opportunities or [],
        analyst_adjustments=adjustments or [],
    )


def _positive_finding(
    finding_id: str,
    *,
    confidence: float = 0.90,
    evidence_confidence: float = 0.88,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        code="STRONG_ROIC",
        rule_id="PR001",
        severity="positive",
        direction="positive",
        category="profitability",
        summary="Excellent ROIC",
        evidence=[
            Evidence(
                kind="rule_trigger",
                label="ROIC",
                metric="ROIC",
                value=0.22,
                confidence=evidence_confidence,
                source="unit_test",
            )
        ],
        confidence=confidence,
    )


def _risk(
    risk_id: str,
    *,
    severity: str = "warning",
    confidence: float = 0.80,
) -> RiskItem:
    return RiskItem(
        risk_id=risk_id,
        code="HIGH_LEVERAGE",
        severity=severity,  # type: ignore[arg-type]
        summary="Elevated leverage",
        evidence=_evidence("debt"),
        confidence=confidence,
    )


def _opportunity(opportunity_id: str, *, confidence: float = 0.82) -> OpportunityItem:
    return OpportunityItem(
        opportunity_id=opportunity_id,
        code="STRONG_GROWTH",
        summary="Sustained revenue growth",
        evidence=_evidence("growth"),
        confidence=confidence,
    )


def _full_bq_modules(scores: dict[str, float]) -> list[AnalysisModuleResult]:
    return [
        _module(name, score=scores.get(name, 80.0))
        for name in BUSINESS_QUALITY_MODULE_NAMES
    ]


def test_weights_match_scoring_system() -> None:
    assert BUSINESS_QUALITY_WEIGHTS["profitability"] == 0.25
    assert BUSINESS_QUALITY_WEIGHTS["growth"] == 0.15
    assert BUSINESS_QUALITY_WEIGHTS["cash_flow"] == 0.20
    assert BUSINESS_QUALITY_WEIGHTS["balance_sheet"] == 0.15
    assert BUSINESS_QUALITY_WEIGHTS["capital_allocation"] == 0.15
    assert BUSINESS_QUALITY_WEIGHTS["business_outlook"] == 0.10
    assert abs(sum(BUSINESS_QUALITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_exceptional_business_classification() -> None:
    modules = _full_bq_modules(
        {
            "profitability": 95.0,
            "growth": 92.0,
            "cash_flow": 94.0,
            "balance_sheet": 91.0,
            "capital_allocation": 93.0,
            "business_outlook": 88.0,
        }
    )
    result = aggregate_business_quality(modules)
    assert result.score is not None and result.score >= 90.0
    assert result.classification == "EXCEPTIONAL_BUSINESS"
    assert result.classification_label == "Exceptional Business"
    assert len(result.module_contributions) == 6
    assert abs(sum(result.effective_weights.values()) - 1.0) < 1e-9


def test_average_business_classification() -> None:
    modules = _full_bq_modules({name: 65.0 for name in BUSINESS_QUALITY_MODULE_NAMES})
    result = aggregate_business_quality(modules)
    assert result.score == 65.0
    assert result.classification == "AVERAGE_BUSINESS"
    assert result.classification_label == "Average Business"


def test_weak_business_classification() -> None:
    modules = _full_bq_modules({name: 45.0 for name in BUSINESS_QUALITY_MODULE_NAMES})
    result = aggregate_business_quality(modules)
    assert result.score == 45.0
    assert result.classification == "WEAK_BUSINESS"
    assert result.classification_label == "Weak Business"


def test_skipped_modules_reduce_confidence_and_renormalize() -> None:
    modules = [
        _module("profitability", score=88.0, confidence=0.90),
        _module("growth", score=88.0, confidence=0.88),
        _module("cash_flow", score=88.0, confidence=0.86),
        _module("balance_sheet", status="skipped", score=None, confidence=0.0),
        _module("capital_allocation", status="skipped", score=None, confidence=0.0),
        _module("business_outlook", status="skipped", score=None, confidence=0.0),
    ]
    full = aggregate_business_quality(_full_bq_modules({name: 88.0 for name in BUSINESS_QUALITY_MODULE_NAMES}))
    partial = aggregate_business_quality(modules)

    assert partial.score == 88.0
    assert "balance_sheet" in partial.skipped_modules
    assert partial.confidence < full.confidence
    assert set(partial.effective_weights) == {"profitability", "growth", "cash_flow"}
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_low_confidence_modules_reduce_overall_confidence() -> None:
    high_conf_modules = _full_bq_modules({name: 80.0 for name in BUSINESS_QUALITY_MODULE_NAMES})
    low_conf_modules = [
        _module(name, score=80.0, confidence=0.45 if name == "growth" else 0.85)
        for name in BUSINESS_QUALITY_MODULE_NAMES
    ]
    high = aggregate_business_quality(high_conf_modules)
    low = aggregate_business_quality(low_conf_modules)
    assert "growth" in low.low_confidence_modules
    assert low.confidence < high.confidence


def test_strengths_ranked_by_confidence_and_evidence() -> None:
    modules = [
        _module(
            "profitability",
            score=90.0,
            findings=[_positive_finding("f-strong", confidence=0.95, evidence_confidence=0.92)],
        ),
        _module(
            "growth",
            score=85.0,
            findings=[_positive_finding("f-weaker", confidence=0.70, evidence_confidence=0.65)],
        ),
        _module("cash_flow", score=80.0),
        _module("balance_sheet", score=80.0),
        _module("capital_allocation", score=80.0),
        _module("business_outlook", score=80.0),
    ]
    result = aggregate_business_quality(modules)
    assert len(result.strengths) == 2
    assert result.strengths[0].finding_id == "f-strong"
    assert all(item.evidence for item in result.strengths)


def test_weaknesses_ranked_by_severity() -> None:
    modules = [
        _module(
            "profitability",
            score=70.0,
            risks=[_risk("r-warn", severity="warning", confidence=0.90)],
        ),
        _module(
            "balance_sheet",
            score=65.0,
            risks=[_risk("r-crit", severity="critical", confidence=0.75)],
        ),
        _module("growth", score=70.0),
        _module("cash_flow", score=70.0),
        _module("capital_allocation", score=70.0),
        _module("business_outlook", score=70.0),
    ]
    result = aggregate_business_quality(modules)
    assert len(result.weaknesses) == 2
    assert result.weaknesses[0].risk_id == "r-crit"


def test_opportunities_aggregated() -> None:
    modules = [
        _module("profitability", score=80.0, opportunities=[_opportunity("o1", confidence=0.90)]),
        _module("growth", score=80.0, opportunities=[_opportunity("o2", confidence=0.75)]),
        _module("cash_flow", score=80.0),
        _module("balance_sheet", score=80.0),
        _module("capital_allocation", score=80.0),
        _module("business_outlook", score=80.0),
    ]
    result = aggregate_business_quality(modules)
    assert len(result.opportunities) == 2
    assert result.opportunities[0].opportunity_id == "o1"


def test_adjustments_deduplicated_and_merged() -> None:
    dup_a = AnalystAdjustmentProposal(
        adjustment_id="profitability:adj:review:pr001",
        action="review_assumption",
        priority="medium",
        rationale_code="MARGIN_COMPRESSION",
        target="income_statement.operating_income",
        related_finding_ids=["f1"],
        confidence=0.70,
    )
    dup_b = AnalystAdjustmentProposal(
        adjustment_id="growth:adj:review:gr007",
        action="review_assumption",
        priority="high",
        rationale_code="MARGIN_COMPRESSION",
        target="income_statement.operating_income",
        related_finding_ids=["f2"],
        confidence=0.80,
    )
    unique = AnalystAdjustmentProposal(
        adjustment_id="cash_flow:adj:request-history",
        action="request_more_data",
        priority="medium",
        rationale_code="INSUFFICIENT_CASH_FLOW_HISTORY",
        target="cash_flow_statement.free_cash_flow",
        confidence=0.85,
    )
    modules = [
        _module("profitability", score=80.0, adjustments=[dup_a]),
        _module("growth", score=80.0, adjustments=[dup_b]),
        _module("cash_flow", score=80.0, adjustments=[unique]),
        _module("balance_sheet", score=80.0),
        _module("capital_allocation", score=80.0),
        _module("business_outlook", score=80.0),
    ]
    result = aggregate_business_quality(modules)
    assert len(result.analyst_adjustments) == 2
    merged = next(
        item
        for item in result.analyst_adjustments
        if item.rationale_code == "MARGIN_COMPRESSION"
    )
    assert merged.priority == "high"
    assert set(merged.related_finding_ids) == {"f1", "f2"}
    assert merged.confidence == 0.80


def test_conflicting_findings_preserved() -> None:
    positive = _positive_finding("f-pos")
    risk = _risk("r-neg", severity="critical")
    modules = [
        _module("profitability", score=75.0, findings=[positive], risks=[risk]),
        _module("growth", score=75.0),
        _module("cash_flow", score=75.0),
        _module("balance_sheet", score=75.0),
        _module("capital_allocation", score=75.0),
        _module("business_outlook", score=75.0),
    ]
    result = aggregate_business_quality(modules)
    assert any(item.finding_id == "f-pos" for item in result.strengths)
    assert any(item.risk_id == "r-neg" for item in result.weaknesses)


def test_deterministic_output() -> None:
    modules = _full_bq_modules(
        {
            "profitability": 82.0,
            "growth": 78.0,
            "cash_flow": 80.0,
            "balance_sheet": 76.0,
            "capital_allocation": 79.0,
            "business_outlook": 74.0,
        }
    )
    first = BusinessQualityAggregator().aggregate(modules)
    second = BusinessQualityAggregator().aggregate(modules)
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert first.classification == second.classification
    assert [item.finding_id for item in first.strengths] == [
        item.finding_id for item in second.strengths
    ]


def test_no_scored_modules_returns_insufficient_data() -> None:
    modules = [
        _module(name, status="skipped", score=None, confidence=0.0)
        for name in BUSINESS_QUALITY_MODULE_NAMES
    ]
    result = aggregate_business_quality(modules)
    assert result.score is None
    assert result.classification == "INSUFFICIENT_DATA"
    assert result.confidence == 0.0
    assert len(result.skipped_modules) == 6


def test_ignores_non_business_quality_modules() -> None:
    modules = _full_bq_modules({name: 80.0 for name in BUSINESS_QUALITY_MODULE_NAMES})
    modules.append(_module("valuation", score=50.0, confidence=0.50))
    modules.append(_module("recommendation", status="skipped", score=None))
    result = aggregate_business_quality(modules)
    assert result.score == 80.0
    assert "valuation" not in result.effective_weights
