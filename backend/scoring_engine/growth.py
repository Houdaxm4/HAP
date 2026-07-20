"""Growth scoring per docs/SCORING_SYSTEM.md and GROWTH_MODULE_SPEC.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_eps_cagr,
    score_fcf_cagr,
    score_growth_stability,
    score_organic_growth,
    score_revenue_cagr,
    weighted_module_score,
)
from scoring_engine.weights import GROWTH_WEIGHTS


class GrowthScoreInputs:
    """Raw growth inputs for deterministic scoring."""

    def __init__(
        self,
        *,
        revenue_cagr: float | None = None,
        eps_cagr: float | None = None,
        fcf_cagr: float | None = None,
        growth_stability: float | None = None,
        organic_cagr: float | None = None,
        inorganic_rev_share: float | None = None,
        latest_fcf: float | None = None,
        organic_data_available: bool = False,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.revenue_cagr = revenue_cagr
        self.eps_cagr = eps_cagr
        self.fcf_cagr = fcf_cagr
        self.growth_stability = growth_stability
        self.organic_cagr = organic_cagr
        self.inorganic_rev_share = inorganic_rev_share
        self.latest_fcf = latest_fcf
        self.organic_data_available = organic_data_available
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class GrowthScoreResult:
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


def score_growth(inputs: GrowthScoreInputs) -> GrowthScoreResult:
    """
    Calculate the Growth Score (0–100).

    Weights (SCORING_SYSTEM.md / GROWTH_MODULE_SPEC.md):
    Revenue CAGR 30%, EPS CAGR 25%, FCF CAGR 25%,
    Growth Stability 10%, Organic Growth 10%.
    """
    organic_raw = inputs.organic_cagr
    if organic_raw is None and inputs.revenue_cagr is not None:
        # No organic overlay: fall back to reported revenue CAGR with confidence penalty.
        organic_raw = inputs.revenue_cagr

    component_raw_scores: dict[str, float | None] = {
        "REVENUE_CAGR": (
            score_revenue_cagr(inputs.revenue_cagr) if inputs.revenue_cagr is not None else None
        ),
        "EPS_CAGR": score_eps_cagr(inputs.eps_cagr) if inputs.eps_cagr is not None else None,
        "FCF_CAGR": (
            score_fcf_cagr(
                inputs.fcf_cagr,
                latest_fcf=inputs.latest_fcf,
                revenue_cagr=inputs.revenue_cagr,
            )
            if inputs.fcf_cagr is not None
            else None
        ),
        "GROWTH_STABILITY": (
            score_growth_stability(inputs.growth_stability)
            if inputs.growth_stability is not None
            else None
        ),
        "ORGANIC_GROWTH": (
            score_organic_growth(
                organic_raw,
                inorganic_rev_share=(
                    inputs.inorganic_rev_share if inputs.organic_data_available else None
                ),
            )
            if organic_raw is not None
            else None
        ),
    }

    names = {
        "REVENUE_CAGR": "Revenue CAGR",
        "EPS_CAGR": "EPS CAGR",
        "FCF_CAGR": "FCF CAGR",
        "GROWTH_STABILITY": "Growth Stability",
        "ORGANIC_GROWTH": "Organic Growth",
    }
    raw_values = {
        "REVENUE_CAGR": inputs.revenue_cagr,
        "EPS_CAGR": inputs.eps_cagr,
        "FCF_CAGR": inputs.fcf_cagr,
        "GROWTH_STABILITY": inputs.growth_stability,
        "ORGANIC_GROWTH": organic_raw,
    }

    score, effective = weighted_module_score(component_raw_scores, GROWTH_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in GROWTH_WEIGHTS.items():
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
    if not inputs.organic_data_available and component_raw_scores["ORGANIC_GROWTH"] is not None:
        confidence = clamp_confidence(confidence - 0.08)

    return GrowthScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
