"""Validate ten years of Bloomberg-prefilled statements against SEC filings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.new_company import NewCompanyStatementValidationReport, StatementDiscrepancy
from services.annual_period_service import detect_year_columns
from services.formula_dependencies import MetricDependencies
from services.sec_service import SecService
from services.statement_row_rules import STATEMENT_ROW_RULES, sign_for
from services.workbook_flag_service import flag_filled, flag_missing_data

# concept, sheet, label needles, xbrl tags, scale_if_large
_CHECKS: list[tuple[str, str, tuple[str, ...], tuple[str, ...], bool]] = [
    ("revenue", "Income - GAAP", ("revenue", "sales"), ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"), True),
    ("gross_profit", "Income - GAAP", ("gross profit",), ("GrossProfit",), True),
    ("operating_income", "Income - GAAP", ("operating income", "operating income (loss)"), ("OperatingIncomeLoss",), True),
    ("pretax_income", "Income - GAAP", ("pretax income", "income before tax", "income before income taxes"), ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"), True),
    ("income_tax_expense", "Income - GAAP", ("income tax expense", "income tax expense (benefit)", "provision for income taxes"), ("IncomeTaxExpenseBenefit",), True),
    ("net_income", "Income - GAAP", ("net income", "net income (loss)"), ("NetIncomeLoss",), True),
    ("diluted_eps", "Income - GAAP", ("diluted eps", "earnings per share diluted", "eps - diluted"), ("EarningsPerShareDiluted",), False),
    ("cfo", "Cash Flow - Standardized", ("cash from operating", "operating activities"), ("NetCashProvidedByUsedInOperatingActivities",), True),
    ("capex", STATEMENT_ROW_RULES["capex"]["sheet"], STATEMENT_ROW_RULES["capex"]["needles"], STATEMENT_ROW_RULES["capex"]["tags"], True),
    ("cfi", "Cash Flow - Standardized", ("cash from investing", "investing activities"), ("NetCashProvidedByUsedInInvestingActivities",), True),
    ("cff", "Cash Flow - Standardized", ("cash from financing", "financing activities"), ("NetCashProvidedByUsedInFinancingActivities",), True),
    ("cash", "Balance Sheet - Standardized", ("cash and cash equivalents", "cash & cash equivalents", "cash"), ("CashAndCashEquivalentsAtCarryingValue",), True),
    ("total_assets", "Balance Sheet - Standardized", ("total assets",), ("Assets",), True),
    ("current_liabilities", "Balance Sheet - Standardized", ("total current liabilities", "current liabilities"), ("LiabilitiesCurrent",), True),
    ("total_liabilities", "Balance Sheet - Standardized", ("total liabilities",), ("Liabilities",), True),
    ("equity", "Balance Sheet - Standardized", ("total equity", "total shareholders", "stockholders' equity"), ("StockholdersEquity",), True),
    ("debt", STATEMENT_ROW_RULES["debt"]["sheet"], STATEMENT_ROW_RULES["debt"]["needles"], STATEMENT_ROW_RULES["debt"]["tags"], True),
    ("diluted_shares", "Income - GAAP", ("diluted weighted", "weighted average shares diluted", "diluted shares"), ("WeightedAverageNumberOfDilutedSharesOutstanding",), True),
]

_REL = 0.03
_ABS = 25.0
_MATERIAL_REL = 0.05


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("(", "-").replace(")", ""))
    except (TypeError, ValueError):
        return None


def _is_formula(v: Any) -> bool:
    return isinstance(v, str) and v.startswith("=")


def _scale_usd(value: float, *, scale: bool) -> float:
    if not scale:
        return value
    if abs(value) >= 10_000:
        return value / 1_000_000.0
    return value


class NewCompanyStatementValidationService:
    """SEC is authoritative for blanks: a blank statement cell is filled from SEC (shaded, source in the comment).

    A blank that no filing can fill is flagged only when a reported metric depends on it. Supplied (non-blank)
    values are never overwritten; material differences are flagged for the analyst.
    """

    def validate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        filing_overrides: dict[str, dict[str, float]] | None = None,
        yahoo_fallback: Any = None,
    ) -> NewCompanyStatementValidationReport:
        wb = load_workbook(workbook_path, data_only=False)
        sec = SecService()
        items: list[dict[str, Any]] = []
        discrepancies: list[StatementDiscrepancy] = []
        filled: list[StatementDiscrepancy] = []
        corrections: list[StatementDiscrepancy] = []
        unresolved: list[str] = []
        flagged_missing: list[str] = []
        formulas_ok = True
        try:
            dependencies = MetricDependencies(wb)
            for fy in fiscal_years:
                for concept, sheet, needles, tags, scale in _CHECKS:
                    bb = None
                    cell_addr = None
                    formula = False
                    row = col = None
                    if sheet in wb.sheetnames:
                        ws = wb[sheet]
                        cols = detect_year_columns(ws, wb)
                        col = cols.get(fy)
                        row = self._find_row(ws, needles)
                        if col and row:
                            val = ws.cell(row, col).value
                            formula = _is_formula(val)
                            if formula:
                                formulas_ok = formulas_ok and True
                            else:
                                bb = _num(val)
                            cell_addr = f"{sheet}!{get_column_letter(col)}{row}"

                    filing = None
                    source = None
                    if filing_overrides and fy in filing_overrides and concept in filing_overrides[fy]:
                        filing = float(filing_overrides[fy][concept]) * sign_for(concept)
                        source = "filing_override"
                    elif company_facts:
                        for tag in tags:
                            fact = sec.find_fact(company_facts, concept, fy, xbrl_tag_hint=tag)
                            if fact is not None and fact.value is not None:
                                filing = _scale_usd(float(fact.value), scale=scale) * sign_for(concept)
                                source = f"SEC {fact.form} {tag} accn={fact.accession_number}"
                                break

                    status = "validated"
                    action = "preserve"
                    if formula:
                        status = "formula_preserved"
                    elif bb is None and filing is not None and row and col and sheet in wb.sheetnames:
                        cell = wb[sheet].cell(row, col)
                        cell.value = filing
                        flag_filled(
                            wb[sheet], cell.coordinate, value=filing, source=source or "SEC",
                            reason="The supplied workbook left this statement cell blank; the filing reports the figure.",
                        )
                        action = "fill_missing"
                        status = "filled_from_sec"
                        filled.append(
                            StatementDiscrepancy(
                                fiscal_year=fy,
                                statement=sheet,
                                concept=concept,
                                sheet=sheet,
                                cell=cell_addr,
                                old_value=None,
                                new_value=filing,
                                source=source,
                                reason="Blank in the supplied workbook; filled from the SEC filing.",
                                impact="Enables downstream formulas that require this concept.",
                                action=action,
                                material=True,
                            )
                        )
                        bb = filing
                    elif bb is not None and filing is not None:
                        if not self._close(bb, filing):
                            material = abs(bb - filing) / max(abs(filing), 1.0) > _MATERIAL_REL
                            rec = StatementDiscrepancy(
                                fiscal_year=fy,
                                statement=sheet,
                                concept=concept,
                                sheet=sheet,
                                cell=cell_addr,
                                old_value=bb,
                                new_value=filing,
                                source=source,
                                reason="Bloomberg prefilled value differs from SEC-reported amount.",
                                impact="May affect ROIC, tax, and valuation if uncorrected.",
                                action="correct" if material else "preserve",
                                material=material,
                            )
                            discrepancies.append(rec)
                            if material and row and col and sheet in wb.sheetnames:
                                from services.workbook_flag_service import flag_discrepancy

                                ws = wb[sheet]
                                cell = ws.cell(row, col)
                                rec.action = "flag_for_upstream"
                                corrections.append(rec)
                                status = "flagged_material_discrepancy"
                                unresolved.append(
                                    f"{fy}:{concept}:{cell_addr}: workbook={bb} sec={filing} ({source})"
                                )
                                if not _is_formula(cell.value):
                                    flag_discrepancy(
                                        ws,
                                        cell.coordinate,
                                        workbook_value=bb,
                                        source_value=filing,
                                        provenance=source or "SEC",
                                        issue="Material statement discrepancy. Supplied value preserved.",
                                    )
                            else:
                                rec.action = "preserve"
                                status = "immaterial_difference"
                        else:
                            status = "validated"
                    elif bb is None and filing is None and self._try_yahoo(
                        wb, ws=wb[sheet] if sheet in wb.sheetnames else None, row=row, col=col, fy=fy, concept=concept,
                        ticker=ticker, yahoo=yahoo_fallback, filled=filled, cell_addr=cell_addr, sheet=sheet,
                    ):
                        status = "filled_from_yahoo"
                    elif bb is None and filing is None:
                        status = "missing_both"
                        if row and col and sheet in wb.sheetnames and dependencies.feeds_metrics(sheet, row, col):
                            status = "missing_important"
                            flagged_missing.append(f"{fy}:{concept}:{cell_addr}")
                            flag_missing_data(
                                wb[sheet], wb[sheet].cell(row, col).coordinate, concept=concept,
                                reason="Blank in the supplied workbook and not found in the SEC filings.",
                            )
                    elif bb is None:
                        status = "missing_workbook"
                    else:
                        status = "sec_unavailable_preserved"

                    items.append(
                        {
                            "fiscal_year": fy,
                            "concept": concept,
                            "bloomberg_value": bb,
                            "filing_value": filing,
                            "status": status,
                            "cell": cell_addr,
                            "source": source,
                        }
                    )
            wb.save(workbook_path)
        finally:
            wb.close()

        if unresolved:
            status = "blocked"
        elif corrections or discrepancies:
            status = "reviewed"
        else:
            status = "ok"
        return NewCompanyStatementValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            items=items,
            discrepancies=discrepancies,
            filled_missing=filled,
            corrections=corrections,
            unresolved_material=unresolved,
            flagged_missing=flagged_missing,
            formulas_preserved=formulas_ok,
            status=status,
            summary=(
                f"Statements: {len(items)} checks; filled_from_sec={len(filled)}; "
                f"material_flagged={len(corrections)}; discrepancies={len(discrepancies)}; "
                f"unresolved={len(unresolved)}; important_data_unavailable={len(flagged_missing)}. "
                "Supplied values were not overwritten."
            ),
        )

    # Labels that look like an amount line but are rates, ratios or checks ("Cost of Debt", "Debt / Equity").
    _NOT_AN_AMOUNT = ("cost of", "ratio", "/", "%", "check", "per share", "rate", "yield")

    def _try_yahoo(self, wb, *, ws, row, col, fy, concept, ticker, yahoo, filled, cell_addr, sheet) -> bool:
        """Last resort for a blank cell SEC has nothing for: a Yahoo figure, only if its year provably lines up."""
        if yahoo is None or ws is None or not row or not col:
            return False
        anchors = self._anchors(wb, fy)
        found = yahoo.value(ticker, concept, fy, anchors)
        if found is None or _is_formula(ws.cell(row, col).value):
            return False
        value, source = found
        ws.cell(row, col).value = value
        flag_filled(
            ws, ws.cell(row, col).coordinate, value=value, source=source,
            reason="Blank in the supplied workbook and not found in the SEC filings; Yahoo's figure is indicative only.",
        )
        filled.append(
            StatementDiscrepancy(
                fiscal_year=fy, statement=sheet, concept=concept, sheet=sheet, cell=cell_addr, old_value=None,
                new_value=value, source=source,
                reason="Blank in the supplied workbook, not in SEC; filled from Yahoo Finance (indicative).",
                impact="Enables downstream formulas; verify against the filing before relying on it.",
                action="fill_missing", material=False,
            )
        )
        return True

    def _anchors(self, wb, fy: str) -> dict[str, float | None]:
        """The workbook's own revenue and net income for this fiscal year (used to prove a Yahoo year lines up)."""
        out: dict[str, float | None] = {}
        for concept, sheet, needles, _tags, _scale in _CHECKS:
            if concept not in ("revenue", "net_income") or sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            col = detect_year_columns(ws, wb).get(fy)
            row = self._find_row(ws, needles)
            raw = ws.cell(row, col).value if row and col else None
            out[concept] = float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None
        return out

    @staticmethod
    def _find_row(ws, needles: tuple[str, ...]) -> int | None:
        """Row whose label is the statement line. Bloomberg marks sub-lines with a leading '+' or '-'.

        Priority: exact label (with or without the marker) beats a substring match, and a substring match is only
        allowed on unmarked rows, so a sub-line can never be mistaken for the total it feeds.
        """
        from services.title_row_guard import title_rows

        substring_hit = None
        titles = title_rows(ws)  # section titles repeat the label of the real data row and must stay blank
        for row in range(1, min(ws.max_row or 1, 160) + 1):
            if row in titles:
                continue
            raw = str(ws.cell(row, 1).value or "").strip().lower()
            if not raw:
                continue
            marked = raw[0] in "+-"
            lab = raw.lstrip("+- ").strip()
            if any(word in lab for word in NewCompanyStatementValidationService._NOT_AN_AMOUNT):
                continue
            if any(n == lab for n in needles):
                return row
            if not marked and substring_hit is None and any(n in lab for n in needles):
                substring_hit = row
        return substring_hit

    @staticmethod
    def _close(a: float, b: float) -> bool:
        if abs(a - b) <= _ABS:
            return True
        denom = max(abs(b), abs(a), 1e-9)
        return abs(a - b) / denom <= _REL
