"""Extract canonical statement series from SEC companyfacts (source of truth)."""

from __future__ import annotations

from typing import Any

from canonical_model.primitives import FinancialPoint, FinancialSeries, LineItemProvenance
from services.sec_service import CONCEPT_TO_XBRL, SecService

# Canonical field → preferred SEC concept key (must exist in CONCEPT_TO_XBRL or use xbrl hint).
_STATEMENT_SEC_MAP: list[tuple[str, str, str, str | None]] = [
    # statement, field, concept_for_alias, optional explicit preferred tag
    ("income_statement", "revenue", "revenue", None),
    ("income_statement", "gross_profit", "gross profit", None),
    ("income_statement", "operating_income", "operating income", None),
    ("income_statement", "net_income", "net income", None),
    ("income_statement", "diluted_eps", "earnings per share", "EarningsPerShareDiluted"),
    ("income_statement", "interest_expense", "interest expense", "InterestExpense"),
    ("income_statement", "tax_expense", "tax expense", "IncomeTaxExpenseBenefit"),
    ("income_statement", "ebit", "ebit", "OperatingIncomeLoss"),
    ("income_statement", "ebitda", "ebitda", None),
    ("income_statement", "cost_of_revenue", "cost of revenue", "CostOfRevenue"),
    ("balance_sheet", "cash", "cash and cash equivalents", None),
    ("balance_sheet", "total_assets", "total assets", None),
    ("balance_sheet", "total_liabilities", "total liabilities", None),
    ("balance_sheet", "shareholders_equity", "stockholders equity", None),
    ("balance_sheet", "current_assets", "current assets", "AssetsCurrent"),
    ("balance_sheet", "current_liabilities", "current liabilities", "LiabilitiesCurrent"),
    ("balance_sheet", "total_debt", "total debt", "LongTermDebt"),
    ("cash_flow_statement", "operating_cash_flow", "operating cash flow", None),
    ("cash_flow_statement", "capital_expenditures", "capital expenditures", None),
    ("cash_flow_statement", "free_cash_flow", "free cash flow", None),
    ("cash_flow_statement", "dividends", "dividends", "PaymentsOfDividends"),
    (
        "cash_flow_statement",
        "share_repurchases",
        "share repurchase",
        "PaymentsForRepurchaseOfCommonStock",
    ),
]

# Extra tags tried when CONCEPT_TO_XBRL lacks a concept.
_EXTRA_TAGS: dict[str, list[str]] = {
    "interest expense": ["InterestExpense", "InterestExpenseDebt"],
    "tax expense": ["IncomeTaxExpenseBenefit"],
    "cost of revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "current assets": ["AssetsCurrent"],
    "current liabilities": ["LiabilitiesCurrent"],
    "total debt": [
        "LongTermDebt",
        "LongTermDebtNoncurrent",
        "DebtCurrent",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "free cash flow": [],  # usually derived
    "dividends": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "share repurchase": [
        "PaymentsForRepurchaseOfCommonStock",
        "TreasuryStockValueAcquiredCostMethod",
    ],
    "ebitda": ["EBITDA"],
}


def extract_statement_cells_from_sec(
    company_facts: dict[str, Any],
    *,
    years: int = 10,
) -> list[dict[str, Any]]:
    """
    Build workbook-cell-like payloads from SEC companyfacts for annual FY windows.

    Never invents values — skips years/tags with no match.
    """
    sec = SecService()
    cells: list[dict[str, Any]] = []
    latest_year = _infer_latest_fiscal_year(company_facts)
    if latest_year is None:
        return cells
    year_list = list(range(latest_year - years + 1, latest_year + 1))

    for _statement, _field, concept, preferred_tag in _STATEMENT_SEC_MAP:
        for year in year_list:
            period = f"FY{year}"
            fact = None
            if preferred_tag:
                fact = sec.find_fact(company_facts, concept, period, preferred_tag)
            if fact is None:
                # Try alias table / extras
                if concept in CONCEPT_TO_XBRL or concept in _EXTRA_TAGS:
                    fact = sec.find_fact(company_facts, concept, period, None)
                if fact is None:
                    for tag in _EXTRA_TAGS.get(concept, []):
                        fact = sec.find_fact(company_facts, concept, period, tag)
                        if fact is not None:
                            break
            if fact is None:
                continue
            cells.append(
                {
                    "concept": concept,
                    "period": period,
                    "value": fact.value,
                    "currency": "USD",
                    "unit": fact.unit,
                    "source": "sec_companyfacts",
                    "source_document": None,
                    "xbrl_tag": f"{fact.taxonomy}:{fact.tag}",
                    "confidence": 0.9,
                    "audited": fact.form in {"10-K", "20-F"},
                    "filing_type": fact.form,
                    "accession_number": fact.accession_number,
                    "worksheet": "SEC",
                    "cell_ref": f"SEC!{concept}!{period}",
                }
            )

    # Derive FCF = OCF - |CapEx| when both exist and FCF missing for period.
    by_period: dict[str, dict[str, float]] = {}
    for cell in cells:
        concept = str(cell["concept"])
        period = str(cell["period"])
        by_period.setdefault(period, {})[concept] = float(cell["value"])
    for period, values in by_period.items():
        if "free cash flow" in values:
            continue
        ocf = values.get("operating cash flow")
        capex = values.get("capital expenditures")
        if ocf is None or capex is None:
            continue
        fcf = ocf - abs(capex)
        cells.append(
            {
                "concept": "free cash flow",
                "period": period,
                "value": fcf,
                "currency": "USD",
                "unit": "USD",
                "source": "sec_derived",
                "confidence": 0.85,
                "audited": True,
                "filing_type": "10-K",
                "worksheet": "SEC",
                "cell_ref": f"SEC!free cash flow!{period}",
            }
        )
    return cells


def _infer_latest_fiscal_year(company_facts: dict[str, Any]) -> int | None:
    years: list[int] = []
    for taxonomy in company_facts.get("facts", {}).values():
        if not isinstance(taxonomy, dict):
            continue
        for payload in taxonomy.values():
            units = payload.get("units", {})
            for entries in units.values():
                for entry in entries:
                    fy = entry.get("fy")
                    form = entry.get("form", "")
                    if isinstance(fy, int) and form in {"10-K", "10-Q", "20-F"}:
                        years.append(fy)
    return max(years) if years else None
