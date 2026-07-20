"""Expected Return scoring per SCORING_SYSTEM.md and HAP methodology."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_expected_cagr_level,
    score_return_contribution,
    score_valuation_reversion_contribution,
    weighted_module_score,
)
from scoring_engine.weights import EXPECTED_RETURN_WEIGHTS

EXPECTED_RETURN_CONFIDENCE_CAP = 0.85


class ExpectedReturnScoreInputs:
    def __init__(
        self,
        *,
        growth_contribution: float | None = None,
        dividend_yield: float | None = None,
        buyback_yield: float | None = None,
        valuation_reversion: float | None = None,
        multiple_expansion: float | None = None,
        expected_cagr: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.growth_contribution = growth_contribution
        self.dividend_yield = dividend_yield
        self.buyback_yield = buyback_yield
        self.valuation_reversion = valuation_reversion
        self.multiple_expansion = multiple_expansion
        self.expected_cagr = expected_cagr
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class ExpectedReturnScoreResult:
    def __init__(
        self,
        *,
        score: float | None,
        confidence: float,
        components: list[ComponentScore],
        effective_weights: dict[str, float],
    ) -> None:
        self.score = score
        self.confidence = confidence
        self.components = components
        self.effective_weights = effective_weights


def score_expected_return(inputs: ExpectedReturnScoreInputs) -> ExpectedReturnScoreResult:
    component_raw_scores: dict[str, float | None] = {
        "GROWTH_CONTRIBUTION": score_return_contribution(inputs.growth_contribution),
        "DIVIDEND_YIELD": score_return_contribution(inputs.dividend_yield),
        "BUYBACK_YIELD": score_return_contribution(inputs.buyback_yield),
        "VALUATION_REVERSION": score_valuation_reversion_contribution(inputs.valuation_reversion),
        "MULTIPLE_EXPANSION": score_return_contribution(inputs.multiple_expansion),
        "EXPECTED_CAGR_LEVEL": score_expected_cagr_level(inputs.expected_cagr),
    }

    names = {
        "GROWTH_CONTRIBUTION": "Growth Contribution",
        "DIVIDEND_YIELD": "Dividend Yield",
        "BUYBACK_YIELD": "Buyback Yield",
        "VALUATION_REVERSION": "Valuation Reversion",
        "MULTIPLE_EXPANSION": "Multiple Expansion",
        "EXPECTED_CAGR_LEVEL": "Expected CAGR",
    }
    raw_values = {
        "GROWTH_CONTRIBUTION": inputs.growth_contribution,
        "DIVIDEND_YIELD": inputs.dividend_yield,
        "BUYBACK_YIELD": inputs.buyback_yield,
        "VALUATION_REVERSION": inputs.valuation_reversion,
        "MULTIPLE_EXPANSION": inputs.multiple_expansion,
        "EXPECTED_CAGR_LEVEL": inputs.expected_cagr,
    }

    score, effective = weighted_module_score(component_raw_scores, EXPECTED_RETURN_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in EXPECTED_RETURN_WEIGHTS.items():
        components.append(
            ComponentScore(
                code=code,
                name=names[code],
                weight=effective.get(code, weight),
                raw_value=raw_values[code],
                score=component_raw_scores[code],
                available=component_raw_scores[code] is not None,
                evidence=list(inputs.evidence.get(code, [])),
            )
        )

    confidences = [
        inputs.input_confidence[code]
        for code, value in component_raw_scores.items()
        if value is not None and code in inputs.input_confidence
    ]
    availability = sum(1 for value in component_raw_scores.values() if value is not None) / len(
        component_raw_scores
    )
    base_conf = min(EXPECTED_RETURN_CONFIDENCE_CAP, mean(confidences) if confidences else 0.60)
    confidence = clamp_confidence(
        min(
            EXPECTED_RETURN_CONFIDENCE_CAP,
            (base_conf or 0.60) * (0.55 + 0.45 * availability) - inputs.confidence_penalty,
        )
    )

    return ExpectedReturnScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
