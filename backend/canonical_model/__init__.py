"""Canonical Financial Model layer for HAP.

Converts validated workbook cell data into structured historical statement
series. The analysis engine consumes only ``CompanyFinancialModel`` objects.
"""

from canonical_model.builder import CompanyFinancialModelBuilder, build_company_financial_model
from canonical_model.company import CompanyFinancialModel, MarketData, ValuationInputs
from canonical_model.primitives import (
    FinancialPoint,
    FinancialSeries,
    LineItemProvenance,
    PeriodAmount,
)
from canonical_model.statements import BalanceSheet, CashFlowStatement, IncomeStatement
from canonical_model.workbook_metrics import WorkbookMetric, WorkbookMetricCatalog

__all__ = [
    "BalanceSheet",
    "CashFlowStatement",
    "CompanyFinancialModel",
    "CompanyFinancialModelBuilder",
    "FinancialPoint",
    "FinancialSeries",
    "IncomeStatement",
    "LineItemProvenance",
    "MarketData",
    "PeriodAmount",
    "ValuationInputs",
    "WorkbookMetric",
    "WorkbookMetricCatalog",
    "build_company_financial_model",
]
