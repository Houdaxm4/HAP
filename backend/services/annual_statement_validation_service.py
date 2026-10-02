"""Validate new-FY statements against the 10-K. Blank cells are filled from the filing; supplied values never are."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import AnnualStatementValidationReport, StatementValidationItem
from services.accounting_concept_matcher import CONCEPT_ALIASES
from services.annual_continuity_service import detect_year_columns
from services.formula_dependencies import MetricDependencies
from services.new_company_statement_validation_service import NewCompanyStatementValidationService
from services.statement_row_rules import STATEMENT_ROW_RULES, sign_for
from services.sec_service import SecService
from services.workbook_flag_service import flag_filled, flag_missing_data

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
    ("balance_sheet", "debt", STATEMENT_ROW_RULES["debt"]["sheet"], STATEMENT_ROW_RULES["debt"]["tags"]),
    ("cash_flow", "capex", STATEMENT_ROW_RULES["capex"]["sheet"], STATEMENT_ROW_RULES["capex"]["tags"]),
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
    """Compare the new FY totals to the annual filing.

    A blank cell is filled from the 10-K (shaded, source in the comment). A blank the filing cannot fill is flagged
    only when a reported metric depends on it. A supplied value is never overwritten; a material difference is
    flagged for the analyst.
    """

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
        filled = missing_important = 0
        try:
            dependencies = MetricDependencies(wb)
            for statement, concept, sheet, tags in _CHECKS:
                bb = None
                col = row = None
                ws = None
                is_formula = False
                if sheet in wb.sheetnames:
                    ws = wb[sheet]
                    cols = detect_year_columns(ws)
                    col = cols.get(fy)
                    row = self._find_row(ws, concept)
                    if col and row:
                        raw = ws.cell(row, col).value
                        is_formula = isinstance(raw, str) and raw.startswith("=")
                        bb = _num(raw)
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
                            filing = filing * sign_for(concept)
                            break
                status, reason = self._classify(bb, filing)
                if is_formula:
                    status, reason = "FORMULA_PRESERVED", "The cell holds a formula; it was not compared or overwritten."
                elif bb is None and filing is not None and ws is not None and col and row:
                    cell = ws.cell(row, col)
                    cell.value = filing
                    flag_filled(
                        ws, cell.coordinate, value=filing, source=f"SEC 10-K {fy}",
                        reason="The supplied workbook left this statement cell blank; the 10-K reports the figure.",
                    )
                    bb = filing
                    filled += 1
                    status, reason = "FILLED_FROM_SEC", "Blank in the supplied workbook; filled from the 10-K."
                elif bb is None and filing is None:
                    status, reason = "NOT_AVAILABLE", "Blank in the workbook and not found in the filing; no reported metric uses it."
                    if ws is not None and col and row and dependencies.feeds_metrics(sheet, row, col):
                        status = "MISSING_IMPORTANT"
                        reason = "Blank in the workbook and not found in the SEC filing; a reported metric needs it."
                        missing_important += 1
                        flag_missing_data(ws, ws.cell(row, col).coordinate, concept=concept, reason=reason)
                if status == "DISCREPANCY" and ws is not None and col and row:
                    from services.workbook_flag_service import flag_discrepancy

                    cell = ws.cell(row, col)
                    original = cell.value
                    if not (isinstance(original, str) and original.startswith("=")):
                        flag_discrepancy(
                            ws,
                            cell.coordinate,
                            workbook_value=bb,
                            source_value=filing,
                            provenance=f"SEC 10-K {fy}",
                            issue=reason,
                        )
                        cell.value = original
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
            wb.save(workbook_path)
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
            filled=filled,
            missing_important=missing_important,
            summary=(
                f"New-FY statement validation: {len(items)} concepts, {disc} discrepancy(ies), {filled} blank(s) filled "
                f"from the 10-K, {missing_important} needed value(s) unavailable; supplied values preserved."
            ),
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
        rule = STATEMENT_ROW_RULES.get(concept)
        aliases = tuple(rule["needles"]) if rule else tuple(a.lower() for a in CONCEPT_ALIASES.get(concept, (concept,)))
        return NewCompanyStatementValidationService._find_row(ws, aliases)
