"""Investment Attractiveness aggregator tests."""

from __future__ import annotations

from analysis_engine import (
    INVESTMENT_ATTRACTIVENESS_MODULE_NAMES,
    InvestmentAttractivenessAggregator,
    aggregate_investment_attractiveness,
)
from analysis_engine.schemas import (
    AnalysisModuleResult,
    AnalystAdjustmentProposal,
    Evidence,
    Finding,
    OpportunityItem,
    RiskItem,
)
from scoring_engine.weights import INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS


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


def _positive_finding(finding_id: str, *, confidence: float = 0.90) -> Finding:
    return Finding(
        finding_id=finding_id,
        code="ATTRACTIVE_VALUATION",
        rule_id="VA001",
        severity="positive",
        direction="positive",
        category="valuation",
        summary="Strong margin of safety",
        evidence=_evidence("mos"),
        confidence=confidence,
    )


def _risk(risk_id: str, *, severity: str = "warning", confidence: float = 0.80) -> RiskItem:
    return RiskItem(
        risk_id=risk_id,
        code="POTENTIAL_OVERVALUATION",
        severity=severity,  # type: ignore[arg-type]
        summary="Price above intrinsic value",
        evidence=_evidence("price"),
        confidence=confidence,
    )


def _opportunity(opportunity_id: str, *, confidence: float = 0.82) -> OpportunityItem:
    return OpportunityItem(
        opportunity_id=opportunity_id,
        code="HIGH_EXPECTED_RETURN",
        summary="Expected return exceeds hurdle",
        evidence=_evidence("er"),
        confidence=confidence,
    )


def _full_ia_modules(valuation: float, expected_return: float) -> list[AnalysisModuleResult]:
    return [
        _module("valuation", score=valuation),
        _module("expected_return", score=expected_return),
    ]


def test_weights_match_scoring_system() -> None:
    assert INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS["valuation"] == 0.70
    assert INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS["expected_return"] == 0.30
    assert abs(sum(INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS.values()) - 1.0) < 1e-9


def test_exceptional_opportunity_classification() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(95.0, 92.0))
    assert result.score is not None and result.score >= 90.0
    assert result.classification == "EXCEPTIONAL_OPPORTUNITY"
    assert result.classification_label == "Exceptional Opportunity"
    assert len(result.module_contributions) == 2
    assert abs(sum(result.effective_weights.values()) - 1.0) < 1e-9


def test_attractive_opportunity_classification() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(85.0, 82.0))
    assert result.score is not None and result.score >= 80.0
    assert result.classification == "ATTRACTIVE_OPPORTUNITY"
    assert result.classification_label == "Attractive Opportunity"


def test_fairly_valued_classification() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(65.0, 62.0))
    assert result.score == 64.1
    assert result.classification == "FAIRLY_VALUED"
    assert result.classification_label == "Fairly Valued"


def test_overvalued_classification() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(55.0, 52.0))
    assert result.classification == "OVERVALUED"
    assert result.classification_label == "Overvalued"


def test_highly_overvalued_classification() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(40.0, 35.0))
    assert result.classification == "HIGHLY_OVERVALUED"
    assert result.classification_label == "Highly Overvalued"


def test_weighted_score_uses_module_weights() -> None:
    result = aggregate_investment_attractiveness(_full_ia_modules(100.0, 0.0))
    assert result.score == 70.0


def test_skipped_modules_reduce_confidence_and_renormalize() -> None:
    full = aggregate_investment_attractiveness(_full_ia_modules(88.0, 88.0))
    partial = aggregate_investment_attractiveness(
        [
            _module("valuation", score=88.0, confidence=0.90),
            _module("expected_return", status="skipped", score=None, confidence=0.0),
        ]
    )
    assert partial.score == 88.0
    assert "expected_return" in partial.skipped_modules
    assert partial.confidence < full.confidence
    assert set(partial.effective_weights) == {"valuation"}
    assert partial.effective_weights["valuation"] == 1.0


def test_low_confidence_modules_reduce_overall_confidence() -> None:
    high = aggregate_investment_attractiveness(_full_ia_modules(80.0, 80.0))
    low = aggregate_investment_attractiveness(
        [
            _module("valuation", score=80.0, confidence=0.85),
            _module("expected_return", score=80.0, confidence=0.45),
        ]
    )
    assert "expected_return" in low.low_confidence_modules
    assert low.confidence < high.confidence


def test_strengths_weaknesses_opportunities_aggregated() -> None:
    modules = [
        _module(
            "valuation",
            score=90.0,
            findings=[_positive_finding("f-val", confidence=0.95)],
            risks=[_risk("r-val", severity="warning")],
            opportunities=[_opportunity("o-val", confidence=0.90)],
        ),
        _module(
            "expected_return",
            score=85.0,
            findings=[_positive_finding("f-er", confidence=0.80)],
            risks=[_risk("r-er", severity="critical")],
            opportunities=[_opportunity("o-er", confidence=0.75)],
        ),
    ]
    result = aggregate_investment_attractiveness(modules)
    assert len(result.strengths) == 2
    assert result.strengths[0].finding_id == "f-val"
    assert result.weaknesses[0].risk_id == "r-er"
    assert len(result.opportunities) == 2


def test_no_scored_modules_returns_insufficient_data() -> None:
    modules = [
        _module(name, status="skipped", score=None, confidence=0.0)
        for name in INVESTMENT_ATTRACTIVENESS_MODULE_NAMES
    ]
    result = aggregate_investment_attractiveness(modules)
    assert result.score is None
    assert result.classification == "INSUFFICIENT_DATA"
    assert result.confidence == 0.0
    assert len(result.skipped_modules) == 2


def test_ignores_non_investment_attractiveness_modules() -> None:
    modules = _full_ia_modules(80.0, 80.0)
    modules.append(_module("profitability", score=50.0))
    result = aggregate_investment_attractiveness(modules)
    assert result.score == 80.0
    assert "profitability" not in result.effective_weights


def test_deterministic_output() -> None:
    modules = _full_ia_modules(82.0, 78.0)
    first = InvestmentAttractivenessAggregator().aggregate(modules)
    second = InvestmentAttractivenessAggregator().aggregate(modules)
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert first.classification == second.classification
