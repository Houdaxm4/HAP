"""Cash Flow scoring per docs/SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_cash_conversion,
    score_fcf_margin,
    score_fcf_stability,
    score_owner_earnings_margin,
    weighted_module_score,
)
from scoring_engine.weights import CASH_FLOW_WEIGHTS


class CashFlowScoreInputs:
    """Raw cash-flow inputs for deterministic scoring."""

    def __init__(
        self,
        *,
        fcf_margin: float | None = None,
        cash_conversion: float | None = None,
        owner_earnings_margin: float | None = None,
        fcf_stability: float | None = None,
        latest_fcf: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.fcf_margin = fcf_margin
        self.cash_conversion = cash_conversion
        self.owner_earnings_margin = owner_earnings_margin
        self.fcf_stability = fcf_stability
        self.latest_fcf = latest_fcf
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class CashFlowScoreResult:
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


def score_cash_flow(inputs: CashFlowScoreInputs) -> CashFlowScoreResult:
    """
    Calculate the Cash Flow Score (0–100).

    Weights (SCORING_SYSTEM.md):
    Free Cash Flow 30%, Cash Conversion 30%, Owner Earnings 20%, FCF Stability 20%.
    """
    component_raw_scores: dict[str, float | None] = {
        "FREE_CASH_FLOW": (
            score_fcf_margin(inputs.fcf_margin, latest_fcf=inputs.latest_fcf)
            if inputs.fcf_margin is not None
            else None
        ),
        "CASH_CONVERSION": (
            score_cash_conversion(inputs.cash_conversion)
            if inputs.cash_conversion is not None
            else None
        ),
        "OWNER_EARNINGS": (
            score_owner_earnings_margin(inputs.owner_earnings_margin)
            if inputs.owner_earnings_margin is not None
            else None
        ),
        "FCF_STABILITY": (
            score_fcf_stability(inputs.fcf_stability)
            if inputs.fcf_stability is not None
            else None
        ),
    }

    names = {
        "FREE_CASH_FLOW": "Free Cash Flow",
        "CASH_CONVERSION": "Cash Conversion",
        "OWNER_EARNINGS": "Owner Earnings",
        "FCF_STABILITY": "FCF Stability",
    }
    raw_values = {
        "FREE_CASH_FLOW": inputs.fcf_margin,
        "CASH_CONVERSION": inputs.cash_conversion,
        "OWNER_EARNINGS": inputs.owner_earnings_margin,
        "FCF_STABILITY": inputs.fcf_stability,
    }

    score, effective = weighted_module_score(component_raw_scores, CASH_FLOW_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in CASH_FLOW_WEIGHTS.items():
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
    base_conf = mean(confidences) if confidences else 0.6
    confidence = clamp_confidence(
        (base_conf or 0.6) * (0.55 + 0.45 * availability) - inputs.confidence_penalty
    )

    return CashFlowScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
