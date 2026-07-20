"""Balance Sheet scoring per docs/SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine.schemas import ComponentScore, Evidence
from analysis_engine.utils import clamp_confidence, mean
from scoring_engine.components import (
    score_debt_leverage,
    score_interest_coverage,
    score_liquidity,
    score_net_cash_position,
    score_working_capital_trend,
    weighted_module_score,
)
from scoring_engine.weights import BALANCE_SHEET_WEIGHTS


class BalanceSheetScoreInputs:
    def __init__(
        self,
        *,
        debt_to_ebitda: float | None = None,
        current_ratio: float | None = None,
        interest_coverage: float | None = None,
        net_debt: float | None = None,
        ebitda: float | None = None,
        working_capital_trend: float | None = None,
        period: str | None = None,
        evidence: dict[str, list[Evidence]] | None = None,
        input_confidence: dict[str, float] | None = None,
        confidence_penalty: float = 0.0,
    ) -> None:
        self.debt_to_ebitda = debt_to_ebitda
        self.current_ratio = current_ratio
        self.interest_coverage = interest_coverage
        self.net_debt = net_debt
        self.ebitda = ebitda
        self.working_capital_trend = working_capital_trend
        self.period = period
        self.evidence = evidence or {}
        self.input_confidence = input_confidence or {}
        self.confidence_penalty = confidence_penalty


class BalanceSheetScoreResult:
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


def score_balance_sheet(inputs: BalanceSheetScoreInputs) -> BalanceSheetScoreResult:
    """
    Calculate the Balance Sheet Score (0–100).

    Weights (SCORING_SYSTEM.md):
    Debt 35%, Liquidity 25%, Interest Coverage 20%, Net Cash Position 10%, Working Capital 10%.
    """
    net_cash_score = None
    if inputs.net_debt is not None:
        net_cash_score = score_net_cash_position(
            inputs.net_debt,
            ebitda=inputs.ebitda,
        )

    component_raw_scores: dict[str, float | None] = {
        "DEBT": (
            score_debt_leverage(inputs.debt_to_ebitda)
            if inputs.debt_to_ebitda is not None
            else None
        ),
        "LIQUIDITY": (
            score_liquidity(inputs.current_ratio) if inputs.current_ratio is not None else None
        ),
        "INTEREST_COVERAGE": (
            score_interest_coverage(inputs.interest_coverage)
            if inputs.interest_coverage is not None
            else None
        ),
        "NET_CASH_POSITION": net_cash_score,
        "WORKING_CAPITAL": (
            score_working_capital_trend(inputs.working_capital_trend)
            if inputs.working_capital_trend is not None
            else None
        ),
    }

    names = {
        "DEBT": "Debt",
        "LIQUIDITY": "Liquidity",
        "INTEREST_COVERAGE": "Interest Coverage",
        "NET_CASH_POSITION": "Net Cash Position",
        "WORKING_CAPITAL": "Working Capital",
    }
    raw_values = {
        "DEBT": inputs.debt_to_ebitda,
        "LIQUIDITY": inputs.current_ratio,
        "INTEREST_COVERAGE": inputs.interest_coverage,
        "NET_CASH_POSITION": inputs.net_debt,
        "WORKING_CAPITAL": inputs.working_capital_trend,
    }

    score, effective = weighted_module_score(component_raw_scores, BALANCE_SHEET_WEIGHTS)

    components: list[ComponentScore] = []
    for code, weight in BALANCE_SHEET_WEIGHTS.items():
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

    return BalanceSheetScoreResult(
        score=score,
        confidence=confidence,
        components=components,
        effective_weights=effective,
    )
