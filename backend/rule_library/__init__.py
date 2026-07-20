"""HAP Rule Library — deterministic findings only (docs/RULE_LIBRARY.md)."""

from rule_library.base import RuleDefinition, RuleHit, RuleSeverity
from rule_library.balance_sheet import BALANCE_SHEET_RULES, evaluate_balance_sheet_rules
from rule_library.business_outlook import BUSINESS_OUTLOOK_RULES, evaluate_business_outlook_rules
from rule_library.capital_allocation import (
    CAPITAL_ALLOCATION_RULES,
    evaluate_capital_allocation_rules,
)
from rule_library.cash_flow import CASH_FLOW_RULES, evaluate_cash_flow_rules
from rule_library.growth import GROWTH_RULES, evaluate_growth_rules
from rule_library.expected_return import EXPECTED_RETURN_RULES, evaluate_expected_return_rules
from rule_library.profitability import (
    PROFITABILITY_RULES,
    evaluate_profitability_rules,
)
from rule_library.valuation import VALUATION_RULES, evaluate_valuation_rules

__all__ = [
    "BALANCE_SHEET_RULES",
    "BUSINESS_OUTLOOK_RULES",
    "CAPITAL_ALLOCATION_RULES",
    "CASH_FLOW_RULES",
    "EXPECTED_RETURN_RULES",
    "GROWTH_RULES",
    "PROFITABILITY_RULES",
    "VALUATION_RULES",
    "RuleDefinition",
    "RuleHit",
    "RuleSeverity",
    "evaluate_balance_sheet_rules",
    "evaluate_business_outlook_rules",
    "evaluate_capital_allocation_rules",
    "evaluate_cash_flow_rules",
    "evaluate_expected_return_rules",
    "evaluate_growth_rules",
    "evaluate_profitability_rules",
    "evaluate_valuation_rules",
]
