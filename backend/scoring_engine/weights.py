"""Business Quality / Profitability weights from docs/SCORING_SYSTEM.md."""

from __future__ import annotations

# Profitability Score component weights (must sum to 1.0).
PROFITABILITY_WEIGHTS: dict[str, float] = {
    "ROIC": 0.40,
    "OPERATING_MARGIN": 0.20,
    "NET_MARGIN": 0.15,
    "ROE": 0.10,
    "ROA": 0.05,
    "MARGIN_STABILITY": 0.10,
}

# Growth Score component weights from SCORING_SYSTEM.md / GROWTH_MODULE_SPEC.md.
GROWTH_WEIGHTS: dict[str, float] = {
    "REVENUE_CAGR": 0.30,
    "EPS_CAGR": 0.25,
    "FCF_CAGR": 0.25,
    "GROWTH_STABILITY": 0.10,
    "ORGANIC_GROWTH": 0.10,
}

# Cash Flow Score component weights from SCORING_SYSTEM.md.
CASH_FLOW_WEIGHTS: dict[str, float] = {
    "FREE_CASH_FLOW": 0.30,
    "CASH_CONVERSION": 0.30,
    "OWNER_EARNINGS": 0.20,
    "FCF_STABILITY": 0.20,
}

# Balance Sheet Score component weights from SCORING_SYSTEM.md.
BALANCE_SHEET_WEIGHTS: dict[str, float] = {
    "DEBT": 0.35,
    "LIQUIDITY": 0.25,
    "INTEREST_COVERAGE": 0.20,
    "NET_CASH_POSITION": 0.10,
    "WORKING_CAPITAL": 0.10,
}

# Capital Allocation Score component weights from SCORING_SYSTEM.md.
CAPITAL_ALLOCATION_WEIGHTS: dict[str, float] = {
    "ROIC_TREND": 0.30,
    "SHARE_BUYBACKS": 0.20,
    "DIVIDEND_POLICY": 0.10,
    "REINVESTMENT_QUALITY": 0.20,
    "ACQUISITION_QUALITY": 0.20,
}

# Business Outlook Score component weights (SCORING_SYSTEM.md — future prospects).
BUSINESS_OUTLOOK_WEIGHTS: dict[str, float] = {
    "INDUSTRY_TRENDS": 0.20,
    "COMPETITIVE_POSITION": 0.25,
    "MANAGEMENT_GUIDANCE": 0.20,
    "MARKET_OPPORTUNITIES": 0.20,
    "STRUCTURAL_RISK": 0.15,
}

# Business Quality roll-up weights (for later Investment Intelligence Engine).
BUSINESS_QUALITY_WEIGHTS: dict[str, float] = {
    "profitability": 0.25,
    "growth": 0.15,
    "cash_flow": 0.20,
    "balance_sheet": 0.15,
    "capital_allocation": 0.15,
    "business_outlook": 0.10,
}

INVESTMENT_ATTRACTIVENESS_WEIGHTS: dict[str, float] = {
    "intrinsic_value": 0.35,
    "expected_return": 0.30,
    "margin_of_safety": 0.20,
    "relative_valuation": 0.15,
}

# Module roll-up weights for Investment Attractiveness aggregator (valuation + expected return).
# Maps SCORING_SYSTEM.md conceptual weights: valuation 70% (35+20+15), expected return 30%.
INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS: dict[str, float] = {
    "valuation": 0.70,
    "expected_return": 0.30,
}

assert abs(sum(INVESTMENT_ATTRACTIVENESS_MODULE_WEIGHTS.values()) - 1.0) < 1e-9

# Enterprise Valuation Score component weights (ENTERPRISE_VALUATION_MODULE_SPEC.md).
VALUATION_WEIGHTS: dict[str, float] = {
    "MARGIN_OF_SAFETY": 0.35,
    "DCF_REASONABLENESS": 0.25,
    "MULTIPLE_REASONABLENESS": 0.20,
    "METHOD_CONVERGENCE": 0.10,
    "WORKBOOK_ALIGNMENT": 0.10,
}

# Expected Return Score component weights (SCORING_SYSTEM.md + HAP methodology).
EXPECTED_RETURN_WEIGHTS: dict[str, float] = {
    "VALUATION_REVERSION": 0.30,
    "GROWTH_CONTRIBUTION": 0.25,
    "DIVIDEND_YIELD": 0.15,
    "BUYBACK_YIELD": 0.15,
    "MULTIPLE_EXPANSION": 0.10,
    "EXPECTED_CAGR_LEVEL": 0.05,
}

assert abs(sum(PROFITABILITY_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(GROWTH_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(CASH_FLOW_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(BALANCE_SHEET_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(CAPITAL_ALLOCATION_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(BUSINESS_OUTLOOK_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(BUSINESS_QUALITY_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(VALUATION_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(EXPECTED_RETURN_WEIGHTS.values()) - 1.0) < 1e-9
assert abs(sum(INVESTMENT_ATTRACTIVENESS_WEIGHTS.values()) - 1.0) < 1e-9
