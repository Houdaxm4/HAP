"""Financial analysis modules — one concern per module."""

from analysis_engine.modules.balance_sheet import BalanceSheetModule
from analysis_engine.modules.business_outlook import BusinessOutlookModule
from analysis_engine.modules.capital_allocation import CapitalAllocationModule
from analysis_engine.modules.cash_flow import CashFlowModule
from analysis_engine.modules.expected_return import ExpectedReturnModule
from analysis_engine.modules.growth import GrowthModule
from analysis_engine.modules.margins import MarginsModule
from analysis_engine.modules.profitability import ProfitabilityModule
from analysis_engine.modules.recommendation import RecommendationModule
from analysis_engine.modules.valuation import ValuationModule

DEFAULT_MODULES = (
    ProfitabilityModule,
    MarginsModule,
    GrowthModule,
    CashFlowModule,
    BalanceSheetModule,
    CapitalAllocationModule,
    BusinessOutlookModule,
    ValuationModule,
    ExpectedReturnModule,
    RecommendationModule,
)

__all__ = [
    "BalanceSheetModule",
    "BusinessOutlookModule",
    "CapitalAllocationModule",
    "CashFlowModule",
    "DEFAULT_MODULES",
    "ExpectedReturnModule",
    "GrowthModule",
    "MarginsModule",
    "ProfitabilityModule",
    "RecommendationModule",
    "ValuationModule",
]
