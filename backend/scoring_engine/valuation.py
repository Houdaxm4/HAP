"""Enterprise Valuation scoring per ENTERPRISE_VALUATION_MODULE_SPEC.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_dcf_reasonableness,
    score_margin_of_safety,
    score_method_convergence,
    score_multiple_reasonableness,
    score_workbook_alignment,
    weighted_module_score,
)
from scoring_engine.weights import VALUATION_WEIGHTS

VALUATION_CONFIDENCE_CAP = 0.85


class ValuationScoreInputs:
    def __init__(
        self,
        *,
        margin_of_safety: float | None = None,
        terminal_share: float | None = None,
        terminal_growth: float | None = None,
        gdp_growth: float | None = None,
        wacc: float | None = None,
        forecast_years: int | None = None,
        reverse_dcf_unrealistic: bool = False,
        implied_multiple: float | None = None,
        peer_p25: float | None = None,
        peer_median: float | None = None,
        peer_p75: float | None = None,
        historical_median: float | None = None,
        method_spread: float | None = None,
        divergent_count: int = 0,
        comparable_count: int = 0,
        workbook_only_count: int = 0,
        all_within_tolerance: bool = False,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.margin_of_safety = margin_of_safety
        self.terminal_share = terminal_share
        self.terminal_growth = terminal_growth
        self.gdp_growth = gdp_growth
        self.wacc = wacc
        self.forecast_years = forecast_years
        self.reverse_dcf_unrealistic = reverse_dcf_unrealistic
        self.implied_multiple = implied_multiple
        self.peer_p25 = peer_p25
        self.peer_median = peer_median
        self.peer_p75 = peer_p75
        self.historical_median = historical_median
        self.method_spread = method_spread
        self.divergent_count = divergent_count
        self.comparable_count = comparable_count
        self.workbook_only_count = workbook_only_count
        self.all_within_tolerance = all_within_tolerance
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class ValuationScoreResult:
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


def score_valuation(inputs: ValuationScoreInputs) -> ValuationScoreResult:
    component_raw_scores: dict[str, float | None] = {
        "MARGIN_OF_SAFETY": (
            score_margin_of_safety(inputs.margin_of_safety)
            if inputs.margin_of_safety is not None
            else None
        ),
        "DCF_REASONABLENESS": score_dcf_reasonableness(
            terminal_share=inputs.terminal_share,
            terminal_growth=inputs.terminal_growth,
            gdp_growth=inputs.gdp_growth,
            wacc=inputs.wacc,
            forecast_years=inputs.forecast_years,
            reverse_dcf_unrealistic=inputs.reverse_dcf_unrealistic,
        ),
        "MULTIPLE_REASONABLENESS": score_multiple_reasonableness(
            implied_multiple=inputs.implied_multiple,
            peer_p25=inputs.peer_p25,
            peer_median=inputs.peer_median,
            peer_p75=inputs.peer_p75,
            historical_median=inputs.historical_median,
            margin_of_safety=inputs.margin_of_safety,
        ),
        "METHOD_CONVERGENCE": score_method_convergence(inputs.method_spread),
        "WORKBOOK_ALIGNMENT": score_workbook_alignment(
            divergent_count=inputs.divergent_count,
            comparable_count=inputs.comparable_count,
            workbook_only_count=inputs.workbook_only_count,
            all_within_tolerance=inputs.all_within_tolerance,
        ),
    }

    names = {
        "MARGIN_OF_SAFETY": "Margin of Safety",
        "DCF_REASONABLENESS": "DCF Reasonableness",
        "MULTIPLE_REASONABLENESS": "Multiple Reasonableness",
        "METHOD_CONVERGENCE": "Method Convergence",
        "WORKBOOK_ALIGNMENT": "Workbook Alignment",
    }
    raw_values = {
        "MARGIN_OF_SAFETY": inputs.margin_of_safety,
        "DCF_REASONABLENESS": inputs.terminal_share,
        "MULTIPLE_REASONABLENESS": inputs.implied_multiple,
        "METHOD_CONVERGENCE": inputs.method_spread,
        "WORKBOOK_ALIGNMENT": float(inputs.divergent_count),
    }

    score, effective = weighted_module_score(component_raw_scores, VALUATION_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in VALUATION_WEIGHTS.items():
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
    base_conf = min(VALUATION_CONFIDENCE_CAP, mean(confidences) if confidences else 0.60)
    confidence = clamp_confidence(
        min(
            VALUATION_CONFIDENCE_CAP,
            (base_conf or 0.60) * (0.55 + 0.45 * availability) - inputs.confidence_penalty,
        )
    )

    return ValuationScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
