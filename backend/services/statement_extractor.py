"""
Financial Statement Extractor.

Extracts only:
  - Balance Sheet
  - Income Statement
  - Cash Flow

No ratios. No analysis. No valuation metrics.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from models.statements import (
    ExtractStatementsRequest,
    FinancialStatement,
    FinancialStatementsResult,
    StatementLineItem,
    StatementType,
    StatementValue,
)
from services.sec_service import SecService, SecServiceError

# Canonical statement line items → preferred US-GAAP XBRL tags (ordered).
# Keep this list to primary statement concepts only — no ratios.

INCOME_STATEMENT_LINES: list[tuple[str, str, str, list[str]]] = [
    # concept_key, label, section, tags
    ("revenue", "Revenue", "operations", [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ]),
    ("cost_of_revenue", "Cost of Revenue", "operations", [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
    ]),
    ("gross_profit", "Gross Profit", "operations", ["GrossProfit"]),
    ("research_and_development", "Research and Development", "operating_expenses", [
        "ResearchAndDevelopmentExpense",
    ]),
    ("selling_general_administrative", "Selling, General and Administrative", "operating_expenses", [
        "SellingGeneralAndAdministrativeExpense",
    ]),
    ("operating_expenses", "Operating Expenses", "operating_expenses", [
        "OperatingExpenses",
        "CostsAndExpenses",
    ]),
    ("operating_income", "Operating Income", "operations", ["OperatingIncomeLoss"]),
    ("interest_expense", "Interest Expense", "other", [
        "InterestExpense",
        "InterestExpenseDebt",
    ]),
    ("interest_income", "Interest Income", "other", [
        "InvestmentIncomeInterest",
        "InterestAndDividendIncomeOperating",
    ]),
    ("income_before_tax", "Income Before Tax", "operations", [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ]),
    ("income_tax_expense", "Income Tax Expense", "operations", [
        "IncomeTaxExpenseBenefit",
    ]),
    ("net_income", "Net Income", "operations", [
        "NetIncomeLoss",
        "ProfitLoss",
    ]),
    ("net_income_to_common", "Net Income Attributable to Common", "operations", [
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ]),
    ("eps_basic", "EPS (Basic)", "per_share", ["EarningsPerShareBasic"]),
    ("eps_diluted", "EPS (Diluted)", "per_share", ["EarningsPerShareDiluted"]),
    ("weighted_average_shares_basic", "Weighted Average Shares (Basic)", "per_share", [
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ]),
    ("weighted_average_shares_diluted", "Weighted Average Shares (Diluted)", "per_share", [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ]),
]

BALANCE_SHEET_LINES: list[tuple[str, str, str, list[str]]] = [
    ("cash", "Cash and Cash Equivalents", "current_assets", [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
    ]),
    ("short_term_investments", "Short-term Investments", "current_assets", [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ]),
    ("accounts_receivable", "Accounts Receivable", "current_assets", [
        "AccountsReceivableNetCurrent",
        "AccountsReceivableNet",
    ]),
    ("inventory", "Inventory", "current_assets", [
        "InventoryNet",
    ]),
    ("other_current_assets", "Other Current Assets", "current_assets", [
        "OtherAssetsCurrent",
    ]),
    ("total_current_assets", "Total Current Assets", "current_assets", [
        "AssetsCurrent",
    ]),
    ("ppe_net", "Property, Plant and Equipment (Net)", "noncurrent_assets", [
        "PropertyPlantAndEquipmentNet",
    ]),
    ("goodwill", "Goodwill", "noncurrent_assets", ["Goodwill"]),
    ("intangible_assets", "Intangible Assets", "noncurrent_assets", [
        "IntangibleAssetsNetExcludingGoodwill",
    ]),
    ("other_noncurrent_assets", "Other Noncurrent Assets", "noncurrent_assets", [
        "OtherAssetsNoncurrent",
    ]),
    ("total_assets", "Total Assets", "assets", ["Assets"]),
    ("accounts_payable", "Accounts Payable", "current_liabilities", [
        "AccountsPayableCurrent",
    ]),
    ("short_term_debt", "Short-term Debt", "current_liabilities", [
        "ShortTermBorrowings",
        "LongTermDebtCurrent",
        "DebtCurrent",
    ]),
    ("accrued_liabilities", "Accrued Liabilities", "current_liabilities", [
        "AccruedLiabilitiesCurrent",
        "OtherLiabilitiesCurrent",
    ]),
    ("total_current_liabilities", "Total Current Liabilities", "current_liabilities", [
        "LiabilitiesCurrent",
    ]),
    ("long_term_debt", "Long-term Debt", "noncurrent_liabilities", [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ]),
    ("other_noncurrent_liabilities", "Other Noncurrent Liabilities", "noncurrent_liabilities", [
        "OtherLiabilitiesNoncurrent",
    ]),
    ("total_liabilities", "Total Liabilities", "liabilities", ["Liabilities"]),
    ("common_stock", "Common Stock", "equity", [
        "CommonStockValue",
        "CommonStocksIncludingAdditionalPaidInCapital",
    ]),
    ("retained_earnings", "Retained Earnings", "equity", [
        "RetainedEarningsAccumulatedDeficit",
    ]),
    ("stockholders_equity", "Stockholders' Equity", "equity", [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ]),
    ("total_liabilities_and_equity", "Total Liabilities and Equity", "equity", [
        "LiabilitiesAndStockholdersEquity",
    ]),
]

CASH_FLOW_LINES: list[tuple[str, str, str, list[str]]] = [
    ("net_income", "Net Income", "operating", [
        "NetIncomeLoss",
        "ProfitLoss",
    ]),
    ("depreciation_amortization", "Depreciation and Amortization", "operating", [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ]),
    ("stock_based_compensation", "Stock-Based Compensation", "operating", [
        "ShareBasedCompensation",
    ]),
    ("change_in_working_capital", "Changes in Working Capital", "operating", [
        "IncreaseDecreaseInOperatingCapital",
    ]),
    ("operating_cash_flow", "Cash from Operations", "operating", [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ]),
    ("capex", "Capital Expenditures", "investing", [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ]),
    ("acquisitions", "Acquisitions", "investing", [
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "PaymentsToAcquireBusinessesAndInterestInAffiliates",
    ]),
    ("investing_cash_flow", "Cash from Investing", "investing", [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ]),
    ("dividends", "Dividends Paid", "financing", [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ]),
    ("share_repurchases", "Share Repurchases", "financing", [
        "PaymentsForRepurchaseOfCommonStock",
    ]),
    ("debt_issuance", "Debt Issuance", "financing", [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
    ]),
    ("debt_repayment", "Debt Repayment", "financing", [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
    ]),
    ("financing_cash_flow", "Cash from Financing", "financing", [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ]),
    ("net_change_in_cash", "Net Change in Cash", "summary", [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
    ]),
]

STATEMENT_DEFINITIONS: dict[StatementType, tuple[str, list[tuple[str, str, str, list[str]]]]] = {
    "income_statement": ("Income Statement", INCOME_STATEMENT_LINES),
    "balance_sheet": ("Balance Sheet", BALANCE_SHEET_LINES),
    "cash_flow": ("Cash Flow Statement", CASH_FLOW_LINES),
}


class StatementExtractorError(Exception):
    """Raised when financial statement extraction fails."""


class FinancialStatementExtractor:
    """
    Extract Balance Sheet, Income Statement, and Cash Flow from SEC company facts.

    Does not compute ratios or produce analysis.
    """

    def __init__(
        self,
        sec_service: SecService | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.sec_service = sec_service or SecService(cache_dir=cache_dir)

    def extract(self, request: ExtractStatementsRequest) -> FinancialStatementsResult:
        ticker = request.ticker.strip().upper()
        try:
            cik = self.sec_service.resolve_cik(ticker)
            company_facts = self.sec_service.fetch_company_facts(cik)
        except SecServiceError as exc:
            raise StatementExtractorError(str(exc)) from exc

        company_name = company_facts.get("entityName")
        annual_periods, quarterly_periods = self._select_periods(
            company_facts,
            max_annual=request.max_annual_periods,
            max_quarterly=request.max_quarterly_periods if request.include_quarters else 0,
        )
        target_periods = annual_periods + quarterly_periods

        balance_sheet = self._build_statement(
            "balance_sheet",
            company_facts,
            target_periods,
        )
        income_statement = self._build_statement(
            "income_statement",
            company_facts,
            target_periods,
        )
        cash_flow = self._build_statement(
            "cash_flow",
            company_facts,
            target_periods,
        )

        return FinancialStatementsResult(
            extraction_id=str(uuid.uuid4()),
            ticker=ticker,
            cik=cik,
            company_name=company_name,
            source="sec_company_facts",
            balance_sheet=balance_sheet,
            income_statement=income_statement,
            cash_flow=cash_flow,
            annual_periods=annual_periods,
            quarterly_periods=quarterly_periods,
            extracted_at=utc_now_iso(),
            message=(
                "Extracted Balance Sheet, Income Statement, and Cash Flow only. "
                "No ratios or analysis performed."
            ),
        )

    def _build_statement(
        self,
        statement_type: StatementType,
        company_facts: dict[str, Any],
        target_periods: list[str],
    ) -> FinancialStatement:
        title, definitions = STATEMENT_DEFINITIONS[statement_type]
        line_items: list[StatementLineItem] = []
        populated = 0
        used_periods: set[str] = set()

        for concept, label, section, tags in definitions:
            tag, taxonomy, values = self._extract_line_values(
                company_facts,
                tags,
                target_periods,
            )
            if tag is None:
                line_items.append(
                    StatementLineItem(
                        concept=concept,
                        label=label,
                        xbrl_tag=tags[0],
                        taxonomy="us-gaap",
                        section=section,
                        values=[],
                    )
                )
                continue

            populated += sum(1 for item in values if item.value is not None)
            used_periods.update(item.period for item in values)
            line_items.append(
                StatementLineItem(
                    concept=concept,
                    label=label,
                    xbrl_tag=tag,
                    taxonomy=taxonomy,
                    section=section,
                    values=values,
                )
            )

        ordered_periods = [period for period in target_periods if period in used_periods]
        return FinancialStatement(
            statement_type=statement_type,
            title=title,
            periods=ordered_periods,
            line_items=line_items,
            line_item_count=len(line_items),
            populated_value_count=populated,
        )

    def _extract_line_values(
        self,
        company_facts: dict[str, Any],
        tags: list[str],
        target_periods: list[str],
    ) -> tuple[str | None, str, list[StatementValue]]:
        facts = company_facts.get("facts", {})
        target_set = set(target_periods)

        for taxonomy in ("us-gaap", "ifrs-full", "dei"):
            taxonomy_facts = facts.get(taxonomy, {})
            for tag in tags:
                payload = taxonomy_facts.get(tag)
                if not payload:
                    continue
                values_by_period: dict[str, StatementValue] = {}
                for unit, entries in (payload.get("units") or {}).items():
                    for entry in entries:
                        period_key = self._period_key(entry)
                        if period_key is None or period_key not in target_set:
                            continue
                        if entry.get("val") is None:
                            continue
                        candidate = StatementValue(
                            period=period_key,
                            fiscal_year=entry.get("fy"),
                            fiscal_period=entry.get("fp"),
                            value=float(entry["val"]),
                            unit=unit,
                            form=entry.get("form"),
                            filed=entry.get("filed"),
                            accession_number=entry.get("accn"),
                            frame=entry.get("frame"),
                        )
                        existing = values_by_period.get(period_key)
                        if existing is None or self._is_better_entry(candidate, existing):
                            values_by_period[period_key] = candidate

                if values_by_period:
                    ordered = [
                        values_by_period[period]
                        for period in target_periods
                        if period in values_by_period
                    ]
                    return tag, taxonomy, ordered
        return None, "us-gaap", []

    def _select_periods(
        self,
        company_facts: dict[str, Any],
        *,
        max_annual: int,
        max_quarterly: int,
    ) -> tuple[list[str], list[str]]:
        annual: set[str] = set()
        quarterly: set[str] = set()

        for taxonomy_facts in (company_facts.get("facts") or {}).values():
            if not isinstance(taxonomy_facts, dict):
                continue
            for payload in taxonomy_facts.values():
                units = payload.get("units") or {}
                for entries in units.values():
                    for entry in entries:
                        form = str(entry.get("form") or "")
                        if form not in {"10-K", "10-Q", "10-K/A", "10-Q/A"}:
                            continue
                        key = self._period_key(entry)
                        if key is None:
                            continue
                        if key.startswith("FY"):
                            annual.add(key)
                        else:
                            quarterly.add(key)

        annual_sorted = sorted(annual, key=self._period_sort_key, reverse=True)[:max_annual]
        quarterly_sorted = (
            sorted(quarterly, key=self._period_sort_key, reverse=True)[:max_quarterly]
            if max_quarterly
            else []
        )
        # Return chronological for statement presentation.
        return list(reversed(annual_sorted)), list(reversed(quarterly_sorted))

    @staticmethod
    def _period_key(entry: dict[str, Any]) -> str | None:
        year = entry.get("fy")
        fp = str(entry.get("fp") or "").upper()
        form = str(entry.get("form") or "").upper()
        if year is None:
            return None
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            return None

        if fp in {"FY", "Q4"} and form.startswith("10-K"):
            return f"FY{year_int}"
        if fp == "FY":
            return f"FY{year_int}"
        if fp in {"Q1", "Q2", "Q3", "Q4"}:
            return f"{fp} {year_int}"
        return None

    @staticmethod
    def _period_sort_key(period: str) -> tuple[int, int]:
        if period.startswith("FY"):
            return int(period[2:]), 4
        parts = period.split()
        if len(parts) == 2 and parts[0].startswith("Q"):
            return int(parts[1]), int(parts[0][1:])
        return (0, 0)

    @staticmethod
    def _is_better_entry(candidate: StatementValue, existing: StatementValue) -> bool:
        """Prefer 10-K/10-Q over amendments older filings; prefer later filed date."""
        form_score = {
            "10-K": 3,
            "10-Q": 3,
            "10-K/A": 2,
            "10-Q/A": 2,
        }
        cand_score = form_score.get(str(candidate.form or ""), 1)
        existing_score = form_score.get(str(existing.form or ""), 1)
        if cand_score != existing_score:
            return cand_score > existing_score
        return str(candidate.filed or "") > str(existing.filed or "")
