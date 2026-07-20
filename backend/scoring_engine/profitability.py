"""Profitability scoring per docs/SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_margin_stability,
    score_net_margin,
    score_operating_margin,
    score_roa,
    score_roe,
    score_roic,
    weighted_module_score,
)
from scoring_engine.weights import PROFITABILITY_WEIGHTS


class ProfitabilityScoreInputs:
    """Raw profitability inputs for deterministic scoring."""

    def __init__(
        self,
        *,
        roic: float | None = None,
        operating_margin: float | None = None,
        net_margin: float | None = None,
        roe: float | None = None,
        roa: float | None = None,
        margin_stability: float | None = None,
        wacc: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
    ) -> None:
        self.roic = roic
        self.operating_margin = operating_margin
        self.net_margin = net_margin
        self.roe = roe
        self.roa = roa
        self.margin_stability = margin_stability
        self.wacc = wacc
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}


class ProfitabilityScoreResult:
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


def score_profitability(inputs: ProfitabilityScoreInputs) -> ProfitabilityScoreResult:
    """
    Calculate the Profitability Score (0–100).

    Weights (SCORING_SYSTEM.md):
    ROIC 40%, Operating Margin 20%, Net Margin 15%,
    ROE 10%, ROA 5%, Margin Stability 10%.
    """
    component_raw_scores: dict[str, float | None] = {
        "ROIC": score_roic(inputs.roic, inputs.wacc) if inputs.roic is not None else None,
        "OPERATING_MARGIN": (
            score_operating_margin(inputs.operating_margin)
            if inputs.operating_margin is not None
            else None
        ),
        "NET_MARGIN": (
            score_net_margin(inputs.net_margin) if inputs.net_margin is not None else None
        ),
        "ROE": score_roe(inputs.roe) if inputs.roe is not None else None,
        "ROA": score_roa(inputs.roa) if inputs.roa is not None else None,
        "MARGIN_STABILITY": (
            score_margin_stability(inputs.margin_stability)
            if inputs.margin_stability is not None
            else None
        ),
    }

    names = {
        "ROIC": "ROIC",
        "OPERATING_MARGIN": "Operating Margin",
        "NET_MARGIN": "Net Margin",
        "ROE": "ROE",
        "ROA": "ROA",
        "MARGIN_STABILITY": "Margin Stability",
    }
    raw_values = {
        "ROIC": inputs.roic,
        "OPERATING_MARGIN": inputs.operating_margin,
        "NET_MARGIN": inputs.net_margin,
        "ROE": inputs.roe,
        "ROA": inputs.roa,
        "MARGIN_STABILITY": inputs.margin_stability,
    }

    score, effective = weighted_module_score(component_raw_scores, PROFITABILITY_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in PROFITABILITY_WEIGHTS.items():
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
    # Missing components reduce confidence (SCORING_SYSTEM / FINANCIAL_ANALYSIS_SPEC).
    availability = sum(1 for value in component_raw_scores.values() if value is not None) / len(
        component_raw_scores
    )
    base_conf = mean(confidences) if confidences else 0.6
    confidence = clamp_confidence((base_conf or 0.6) * (0.55 + 0.45 * availability))

    return ProfitabilityScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
