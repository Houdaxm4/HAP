"""Capital Allocation scoring per docs/SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_acquisition_quality,
    score_dividend_policy,
    score_reinvestment_quality,
    score_roic_trend,
    score_share_buybacks,
    weighted_module_score,
)
from scoring_engine.weights import CAPITAL_ALLOCATION_WEIGHTS


class CapitalAllocationScoreInputs:
    def __init__(
        self,
        *,
        roic_change: float | None = None,
        share_count_cagr: float | None = None,
        buyback_to_fcf: float | None = None,
        payout_to_fcf: float | None = None,
        dividend_cagr: float | None = None,
        reinvestment_rate: float | None = None,
        roic: float | None = None,
        wacc: float | None = None,
        inorganic_share: float | None = None,
        acquisition_intensity: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.roic_change = roic_change
        self.share_count_cagr = share_count_cagr
        self.buyback_to_fcf = buyback_to_fcf
        self.payout_to_fcf = payout_to_fcf
        self.dividend_cagr = dividend_cagr
        self.reinvestment_rate = reinvestment_rate
        self.roic = roic
        self.wacc = wacc
        self.inorganic_share = inorganic_share
        self.acquisition_intensity = acquisition_intensity
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class CapitalAllocationScoreResult:
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


def score_capital_allocation(inputs: CapitalAllocationScoreInputs) -> CapitalAllocationScoreResult:
    """
    Calculate the Capital Allocation Score (0–100).

    Weights (SCORING_SYSTEM.md):
    ROIC Trend 30%, Share Buybacks 20%, Dividend Policy 10%,
    Reinvestment Quality 20%, Acquisition Quality 20%.
    """
    component_raw_scores: dict[str, float | None] = {
        "ROIC_TREND": (
            score_roic_trend(inputs.roic_change) if inputs.roic_change is not None else None
        ),
        "SHARE_BUYBACKS": score_share_buybacks(
            inputs.share_count_cagr,
            inputs.buyback_to_fcf,
        ),
        "DIVIDEND_POLICY": score_dividend_policy(
            inputs.payout_to_fcf,
            inputs.dividend_cagr,
        ),
        "REINVESTMENT_QUALITY": (
            score_reinvestment_quality(
                inputs.reinvestment_rate,
                roic=inputs.roic,
                wacc=inputs.wacc,
            )
            if inputs.reinvestment_rate is not None
            else None
        ),
        "ACQUISITION_QUALITY": score_acquisition_quality(
            inorganic_share=inputs.inorganic_share,
            roic_change=inputs.roic_change,
            acquisition_intensity=inputs.acquisition_intensity,
        ),
    }

    names = {
        "ROIC_TREND": "ROIC Trend",
        "SHARE_BUYBACKS": "Share Buybacks",
        "DIVIDEND_POLICY": "Dividend Policy",
        "REINVESTMENT_QUALITY": "Reinvestment Quality",
        "ACQUISITION_QUALITY": "Acquisition Quality",
    }
    raw_values = {
        "ROIC_TREND": inputs.roic_change,
        "SHARE_BUYBACKS": inputs.share_count_cagr,
        "DIVIDEND_POLICY": inputs.payout_to_fcf,
        "REINVESTMENT_QUALITY": inputs.reinvestment_rate,
        "ACQUISITION_QUALITY": inputs.inorganic_share,
    }

    score, effective = weighted_module_score(component_raw_scores, CAPITAL_ALLOCATION_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in CAPITAL_ALLOCATION_WEIGHTS.items():
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
    base_conf = mean(confidences) if confidences else 0.55
    confidence = clamp_confidence(
        (base_conf or 0.55) * (0.55 + 0.45 * availability) - inputs.confidence_penalty
    )

    return CapitalAllocationScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
