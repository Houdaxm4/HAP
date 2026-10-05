"""New Company: fill the cumulative (year-to-date) sections of the Last Quarter income statement and cash flow tabs.

Bloomberg gives only the 3-month quarter. The analyst needs the year-to-date figures too, and the margins in columns K and L
(gross, operating and net margin) are built from them. Source order: SEC 10-Q company facts (exact period end and length), then
Yahoo Finance quarterly figures added up over the fiscal year to date. Anything taken from Yahoo is flagged as indicative.

Income statement tab (columns G = current year to date, H = prior-year to date): revenue, cost of revenue, gross profit,
operating income, net income (and net income to common), basic and diluted EPS.
Cash flow tab (columns C = current year to date, D = prior-year to date): net income, cash from operating, investing and financing
activities, net change in cash.

Rows are found by the Bloomberg field code in column B, so section titles are never written to. Only blank cells are filled.
Every fill is logged in the HAP Adjustments tab; notes are placed in columns D/E, never in the hidden column B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.adjustment_ledger_service import AdjustmentLedger
from services.hap_analysis_layout_service import HapAnalysisLayoutService
from services.sec_10q_statement_service import duration_bucket

LQ_IS = "Last Quarter IS Standardized"
LQ_CF = "Last Quarter CF Standardized"
BUCKET = {1: "3m", 2: "6m", 3: "9m"}
MONTHS = {1: 3, 2: 6, 3: 9}
CATEGORY = "Cumulative from 10-Q"

# concept -> (sec tags, unit kind)
SEC_TAGS: dict[str, tuple[tuple[str, ...], str]] = {
    "revenue": (("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"), "usd"),
    "cost_of_revenue": (("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"), "usd"),
    "gross_profit": (("GrossProfit",), "usd"),
    "operating_income": (("OperatingIncomeLoss",), "usd"),
    "sga": (("SellingGeneralAndAdministrativeExpense",), "usd"),
    "rd": (("ResearchAndDevelopmentExpense",), "usd"),
    "net_income": (("NetIncomeLoss", "ProfitLoss"), "usd"),
    "eps_basic": (("EarningsPerShareBasic",), "per_share"),
    "eps_diluted": (("EarningsPerShareDiluted",), "per_share"),
    "cfo": (("NetCashProvidedByUsedInOperatingActivities",), "usd"),
    "cfi": (("NetCashProvidedByUsedInInvestingActivities",), "usd"),
    "cff": (("NetCashProvidedByUsedInFinancingActivities",), "usd"),
    "net_change_cash": (
        ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
         "CashAndCashEquivalentsPeriodIncreaseDecrease"),
        "usd",
    ),
}

# Income statement targets: concept -> Bloomberg field codes (all filled when blank)
IS_TARGETS: dict[str, tuple[str, ...]] = {
    "revenue": ("SALES_REV_TURN", "IS_SALES_AND_SERVICES_REVENUES"),
    "cost_of_revenue": ("IS_COGS_TO_FE_AND_PP_AND_G", "IS_COG_AND_SERVICES_SOLD"),
    "gross_profit": ("GROSS_PROFIT",),
    "operating_income": ("IS_OPER_INC",),
    "net_income": ("NET_INCOME", "EARN_FOR_COMMON"),
    "eps_basic": ("IS_EPS", "IS_EARN_BEF_XO_ITEMS_PER_SH"),
    "eps_diluted": ("IS_DILUTED_EPS", "IS_DIL_EPS_BEF_XO"),
}
CF_TARGETS: dict[str, tuple[str, ...]] = {
    "net_income": ("CF_NET_INC",),
    "cfo": ("CF_CASH_FROM_OPER",),
    "cfi": ("CF_CASH_FROM_INV_ACT",),
    "cff": ("CFF_ACTIVITIES_DETAILED",),
    "net_change_cash": ("CF_NET_CHNG_CASH",),
}
# Where the margins live in columns K/L: (margin row code, numerator row code)
MARGINS = (("GROSS_PROFIT", "gross"), ("IS_OPER_INC", "operating"), ("EARN_FOR_COMMON", "net"))


@dataclass
class CumulativeFill:
    sheet: str
    cell: str
    concept: str
    value: float
    source: str
    method: str


@dataclass
class CumulativeReport:
    fills: list[CumulativeFill] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    margins: dict[str, Any] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.fills)


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def row_by_code(ws, code: str) -> int | None:
    for row in range(1, min(ws.max_row or 1, 200) + 1):
        if str(ws.cell(row, 2).value or "").strip() == code:
            return row
    return None


def sec_period_value(
    company_facts: dict[str, Any] | None, tags: tuple[str, ...], end: date | None, bucket: str | None, *, per_share: bool = False
) -> tuple[float, str] | None:
    """Value of a us-gaap flow fact for the exact period ending near `end` with the given length (3m, 6m, 9m).

    Returns (value in millions or per share, source text with filing and accession) or None."""
    if not company_facts or not tags or end is None or bucket is None:
        return None
    gaap = ((company_facts.get("facts") or {}).get("us-gaap")) or {}
    best: tuple[str, float, str] | None = None
    for tag in tags:
        units = (gaap.get(tag) or {}).get("units") or {}
        for unit, entries in units.items():
            if per_share != ("share" in unit.lower()) or (not per_share and unit != "USD"):
                continue
            for item in entries or []:
                form = str(item.get("form") or "")
                if form not in {"10-Q", "10-Q/A", "10-K", "10-K/A"} or item.get("val") is None:
                    continue
                period_end = _as_date(item.get("end"))
                if period_end is None or abs((period_end - end).days) > 5:
                    continue
                if duration_bucket(item.get("start"), item.get("end")) != bucket:
                    continue
                filed = str(item.get("filed") or "")
                if best is None or filed > best[0]:
                    value = float(item["val"]) if per_share else float(item["val"]) / 1_000_000.0
                    best = (filed, value, f"SEC {form} {item.get('accn') or ''} us-gaap:{tag}".strip())
    return (best[1], best[2]) if best else None


class NewCompanyCumulativeService:
    def apply(
        self,
        *,
        workbook_path: Path,
        company_facts: dict[str, Any] | None,
        latest_quarter: int | None,
        ticker: str | None = None,
        yahoo: Any | None = None,
    ) -> CumulativeReport:
        report = CumulativeReport()
        if latest_quarter not in BUCKET:
            report.skipped.append("Full fiscal year or unidentified quarter: no cumulative section to fill.")
            return report
        path = Path(workbook_path)
        wb = load_workbook(path, data_only=False)
        try:
            if LQ_IS not in wb.sheetnames or LQ_CF not in wb.sheetnames:
                report.skipped.append("Last Quarter IS or CF tab missing.")
                return report
            ledger = AdjustmentLedger(wb)
            notes: list[tuple[str, Any]] = []
            self._income_statement(wb, ledger, report, company_facts, latest_quarter, ticker, yahoo, notes)
            self._cash_flow(wb, ledger, report, company_facts, latest_quarter, ticker, yahoo, notes)
            self._margins(wb, report)
            if report.changed:
                for name in (LQ_IS, LQ_CF):
                    lines = [(label, text) for sheet, label, text in notes if sheet == name]
                    if lines:
                        HapAnalysisLayoutService().write_notes_section(wb[name], lines)
            if report.changed:
                wb.save(path)
        finally:
            wb.close()
        return report

    # ------------------------------------------------------------------ income statement
    def _income_statement(self, wb, ledger, report, facts, quarter, ticker, yahoo, notes) -> None:
        ws = wb[LQ_IS]
        bucket = BUCKET[quarter]
        columns = ((7, ws["C4"].value, "current year to date"), (8, ws["D4"].value, "prior year to date"))
        for col, end_raw, label in columns:
            end = _as_date(end_raw)
            values: dict[str, tuple[float, str, str]] = {}
            for concept in ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_basic", "eps_diluted"):
                found = self._sec(facts, concept, end, bucket)
                if found:
                    values[concept] = (found[0], found[1], "sec_10q")
            self._derive_income_lines(facts, end, bucket, values)
            for concept in ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_basic", "eps_diluted"):
                if concept not in values and yahoo is not None and ticker:
                    got = self._yahoo(yahoo, ticker, concept, end, quarter, ws, "C11")
                    if got:
                        values[concept] = (got[0], got[1], "yahoo_quarterly_sum")
            for concept, codes in IS_TARGETS.items():
                if concept not in values:
                    report.skipped.append(f"{LQ_IS} {label}: {concept} not found in SEC or Yahoo.")
                    continue
                value, source, method = values[concept]
                self._write(ws, ledger, report, concept, codes, col, value, source, method, label, concept_group="is")
            notes.append((LQ_IS, f"Cumulative source ({label})", self._source_note(values)))

    def _derive_income_lines(self, facts, end, bucket, values) -> None:
        """Gross profit and operating income when the filing has no such line (revenue less costs, as the template defines them)."""
        if "gross_profit" not in values and "revenue" in values and "cost_of_revenue" in values:
            values["gross_profit"] = (values["revenue"][0] - values["cost_of_revenue"][0], "derived: revenue - cost of revenue", "derived")
        if "operating_income" not in values and "revenue" in values and "cost_of_revenue" in values:
            sga = self._sec(facts, "sga", end, bucket)
            rd = self._sec(facts, "rd", end, bucket)
            if sga is not None and (rd is not None or not self._has_tag(facts, "ResearchAndDevelopmentExpense")):
                oi = values["revenue"][0] - values["cost_of_revenue"][0] - sga[0] - (rd[0] if rd else 0.0)
                values["operating_income"] = (oi, "derived: revenue - cost of goods sold - SG&A - R&D (SEC 10-Q)", "derived")

    # ------------------------------------------------------------------ cash flow
    def _cash_flow(self, wb, ledger, report, facts, quarter, ticker, yahoo, notes) -> None:
        ws = wb[LQ_CF]
        bucket = BUCKET[quarter]
        columns = ((3, ws["C4"].value, "current year to date"), (4, ws["D4"].value, "prior year to date"))
        for col, end_raw, label in columns:
            end = _as_date(end_raw)
            values: dict[str, tuple[float, str, str]] = {}
            for concept in CF_TARGETS:
                found = self._sec(facts, concept, end, bucket)
                if found:
                    values[concept] = (found[0], found[1], "sec_10q")
                elif yahoo is not None and ticker:
                    got = self._yahoo(yahoo, ticker, concept, end, quarter, wb[LQ_IS], "C11")
                    if got:
                        values[concept] = (got[0], got[1], "yahoo_quarterly_sum")
            for concept, codes in CF_TARGETS.items():
                if concept not in values:
                    report.skipped.append(f"{LQ_CF} {label}: {concept} not found in SEC or Yahoo.")
                    continue
                value, source, method = values[concept]
                self._write(ws, ledger, report, concept, codes, col, value, source, method, label, concept_group="cf")
            notes.append((LQ_CF, f"Cumulative source ({label})", self._source_note(values)))

    # ------------------------------------------------------------------ margins (columns K and L)
    def _margins(self, wb, report) -> None:
        """Gross, operating and net margin use the cumulative columns: K = G / revenue(G), L = H / revenue(H)."""
        ws = wb[LQ_IS]
        revenue_row = row_by_code(ws, "SALES_REV_TURN")
        if not revenue_row:
            return
        for code, name in MARGINS:
            row = row_by_code(ws, code)
            if not row:
                continue
            for out_col, src_col in (("K", "G"), ("L", "H")):
                cell = ws[f"{out_col}{row}"]
                expected = f"={src_col}{row}/{src_col}{revenue_row}"
                if cell.value != expected:
                    cell.value = expected
                    report.margins[f"{name}_{out_col}"] = "formula set"
                else:
                    report.margins[f"{name}_{out_col}"] = "formula present"

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _has_tag(facts, tag: str) -> bool:
        return bool((((facts or {}).get("facts") or {}).get("us-gaap") or {}).get(tag, {}).get("units"))

    @staticmethod
    def _sec(facts, concept: str, end: date | None, bucket: str) -> tuple[float, str] | None:
        tags, kind = SEC_TAGS[concept]
        return sec_period_value(facts, tags, end, bucket, per_share=(kind == "per_share"))

    @staticmethod
    def _yahoo(yahoo, ticker: str, concept: str, end: date | None, quarter: int, ws, anchor_cell: str) -> tuple[float, str] | None:
        try:
            return yahoo.ytd_value(ticker, concept, end, quarter, anchor_revenue=_num(ws[anchor_cell].value))
        except Exception:  # noqa: BLE001 - a Yahoo outage only means no fallback
            return None

    @staticmethod
    def _source_note(values: dict[str, tuple[float, str, str]]) -> str:
        parts = []
        for concept, (_v, source, method) in values.items():
            parts.append(f"{concept}: {source}" + (" (indicative)" if method == "yahoo_quarterly_sum" else ""))
        return "; ".join(parts) if parts else "not available"

    def _write(self, ws, ledger, report, concept, codes, col, value, source, method, label, *, concept_group) -> None:
        primary = True
        for code in codes:
            row = row_by_code(ws, code)
            if not row:
                continue
            cell = ws.cell(row, col)
            existing = cell.value
            if existing not in (None, ""):
                if isinstance(existing, str) and existing.startswith("="):
                    continue
                report.kept.append(f"{ws.title}!{cell.coordinate} already holds {existing}.")
                primary = False
                continue
            # secondary lines (leaf rows, continuing-operations EPS) only when the 3-month column shows the same figure
            if not primary and concept in ("eps_basic", "eps_diluted"):
                continue
            cell.value = round(value, 6)
            ledger.record(
                sheet=ws.title, cell=cell.coordinate, fiscal_year=None, category=CATEGORY,
                what=f"{label}: {concept.replace('_', ' ')}", original="blank", new=round(value, 6), amount=value,
                reason=f"Bloomberg gives only the 3-month quarter, so the {label} figure was filled ({method.replace('_', ' ')}).",
                source=source, method=method, confidence="high" if method == "sec_10q" else ("medium" if method == "derived" else "low"),
            )
            report.fills.append(CumulativeFill(ws.title, cell.coordinate, concept, value, source, method))
            primary = False
