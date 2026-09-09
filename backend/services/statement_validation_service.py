"""Compare completed workbook statement values to SEC companyfacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.statement_validation import (
    StatementValidationDecision,
    StatementValidationEntry,
    StatementValidationReport,
)
from services.sec_service import SecService
from workbook_mapping.explicit_mappings import ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS

# Material line items: (statement, metric, sheet, row, label, concept, preferred_tag, scale, sign)
# scale: millions | per_share | as_is
# sign: as_is | outflow_abs (workbook CF outflows are negative; SEC payments positive)
_MATERIAL_LINES: list[tuple[str, str, str, int, str, str, str | None, str, str]] = [
    ("income_statement", "Revenue", "Income - GAAP", 9, "Revenue", "revenue", None, "millions", "as_is"),
    (
        "income_statement",
        "Cost of Revenue",
        "Income - GAAP",
        14,
        "- Cost of Revenue",
        "cost of revenue",
        "CostOfGoodsAndServicesSold",
        "millions",
        "as_is",
    ),
    ("income_statement", "Gross Profit", "Income - GAAP", 19, "Gross Profit", "gross profit", None, "millions", "as_is"),
    (
        "income_statement",
        "Operating Income",
        "Income - GAAP",
        30,
        "Operating Income (Loss)",
        "operating income",
        None,
        "millions",
        "as_is",
    ),
    (
        "income_statement",
        "Tax Expense",
        "Income - GAAP",
        44,
        "- Income Tax Expense (Benefit)",
        "tax expense",
        "IncomeTaxExpenseBenefit",
        "millions",
        "as_is",
    ),
    (
        "income_statement",
        "Net Income",
        "Income - GAAP",
        58,
        "Net Income, GAAP",
        "net income",
        None,
        "millions",
        "as_is",
    ),
    (
        "income_statement",
        "Diluted EPS",
        "Income - GAAP",
        71,
        "Diluted EPS, GAAP",
        "earnings per share",
        "EarningsPerShareDiluted",
        "per_share",
        "as_is",
    ),
    (
        "balance_sheet",
        "Cash",
        "Balance Sheet - Standardized",
        11,
        "+ Cash & Cash Equivalents",
        "cash and cash equivalents",
        None,
        "millions",
        "as_is",
    ),
    (
        "balance_sheet",
        "Total Assets",
        "Balance Sheet - Standardized",
        61,
        "Total Assets",
        "total assets",
        None,
        "millions",
        "as_is",
    ),
    (
        "balance_sheet",
        "Total Liabilities",
        "Balance Sheet - Standardized",
        106,
        "Total Liabilities",
        "total liabilities",
        "Liabilities",
        "millions",
        "as_is",
    ),
    (
        "balance_sheet",
        "Total Equity",
        "Balance Sheet - Standardized",
        118,
        "Total Equity",
        "stockholders equity",
        None,
        "millions",
        "as_is",
    ),
    (
        "cash_flow",
        "Operating Cash Flow",
        "Cash Flow - Standardized",
        24,
        "Cash from Operating Activities",
        "operating cash flow",
        None,
        "millions",
        "as_is",
    ),
    (
        "cash_flow",
        "Capital Expenditures",
        "Cash Flow - Standardized",
        32,
        "+ Acq of Fixed Prod Assets",
        "capital expenditures",
        None,
        "millions",
        "outflow_abs",
    ),
    (
        "cash_flow",
        "Dividends",
        "Cash Flow - Standardized",
        49,
        "+ Dividends Paid",
        "dividends",
        "PaymentsOfDividends",
        "millions",
        "outflow_abs",
    ),
    (
        "cash_flow",
        "Share Repurchases",
        "Cash Flow - Standardized",
        55,
        "+ Cash (Repurchase) of Equity",
        "share repurchase",
        "PaymentsForRepurchaseOfCommonStock",
        "millions",
        "outflow_abs",
    ),
]

# Quarterly standardized primary cells (latest quarter column C).
_QUARTERLY_LINES: list[tuple[str, str, str, int, str, str, str | None, str, str]] = [
    (
        "quarterly_income_statement",
        "Revenue",
        "Last Quarter IS Standardized",
        11,
        "Revenue",
        "revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "millions",
        "as_is",
    ),
    (
        "quarterly_balance_sheet",
        "Total Assets",
        "Last Quarter BS Standardized",
        61,
        "Total Assets",
        "total assets",
        None,
        "millions",
        "as_is",
    ),
    (
        "quarterly_cash_flow",
        "Operating Cash Flow",
        "Last Quarter CF Standardized",
        11,
        "Cash from Operating Activities",
        "operating cash flow",
        None,
        "millions",
        "as_is",
    ),
]

MATERIALITY_RULES = {
    "validated_abs_millions": 1.0,  # ≤ $1M rounding
    "validated_rel": 0.001,  # ≤ 0.1%
    "discrepancy_abs_millions": 25.0,  # > $25M
    "discrepancy_rel": 0.005,  # > 0.5%
    "per_share_abs": 0.02,
    "note": (
        "Workbook statement grids are USD millions. SEC USD facts are scaled /1e6. "
        "Both absolute and relative thresholds must fail to mark DISCREPANCY; "
        "tiny absolute rounding cannot be escalated by percentage alone on tiny bases."
    ),
}


def _period_map_from_workbook(ws) -> dict[str, str]:
    """Map column letter → FY token from row 7 headers when present."""
    cols: dict[str, str] = {}
    for col, default_fy in zip(ANNUAL_PERIOD_COLS, ANNUAL_PERIOD_FY_TOKENS, strict=True):
        header = ws[f"{col}7"].value
        if header is None:
            cols[col] = default_fy
            continue
        text = str(header).replace(" ", "").upper()
        if text.startswith("FY") and len(text) >= 6:
            cols[col] = f"FY{text[-4:]}"
        else:
            digits = "".join(ch for ch in text if ch.isdigit())
            cols[col] = f"FY{digits[-4:]}" if len(digits) >= 4 else default_fy
    return cols


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if value.startswith("=") or value.strip() == "":
            return None
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compare_values(
    workbook_value: float,
    sec_value: float,
    *,
    scale: str = "millions",
) -> StatementValidationDecision:
    """Deterministic materiality decision."""
    abs_diff = abs(workbook_value - sec_value)
    base = max(abs(workbook_value), abs(sec_value), 1e-12)
    rel = abs_diff / base

    if scale == "per_share":
        if abs_diff <= MATERIALITY_RULES["per_share_abs"] or rel <= MATERIALITY_RULES["validated_rel"]:
            return StatementValidationDecision.VALIDATED
        # Common share-split multiples (as-reported vs restated EPS)
        if abs(workbook_value) > 1e-9:
            ratio = abs(sec_value / workbook_value)
            for split in (2.0, 3.0, 4.0, 5.0, 7.0, 10.0):
                if abs(ratio - split) <= 0.05:
                    return StatementValidationDecision.NOT_COMPARABLE
        if abs_diff > 0.10 and rel > MATERIALITY_RULES["discrepancy_rel"]:
            return StatementValidationDecision.DISCREPANCY
        return StatementValidationDecision.REVIEW_REQUIRED

    # millions: absolute rounding gates VALIDATED so large-base
    # relative-only matches cannot skip the mid-tier REVIEW band.
    abs_ok = abs_diff <= MATERIALITY_RULES["validated_abs_millions"]
    if abs_ok:
        return StatementValidationDecision.VALIDATED

    abs_bad = abs_diff > MATERIALITY_RULES["discrepancy_abs_millions"]
    rel_bad = rel > MATERIALITY_RULES["discrepancy_rel"]
    # Require economically meaningful absolute OR (large relative AND > $5M)
    if abs_bad or (rel_bad and abs_diff > 5.0):
        return StatementValidationDecision.DISCREPANCY
    return StatementValidationDecision.REVIEW_REQUIRED


class StatementValidationService:
    """Validate completed workbook statement grids against SEC (no rewrites)."""

    def __init__(self, sec_service: SecService | None = None) -> None:
        self.sec = sec_service or SecService()

    def validate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        company_facts: dict[str, Any],
        include_quarterly: bool = False,
        annual_lines: bool = True,
    ) -> StatementValidationReport:
        wb = load_workbook(workbook_path, data_only=False)
        entries: list[StatementValidationEntry] = []
        try:
            lines: list = []
            if annual_lines:
                lines.extend(_MATERIAL_LINES)
            if include_quarterly:
                lines.extend(_QUARTERLY_LINES)

            for statement, metric, sheet, row, label, concept, tag, scale, sign in lines:
                if sheet not in wb.sheetnames:
                    entries.append(
                        StatementValidationEntry(
                            statement=statement,
                            metric=metric,
                            workbook_cell=f"{sheet}!C{row}",
                            workbook_label=label,
                            fiscal_period="n/a",
                            decision=StatementValidationDecision.SOURCE_MISSING,
                            reason=f"Sheet '{sheet}' missing from workbook",
                        )
                    )
                    continue

                ws = wb[sheet]
                if statement.startswith("quarterly"):
                    periods = {"C": self._quarter_period_token(ws)}
                else:
                    periods = _period_map_from_workbook(ws)

                for col, fy_token in periods.items():
                    cell_addr = f"{col}{row}"
                    wb_raw = ws[cell_addr].value
                    wb_label = ws[f"A{row}"].value
                    wb_val = _to_float(wb_raw)
                    if wb_val is None:
                        # Formula cells: skip as NOT_COMPARABLE without data_only cache
                        if isinstance(wb_raw, str) and wb_raw.startswith("="):
                            entries.append(
                                StatementValidationEntry(
                                    statement=statement,
                                    metric=metric,
                                    workbook_cell=f"{sheet}!{cell_addr}",
                                    workbook_label=str(wb_label) if wb_label else label,
                                    fiscal_period=fy_token,
                                    decision=StatementValidationDecision.NOT_COMPARABLE,
                                    reason="Workbook cell is formula-driven; compare via cached values not available",
                                )
                            )
                        continue

                    fact = self._find_sec(
                        company_facts,
                        concept=concept,
                        period=fy_token,
                        preferred_tag=tag,
                        quarterly=statement.startswith("quarterly"),
                    )
                    if fact is None:
                        entries.append(
                            StatementValidationEntry(
                                statement=statement,
                                metric=metric,
                                workbook_cell=f"{sheet}!{cell_addr}",
                                workbook_label=str(wb_label) if wb_label else label,
                                fiscal_period=fy_token,
                                workbook_value=wb_val,
                                decision=StatementValidationDecision.SOURCE_MISSING,
                                reason=f"No SEC fact for {concept} @ {fy_token}",
                                scale="USD_millions" if scale == "millions" else scale,
                            )
                        )
                        continue

                    sec_val = float(fact.value)
                    if scale == "millions" and abs(sec_val) >= 1_000:
                        # companyfacts are typically absolute USD
                        sec_val = sec_val / 1_000_000.0
                    # CF investing/financing payments are positive in SEC; workbook uses outflow negatives.
                    if sign == "outflow_abs":
                        sec_val = -abs(sec_val)
                        wb_compare = -abs(wb_val) if wb_val is not None else wb_val
                    else:
                        wb_compare = wb_val

                    decision = compare_values(wb_compare, sec_val, scale=scale)
                    abs_diff = abs(wb_compare - sec_val)
                    if wb_compare != 0:
                        pct = (sec_val - wb_compare) / abs(wb_compare)
                    else:
                        pct = None

                    period_meta = self._fact_period_meta(
                        company_facts,
                        tag=fact.tag,
                        accession=fact.accession_number,
                        fiscal_year=fact.fiscal_year,
                        fiscal_period=fact.fiscal_period,
                        value=fact.value,
                    )

                    reason = {
                        StatementValidationDecision.VALIDATED: (
                            "Workbook agrees with SEC within materiality tolerance"
                            + (" (CF outflow sign-normalized)" if sign == "outflow_abs" else "")
                        ),
                        StatementValidationDecision.DISCREPANCY: (
                            "Material mismatch vs SEC — not rewritten; recorded for review"
                        ),
                        StatementValidationDecision.REVIEW_REQUIRED: (
                            "Difference above rounding but below hard discrepancy threshold"
                        ),
                        StatementValidationDecision.NOT_COMPARABLE: (
                            "EPS as-reported vs restated/split-adjusted series not directly comparable"
                        ),
                    }.get(decision, decision.value)

                    entries.append(
                        StatementValidationEntry(
                            statement=statement,
                            metric=metric,
                            workbook_cell=f"{sheet}!{cell_addr}",
                            workbook_label=str(wb_label) if wb_label else label,
                            fiscal_period=fy_token,
                            workbook_value=wb_val,
                            sec_value=sec_val if sign != "outflow_abs" else -abs(float(fact.value) / (1_000_000.0 if abs(fact.value) >= 1_000 else 1.0)),
                            absolute_difference=round(abs_diff, 6),
                            percentage_difference=round(pct, 6) if pct is not None else None,
                            sec_concept=fact.tag,
                            filing_form=fact.form,
                            accession_number=fact.accession_number,
                            period_start=period_meta.get("start"),
                            period_end=period_meta.get("end"),
                            decision=decision,
                            reason=reason,
                            scale="USD_millions" if scale == "millions" else scale,
                        )
                    )
        finally:
            wb.close()

        counts = {d: 0 for d in StatementValidationDecision}
        for e in entries:
            counts[e.decision] += 1
        summary = (
            f"Statement validation: {counts[StatementValidationDecision.VALIDATED]} VALIDATED, "
            f"{counts[StatementValidationDecision.DISCREPANCY]} DISCREPANCY, "
            f"{counts[StatementValidationDecision.REVIEW_REQUIRED]} REVIEW_REQUIRED, "
            f"{counts[StatementValidationDecision.SOURCE_MISSING]} SOURCE_MISSING, "
            f"{counts[StatementValidationDecision.NOT_COMPARABLE]} NOT_COMPARABLE "
            f"(no workbook writes)."
        )
        return StatementValidationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            entries=entries,
            validated_count=counts[StatementValidationDecision.VALIDATED],
            discrepancy_count=counts[StatementValidationDecision.DISCREPANCY],
            not_comparable_count=counts[StatementValidationDecision.NOT_COMPARABLE],
            source_missing_count=counts[StatementValidationDecision.SOURCE_MISSING],
            review_required_count=counts[StatementValidationDecision.REVIEW_REQUIRED],
            materiality_rules=dict(MATERIALITY_RULES),
            summary=summary,
        )

    def _find_sec(
        self,
        company_facts: dict[str, Any],
        *,
        concept: str,
        period: str,
        preferred_tag: str | None,
        quarterly: bool,
    ):
        # Annual FY2018 / quarterly tokens like Q3 2026 or FY2025Q3
        if quarterly:
            # Prefer latest 10-Q matching period loosely via FY+Q if parseable
            period_key = period if period.startswith("Q") or "Q" in period else period
            if preferred_tag:
                fact = self.sec.find_fact(company_facts, concept, period_key, preferred_tag)
                if fact:
                    return fact
            return self.sec.find_fact(company_facts, concept, period_key, preferred_tag)
        if preferred_tag:
            fact = self.sec.find_fact(company_facts, concept, period, preferred_tag)
            if fact:
                return fact
        return self.sec.find_fact(company_facts, concept, period, preferred_tag)

    @staticmethod
    def _fact_period_meta(
        company_facts: dict[str, Any],
        *,
        tag: str,
        accession: str | None,
        fiscal_year: int | None,
        fiscal_period: str | None,
        value: float | None,
    ) -> dict[str, str | None]:
        """Recover start/end from companyfacts for the matched XBRL fact."""
        facts = (company_facts.get("facts") or {}).get("us-gaap") or {}
        payload = facts.get(tag) or {}
        for _unit, entries in (payload.get("units") or {}).items():
            for entry in entries or []:
                if accession and entry.get("accn") != accession:
                    continue
                if fiscal_year is not None and entry.get("fy") != fiscal_year:
                    continue
                if fiscal_period and entry.get("fp") != fiscal_period:
                    continue
                if value is not None and entry.get("val") is not None:
                    try:
                        if abs(float(entry["val"]) - float(value)) > 1e-3:
                            continue
                    except (TypeError, ValueError):
                        continue
                return {"start": entry.get("start"), "end": entry.get("end")}
        return {"start": None, "end": None}

    @staticmethod
    def _quarter_period_token(ws) -> str:
        raw = ws["C5"].value or ws["C2"].value or "LQ"
        text = str(raw).strip()
        return text or "LQ"
