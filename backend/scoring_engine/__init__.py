"""HAP Scoring Engine — deterministic scores from structured metrics.

Implements docs/SCORING_SYSTEM.md. Scores never rely on LLM judgment.
"""

from scoring_engine.balance_sheet import (
    BalanceSheetScoreInputs,
    BalanceSheetScoreResult,
    score_balance_sheet,
)
from scoring_engine.business_outlook import (
    BusinessOutlookScoreInputs,
    BusinessOutlookScoreResult,
    score_business_outlook,
)
from scoring_engine.capital_allocation import (
    CapitalAllocationScoreInputs,
    CapitalAllocationScoreResult,
    score_capital_allocation,
)
from scoring_engine.cash_flow import CashFlowScoreInputs, CashFlowScoreResult, score_cash_flow
from scoring_engine.growth import GrowthScoreInputs, GrowthScoreResult, score_growth
from scoring_engine.expected_return import (
    EXPECTED_RETURN_CONFIDENCE_CAP,
    ExpectedReturnScoreInputs,
    ExpectedReturnScoreResult,
    score_expected_return,
)
from scoring_engine.profitability import (
    ProfitabilityScoreInputs,
    ProfitabilityScoreResult,
    score_profitability,
)
from scoring_engine.valuation import (
    VALUATION_CONFIDENCE_CAP,
    ValuationScoreInputs,
    ValuationScoreResult,
    score_valuation,
)
from scoring_engine.weights import (
    BALANCE_SHEET_WEIGHTS,
    BUSINESS_OUTLOOK_WEIGHTS,
    BUSINESS_QUALITY_WEIGHTS,
    CAPITAL_ALLOCATION_WEIGHTS,
    CASH_FLOW_WEIGHTS,
    EXPECTED_RETURN_WEIGHTS,
    GROWTH_WEIGHTS,
    INVESTMENT_ATTRACTIVENESS_WEIGHTS,
    PROFITABILITY_WEIGHTS,
    VALUATION_WEIGHTS,
)

__all__ = [
    "BALANCE_SHEET_WEIGHTS",
    "BUSINESS_OUTLOOK_WEIGHTS",
    "BUSINESS_QUALITY_WEIGHTS",
    "CAPITAL_ALLOCATION_WEIGHTS",
    "CASH_FLOW_WEIGHTS",
    "EXPECTED_RETURN_WEIGHTS",
    "GROWTH_WEIGHTS",
    "INVESTMENT_ATTRACTIVENESS_WEIGHTS",
    "PROFITABILITY_WEIGHTS",
    "VALUATION_WEIGHTS",
    "BalanceSheetScoreInputs",
    "BalanceSheetScoreResult",
    "BusinessOutlookScoreInputs",
    "BusinessOutlookScoreResult",
    "CapitalAllocationScoreInputs",
    "CapitalAllocationScoreResult",
    "CashFlowScoreInputs",
    "CashFlowScoreResult",
    "EXPECTED_RETURN_CONFIDENCE_CAP",
    "ExpectedReturnScoreInputs",
    "ExpectedReturnScoreResult",
    "GrowthScoreInputs",
    "GrowthScoreResult",
    "ProfitabilityScoreInputs",
    "ProfitabilityScoreResult",
    "ValuationScoreInputs",
    "ValuationScoreResult",
    "VALUATION_CONFIDENCE_CAP",
    "score_balance_sheet",
    "score_business_outlook",
    "score_capital_allocation",
    "score_cash_flow",
    "score_expected_return",
    "score_growth",
    "score_profitability",
    "score_valuation",
]
