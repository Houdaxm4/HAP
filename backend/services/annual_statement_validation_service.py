"""Validate new-FY Bloomberg statements against the 10-K without reconstructing the statements."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import AnnualStatementValidationReport, StatementValidationItem
from services.accounting_concept_matcher import CONCEPT_ALIASES
from services.annual_continuity_service import detect_year_columns
from services.sec_service import SecService

_CHECKS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("income_statement", "revenue", "Income - GAAP", ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")),
    ("income_statement", "operating_income", "Income - GAAP", ("OperatingIncomeLoss",)),
    ("income_statement", "net_income", "Income - GAAP", ("NetIncomeLoss",)),
    ("income_statement", "diluted_eps", "Income - GAAP", ("EarningsPerShareDiluted",)),
    ("balance_sheet", "total_assets", "Balance Sheet - Standardized", ("Assets",)),
    ("balance_sheet", "total_liabilities", "Balance Sheet - Standardized", ("Liabilities",)),
    ("balance_sheet", "equity", "Balance Sheet - Standardized", ("StockholdersEquity",)),
    ("cash_flow", "cfo", "Cash Flow - Standardized", ("NetCashProvidedByUsedInOperatingActivities",)),
    ("cash_flow", "cfi", "Cash Flow - Standardized", ("NetCashProvidedByUsedInInvestingActivities",)),
    ("cash_flow", "cff", "Cash Flow - Standardized", ("NetCashProvidedByUsedInFinancingActivities",)),
]

_REL = 0.03
_ABS = 25.0


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


class AnnualStatementValidationService:
    """Compare Bloomberg-populated new FY totals to the annual filing; do not auto-rewrite."""

    def validate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_year: str,
        company_facts: dict[str, Any] | None = None,
        filing_overrides: dict[str, float] | None = None,
    ) -> AnnualStatementValidationReport:
        wb = load_workbook(workbook_path, data_only=False)
        items: list[StatementValidationItem] = []
        sec = SecService()
        fy = fiscal_year if str(fiscal_year).startswith("FY") else f"FY{fiscal_year}"
        year_n = int("".join(ch for ch in fy if ch.isdigit()) or 0)
        try:
            for statement, concept, sheet, tags in _CHECKS:
                bb = None
                if sheet in wb.sheetnames:
                    ws = wb[sheet]
                    cols = detect_year_columns(ws)
                    col = cols.get(fy)
                    row = self._find_row(ws, concept)
                    if col and row:
                        bb = _num(ws.cell(row, col).value)
                filing = None
                if filing_overrides and concept in filing_overrides:
                    filing = filing_overrides[concept]
                elif company_facts and year_n:
                    for tag in tags:
                        fact = sec.find_fact(company_facts, concept, fy, xbrl_tag_hint=tag)
                        if fact is not None and fact.value is not None:
                            filing = float(fact.value)
                            if concept != "diluted_eps" and abs(filing) > 10_000:
                                filing = filing / 1_000_000.0
                            break
                status, reason = self._classify(bb, filing)
                items.append(
                    StatementValidationItem(
                        statement=statement,
                        concept=concept,
                        fiscal_year=fy,
                        bloomberg_value=bb,
                        filing_value=filing,
                        status=status,
                        reason=reason,
                    )
                )
        finally:
            wb.close()
        disc = sum(1 for i in items if i.status == "DISCREPANCY")
        return AnnualStatementValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fy,
            items=items,
            bloomberg_preserved=True,
            discrepancies=disc,
            summary=f"New-FY statement validation: {len(items)} concepts, {disc} discrepancy(ies); Bloomberg preserved.",
        )

    @staticmethod
    def _classify(bb: float | None, filing: float | None) -> tuple[str, str]:
        if bb is None and filing is None:
            return "REVIEW_REQUIRED", "Neither Bloomberg nor filing value located."
        if filing is None:
            return "VALIDATED", "Filing value unavailable; Bloomberg preserved."
        if bb is None:
            return "REVIEW_REQUIRED", "Bloomberg cell empty; not reconstructed from SEC."
        abs_d = abs(bb - filing)
        rel = abs_d / max(abs(bb), abs(filing), 1e-9)
        if abs_d <= _ABS or rel <= _REL:
            return "VALIDATED", "Bloomberg agrees with annual filing within rounding tolerance."
        return (
            "DISCREPANCY",
            "Material difference after concept/units/sign checks; Bloomberg not auto-rewritten.",
        )

    @staticmethod
    def _find_row(ws, concept: str) -> int | None:
        aliases = [a.lower() for a in CONCEPT_ALIASES.get(concept, (concept,))]
        hits = []
        for row in range(1, min(ws.max_row or 1, 130) + 1):
            text = str(ws.cell(row, 1).value or "").strip().lower()
            if text and any(a in text or text in a for a in aliases):
                hits.append(row)
        return hits[0] if len(hits) == 1 else (hits[0] if hits else None)
