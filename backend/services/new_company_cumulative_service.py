"""New Company: fill the cumulative (year-to-date) sections of the Last Quarter income statement and cash flow tabs.

Bloomberg gives only the 3-month quarter. The analyst needs the year-to-date figures too, and the margins in columns K and L
(gross, operating and net margin) are built from them. Source order: SEC 10-Q company facts (exact period end and length), then
Yahoo Finance quarterly figures added up over the fiscal year to date (headline lines only; flagged as indicative).

The whole statement is filled, not only the headline lines, so that every "check" row on the tab ties to zero and the error cell
(IS tab L1, CF tab H1) shows 0 and turns green. Lines the filing does not give separately are the remainder after the reported lines.

Income statement tab (columns G current year to date, H prior-year to date) and cash flow tab (columns C and D).
Rows are found by the Bloomberg field code in column B, so section titles are never written to. Only blank cells are filled.
Notes go in the tab's single Notes block (column D, because column B is hidden); every filled column is listed in HAP Adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill

from services.adjustment_ledger_service import AdjustmentLedger
from services.sec_10q_statement_service import duration_bucket
from services.tab_notes import add_notes, fmt_period, note

LQ_IS = "Last Quarter IS Standardized"
LQ_CF = "Last Quarter CF Standardized"
BUCKET = {1: "3m", 2: "6m", 3: "9m"}
CATEGORY = "Cumulative from 10-Q"
FILL = PatternFill("solid", fgColor="E6F4EA")
GREEN = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
RED = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")

# concept -> (SEC tags, sign applied to the SEC value, unit kind)
SEC: dict[str, tuple[tuple[str, ...], int, str]] = {
    "revenue": (("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"), 1, "usd"),
    "cost_of_revenue": (("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"), 1, "usd"),
    "gross_profit": (("GrossProfit",), 1, "usd"),
    "operating_income": (("OperatingIncomeLoss",), 1, "usd"),
    "sga": (("SellingGeneralAndAdministrativeExpense",), 1, "usd"),
    "rd": (("ResearchAndDevelopmentExpense",), 1, "usd"),
    "interest_expense": (("InterestExpense", "InterestExpenseNonoperating"), 1, "usd"),
    "interest_income": (("InvestmentIncomeInterest", "InterestIncomeOther", "InterestAndOtherIncome"), 1, "usd"),
    "pretax": (("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"), 1, "usd"),
    "tax": (("IncomeTaxExpenseBenefit",), 1, "usd"),
    "net_income": (("NetIncomeLoss", "ProfitLoss"), 1, "usd"),
    "eps_basic": (("EarningsPerShareBasic",), 1, "per_share"),
    "eps_diluted": (("EarningsPerShareDiluted",), 1, "per_share"),
    "cfo": (("NetCashProvidedByUsedInOperatingActivities",), 1, "usd"),
    "cfi": (("NetCashProvidedByUsedInInvestingActivities",), 1, "usd"),
    "cff": (("NetCashProvidedByUsedInFinancingActivities",), 1, "usd"),
    "net_change_cash": (("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
                         "CashAndCashEquivalentsPeriodIncreaseDecrease"), 1, "usd"),
    "da": (("DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"), 1, "usd"),
    "sbc": (("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"), 1, "usd"),
    "deferred_tax": (("DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits"), 1, "usd"),
    "ar": (("IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInAccountsAndOtherReceivables"), -1, "usd"),
    "inventory": (("IncreaseDecreaseInInventories",), -1, "usd"),
    "ap": (("IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities"), 1, "usd"),
    "capex": (("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"), -1, "usd"),
    "ppe_sale": (("ProceedsFromSaleOfPropertyPlantAndEquipment",), 1, "usd"),
    "acquisitions": (("PaymentsToAcquireBusinessesNetOfCashAcquired",), -1, "usd"),
    "divestitures": (("ProceedsFromDivestitureOfBusinessesNetOfCashDivested", "ProceedsFromDivestitureOfBusinesses"), 1, "usd"),
    "dividends": (("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), -1, "usd"),
    "st_debt": (("ProceedsFromRepaymentsOfShortTermDebt", "ProceedsFromRepaymentsOfCommercialPaper"), 1, "usd"),
    "lt_proceeds": (("ProceedsFromIssuanceOfLongTermDebt",), 1, "usd"),
    "lt_repay": (("RepaymentsOfLongTermDebt",), -1, "usd"),
    "repurchase": (("PaymentsForRepurchaseOfCommonStock",), -1, "usd"),
    "issuance": (("ProceedsFromIssuanceOfCommonStock", "ProceedsFromStockOptionsExercised"), 1, "usd"),
    "fx": (("EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "EffectOfExchangeRateOnCashAndCashEquivalents"), 1, "usd"),
}
IS_CONCEPTS = ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "sga", "rd", "interest_expense", "interest_income",
               "pretax", "tax", "net_income", "eps_basic", "eps_diluted")
CF_CONCEPTS = ("net_income", "cfo", "cfi", "cff", "net_change_cash", "da", "sbc", "deferred_tax", "ar", "inventory", "ap", "capex",
               "ppe_sale", "acquisitions", "divestitures", "dividends", "st_debt", "lt_proceeds", "lt_repay", "repurchase", "issuance", "fx")
HEADLINE_IS = ("revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_basic", "eps_diluted")
HEADLINE_CF = ("net_income", "cfo", "cfi", "cff", "net_change_cash")


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
    error_cells: dict[str, Any] = field(default_factory=dict)

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
            used = {"is": {"derived": [], "yahoo": [], "plug": []}, "cf": {"derived": [], "yahoo": [], "plug": []}}
            self._income_statement(wb, ledger, report, company_facts, latest_quarter, ticker, yahoo, used["is"])
            self._cash_flow(wb, ledger, report, company_facts, latest_quarter, ticker, yahoo, used["cf"])
            self._margins(wb, report)
            self._error_cells(wb, report)
            if report.changed:
                self._notes(wb, latest_quarter, used)
            wb.save(path)
        finally:
            wb.close()
        return report

    # ------------------------------------------------------------------ income statement
    def _income_statement(self, wb, ledger, report, facts, quarter, ticker, yahoo, used) -> None:
        ws = wb[LQ_IS]
        bucket = BUCKET[quarter]
        for col, end_raw, label in ((7, ws["C4"].value, "current year to date"), (8, ws["D4"].value, "prior year to date")):
            end = _as_date(end_raw)
            vals: dict[str, float] = {}
            how: dict[str, str] = {}
            for concept in IS_CONCEPTS:
                found = self._sec(facts, concept, end, bucket)
                if found:
                    vals[concept], how[concept] = found[0], "sec_10q"
            if "gross_profit" not in vals and "revenue" in vals and "cost_of_revenue" in vals:
                vals["gross_profit"], how["gross_profit"] = vals["revenue"] - vals["cost_of_revenue"], "derived"
            if "operating_income" not in vals and "gross_profit" in vals and "sga" in vals and (
                "rd" in vals or not self._has_tag(facts, "ResearchAndDevelopmentExpense")
            ):
                vals["operating_income"] = vals["gross_profit"] - vals["sga"] - vals.get("rd", 0.0)
                how["operating_income"] = "derived"
                if "operating income" not in used["derived"]:
                    used["derived"].append("operating income")
            for concept in HEADLINE_IS:
                if concept not in vals and yahoo is not None and ticker:
                    got = self._yahoo(yahoo, ticker, concept, end, quarter, ws, "C11")
                    if got:
                        vals[concept], how[concept] = got[0], "yahoo_quarterly_sum"
                        used["yahoo"].append(concept.replace("_", " "))
            lines = self._income_lines(vals, used)
            if not self._write_lines(ws, ledger, report, lines, col, how, label):
                report.skipped.append(f"{LQ_IS} {label}: nothing to fill.")

    @staticmethod
    def _income_lines(v: dict[str, float], used) -> dict[str, tuple[float, str]]:
        """Bloomberg field code -> (value, concept). The full statement, so every check row on the tab ties to zero."""
        out: dict[str, tuple[float, str]] = {}

        def put(code: str, value: float | None, concept: str) -> None:
            if value is not None:
                out[code] = (value, concept)

        put("SALES_REV_TURN", v.get("revenue"), "revenue")
        put("IS_SALES_AND_SERVICES_REVENUES", v.get("revenue"), "revenue")
        put("IS_COGS_TO_FE_AND_PP_AND_G", v.get("cost_of_revenue"), "cost_of_revenue")
        put("IS_COG_AND_SERVICES_SOLD", v.get("cost_of_revenue"), "cost_of_revenue")
        put("GROSS_PROFIT", v.get("gross_profit"), "gross_profit")
        put("IS_OPER_INC", v.get("operating_income"), "operating_income")
        if "gross_profit" in v and "operating_income" in v:
            opex = v["gross_profit"] - v["operating_income"]
            sga, rd = v.get("sga", 0.0), v.get("rd", 0.0)
            put("IS_OPERATING_EXPN", opex, "operating_expenses")
            if "sga" in v:
                put("IS_SG&A_EXPENSE", sga, "sga")
            if "rd" in v:
                put("IS_OPERATING_EXPENSES_R&D", rd, "rd")
            other = opex - sga - rd
            if abs(other) > 0.0005:
                put("OTHER_OPERATING_EXPENSES_RATIO", other, "other_operating_expenses")
        pretax = v.get("pretax")
        if pretax is None and "net_income" in v and "tax" in v:
            pretax = v["net_income"] + v["tax"]
        if pretax is not None and "operating_income" in v:
            nonop = v["operating_income"] - pretax
            put("PRETAX_INC", pretax, "pretax")
            put("NONOP_INCOME_LOSS", nonop, "non_operating")
            if "interest_expense" in v:
                net_interest = v["interest_expense"] - v.get("interest_income", 0.0)
                put("IS_NET_INTEREST_EXPENSE", net_interest, "interest")
                put("IS_INT_EXPENSE", v["interest_expense"], "interest")
                if "interest_income" in v:
                    put("IS_INT_INC", v["interest_income"], "interest")
                rest = nonop - net_interest
            else:
                rest = nonop
            if abs(rest) > 0.0005:
                put("OTHER_NONOP_INCOME_LOSS", rest, "other_non_operating")
            if "tax" in v:
                put("IS_INC_TAX_EXP", v["tax"], "tax")
                if "net_income" in v:
                    affiliates = pretax - v["tax"] - v["net_income"]
                    if abs(affiliates) > 0.0005:
                        put("IS_SH_PRO_EQY_MT_INV_NET_OF_TAX", affiliates, "affiliates")
        if "net_income" in v:
            ni = v["net_income"]
            put("IS_INC_BEF_XO_ITEM", ni, "net_income")
            put("NI_INCLUDING_MINORITY_INT_RATIO", ni, "net_income")
            put("NET_INCOME", ni, "net_income")
            put("EARN_FOR_COMMON", ni, "net_income")
        put("IS_EPS", v.get("eps_basic"), "eps_basic")
        put("IS_DILUTED_EPS", v.get("eps_diluted"), "eps_diluted")
        return out

    # ------------------------------------------------------------------ cash flow
    def _cash_flow(self, wb, ledger, report, facts, quarter, ticker, yahoo, used) -> None:
        ws = wb[LQ_CF]
        bucket = BUCKET[quarter]
        for col, end_raw, label in ((3, ws["C4"].value, "current year to date"), (4, ws["D4"].value, "prior year to date")):
            end = _as_date(end_raw)
            vals: dict[str, float] = {}
            how: dict[str, str] = {}
            for concept in CF_CONCEPTS:
                found = self._sec(facts, concept, end, bucket)
                if found:
                    vals[concept], how[concept] = found[0], "sec_10q"
            for concept in HEADLINE_CF:
                if concept not in vals and yahoo is not None and ticker:
                    got = self._yahoo(yahoo, ticker, concept, end, quarter, wb[LQ_IS], "C11")
                    if got:
                        vals[concept], how[concept] = got[0], "yahoo_quarterly_sum"
                        used["yahoo"].append(concept.replace("_", " "))
            # totals already on the tab (from the earlier SEC step) take precedence so the detail ties to them
            for concept, code in (("cfo", "CF_CASH_FROM_OPER"), ("cfi", "CF_CASH_FROM_INV_ACT"), ("cff", "CFF_ACTIVITIES_DETAILED")):
                row = row_by_code(ws, code)
                existing = _num(ws.cell(row, col).value) if row else None
                if existing is not None:
                    vals[concept] = existing
            lines = self._cash_flow_lines(vals)
            if not self._write_lines(ws, ledger, report, lines, col, how, label):
                report.skipped.append(f"{LQ_CF} {label}: nothing to fill.")

    @staticmethod
    def _cash_flow_lines(v: dict[str, float]) -> dict[str, tuple[float, str]]:
        out: dict[str, tuple[float, str]] = {}

        def put(code: str, value: float | None, concept: str) -> None:
            if value is not None:
                out[code] = (value, concept)

        put("CF_NET_INC", v.get("net_income"), "net_income")
        put("CF_CASH_FROM_OPER", v.get("cfo"), "cfo")
        if "net_income" in v and "cfo" in v:
            da = v.get("da", 0.0)
            sbc, deferred = v.get("sbc", 0.0), v.get("deferred_tax", 0.0)
            wc = v.get("ar", 0.0) + v.get("inventory", 0.0) + v.get("ap", 0.0)
            other = v["cfo"] - v["net_income"] - da - sbc - deferred - wc
            if "da" in v:
                put("CF_DEPR_AMORT", da, "da")
            if "sbc" in v:
                put("CF_STOCK_BASED_COMPENSATION", sbc, "sbc")
            if "deferred_tax" in v:
                put("CF_DEF_INC_TAX", deferred, "deferred_tax")
            put("OTHER_NON_CASH_ADJ_LESS_DETAILED", other, "other_non_cash")
            put("NON_CASH_ITEMS_DETAILED", sbc + deferred + other, "non_cash")
            if any(k in v for k in ("ar", "inventory", "ap")):
                put("CF_CHNG_NON_CASH_WORK_CAP", wc, "working_capital")
                if "ar" in v:
                    put("CF_ACCT_RCV_UNBILLED_REV", v["ar"], "ar")
                if "inventory" in v:
                    put("CF_CHANGE_IN_INVENTORIES", v["inventory"], "inventory")
                if "ap" in v:
                    put("CF_CHANGE_IN_ACCOUNTS_PAYABLE", v["ap"], "ap")
        put("CF_CASH_FROM_INV_ACT", v.get("cfi"), "cfi")
        if "cfi" in v:
            parts = 0.0
            if "capex" in v or "ppe_sale" in v:
                capex, sale = v.get("capex", 0.0), v.get("ppe_sale", 0.0)
                if "capex" in v:
                    put("CF_PURCHASE_OF_FIXED_PROD_ASSETS", capex, "capex")
                    put("ACQUIS_FXD_&_INTANG_DETAILED", capex, "capex")
                if "ppe_sale" in v:
                    put("CF_DISPOSAL_OF_FIXED_PROD_ASSETS", sale, "ppe_sale")
                    put("DISP_FXD_&_INTANGIBLES_DETAILED", sale, "ppe_sale")
                put("CHG_IN_FXD_&_INTANG_AST_DETAILED", capex + sale, "capex")
                parts += capex + sale
            if "acquisitions" in v or "divestitures" in v:
                acq, div = v.get("acquisitions", 0.0), v.get("divestitures", 0.0)
                if "acquisitions" in v:
                    put("CF_CASH_FOR_ACQUIS_SUBSIDIARIES", acq, "acquisitions")
                if "divestitures" in v:
                    put("CF_CASH_FOR_DIVESTITURES", div, "divestitures")
                put("CF_NT_CSH_RCVD_PD_FOR_ACQUIS_DIV", acq + div, "acquisitions")
                parts += acq + div
            other_inv = v["cfi"] - parts
            if abs(other_inv) > 0.0005:
                put("OTHER_INVESTING_ACT_DETAILED", other_inv, "other_investing")
        put("CFF_ACTIVITIES_DETAILED", v.get("cff"), "cff")
        if "cff" in v:
            parts = 0.0
            if "dividends" in v:
                put("CF_DVD_PAID", v["dividends"], "dividends")
                parts += v["dividends"]
            debt_found = [k for k in ("st_debt", "lt_proceeds", "lt_repay") if k in v]
            if debt_found:
                for key, code in (("st_debt", "CF_NET_CHG_IN_ST_DBT_&_CPTL_LEAS"), ("lt_proceeds", "CF_PROC_LT_DEBT_&_CAPITAL_LEASE"),
                                  ("lt_repay", "CF_PYMT_LT_DEBT_&_CAPITAL_LEASE")):
                    if key in v:
                        put(code, v[key], key)
                debt = sum(v[k] for k in debt_found)
                put("PROC_FR_REPAYMNTS_BOR_DETAILED", debt, "debt")
                parts += debt
            if "repurchase" in v or "issuance" in v:
                eq = v.get("repurchase", 0.0) + v.get("issuance", 0.0)
                if "issuance" in v:
                    put("CF_INCR_CAP_STOCK", v["issuance"], "issuance")
                if "repurchase" in v:
                    put("CF_DECR_CAP_STOCK", v["repurchase"], "repurchase")
                put("PROC_FR_REPURCH_EQTY_DETAILED", eq, "equity")
                parts += eq
            other_fin = v["cff"] - parts
            if abs(other_fin) > 0.0005:
                put("CF_OTHER_FINANCING_ACT_EXCL_FX", other_fin, "other_financing")
        put("CF_EFFECT_FOREIGN_EXCHANGES", v.get("fx"), "fx")
        put("CF_NET_CHNG_CASH", v.get("net_change_cash"), "net_change_cash")
        return out

    # ------------------------------------------------------------------ writing
    def _write_lines(self, ws, ledger, report, lines: dict[str, tuple[float, str]], col: int, how: dict[str, str], label: str) -> int:
        filled: list[str] = []
        sources: set[str] = set()
        for code, (value, concept) in lines.items():
            row = row_by_code(ws, code)
            if not row:
                continue
            cell = ws.cell(row, col)
            existing = cell.value
            if isinstance(existing, (int, float)) and not isinstance(existing, bool) and existing == 0 and abs(value) > 0.0005:
                existing = None  # the template leaves 0 in an empty year-to-date column; that is not a reported figure
            if existing not in (None, ""):
                if not (isinstance(existing, str) and existing.startswith("=")):
                    report.kept.append(f"{ws.title}!{cell.coordinate} already holds {existing}.")
                continue
            cell.value = round(value, 6)
            cell.fill = FILL
            method = how.get(concept, "derived")
            sources.add(method)
            filled.append(cell.coordinate)
            report.fills.append(CumulativeFill(ws.title, cell.coordinate, concept, value, method, method))
        if filled:
            from_yahoo = "yahoo_quarterly_sum" in sources
            ledger.record(
                sheet=ws.title, cell=filled[0], fiscal_year=None, category=CATEGORY,
                what=f"{label.capitalize()} column: {len(filled)} lines filled", original="blank", new=f"{len(filled)} figures", amount=None,
                reason="Bloomberg gives only the three-month quarter; the year-to-date column was completed so the statement and its check lines tie.",
                source="SEC 10-Q filing" + (" and Yahoo Finance quarters (indicative)" if from_yahoo else ""),
                method="yahoo_quarterly_sum" if from_yahoo else "sec_10q", confidence="medium" if from_yahoo else "high",
                mark_cell=False,
            )
        return len(filled)

    # ------------------------------------------------------------------ margins (columns K and L)
    def _margins(self, wb, report) -> None:
        """Gross, operating and net margin use the cumulative columns: K = G / revenue(G), L = H / revenue(H)."""
        ws = wb[LQ_IS]
        revenue_row = row_by_code(ws, "SALES_REV_TURN")
        if not revenue_row:
            return
        for code, name in (("GROSS_PROFIT", "gross"), ("IS_OPER_INC", "operating"), ("EARN_FOR_COMMON", "net")):
            row = row_by_code(ws, code)
            if not row:
                continue
            for out_col, src_col in (("K", "G"), ("L", "H")):
                cell = ws[f"{out_col}{row}"]
                expected = f"={src_col}{row}/{src_col}{revenue_row}"
                report.margins[f"{name}_{out_col}"] = "formula present" if cell.value == expected else "formula set"
                cell.value = expected
                cell.number_format = "0.0%"

    # ------------------------------------------------------------------ error cells: 0 and green
    def _error_cells(self, wb, report) -> None:
        """IS tab L1 and CF tab H1 count the check lines that do not tie. Green when 0, red otherwise (live, not painted)."""
        for sheet, addr in ((LQ_IS, "L1"), (LQ_CF, "H1")):
            ws = wb[sheet]
            existing = [r for rng, rules in ws.conditional_formatting._cf_rules.items() if addr in str(rng.sqref) for r in rules]
            has_green = any(getattr(r, "operator", None) == "equal" and r.formula == ["0"] for r in existing)
            has_red = any(getattr(r, "operator", None) in {"notEqual", "greaterThan"} for r in existing)
            if not has_green:
                ws.conditional_formatting.add(addr, CellIsRule(operator="equal", formula=["0"], fill=GREEN))
            if not has_red:
                ws.conditional_formatting.add(addr, CellIsRule(operator="greaterThan", formula=["0"], fill=RED))
            report.error_cells[sheet] = addr

    # ------------------------------------------------------------------ notes
    def _notes(self, wb, quarter: int, used) -> None:
        ws_is, ws_cf = wb[LQ_IS], wb[LQ_CF]
        year = ws_is["C4"].value.year if hasattr(ws_is["C4"].value, "year") else ""
        tenq = f"the company's 10-Q for {fmt_period(f'FY{year} Q{quarter}')}"
        for ws, kind, name in ((ws_is, "is", "income statement"), (ws_cf, "cf", "cash flow statement")):
            lines = [
                note(f"The year-to-date columns of the {name} were filled", "Bloomberg gives only the three-month quarter", tenq),
                note(
                    "Every line was filled so the check lines add up and the error count shows 0",
                    "lines the filing does not give separately are shown as what remains after the reported lines",
                    tenq,
                ),
            ]
            if kind == "is":
                if used["is"]["derived"]:
                    lines.append(note("Operating income was calculated as revenue minus cost of goods sold, SG&A and R&D",
                                      "the company does not report an operating income line", tenq))
                lines.append(note("The margins in columns K and L were recalculated from the year-to-date figures",
                                  "margins should compare the same period in both years", tenq))
            if used[kind]["yahoo"]:
                lines.append(note(f"Some figures ({', '.join(sorted(set(used[kind]['yahoo'])))}) were taken from Yahoo Finance",
                                  "the SEC filing did not give them and they are indicative", "Yahoo Finance quarterly figures added up for the year to date"))
            add_notes(ws, lines, replace_containing=("year-to-date columns of the", "Every line was filled", "Operating income was calculated",
                                                      "margins in columns K and L", "were taken from Yahoo Finance"))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _has_tag(facts, tag: str) -> bool:
        return bool((((facts or {}).get("facts") or {}).get("us-gaap") or {}).get(tag, {}).get("units"))

    @staticmethod
    def _sec(facts, concept: str, end: date | None, bucket: str) -> tuple[float, str] | None:
        tags, sign, kind = SEC[concept]
        got = sec_period_value(facts, tags, end, bucket, per_share=(kind == "per_share"))
        return (sign * got[0], got[1]) if got else None

    @staticmethod
    def _yahoo(yahoo, ticker: str, concept: str, end: date | None, quarter: int, ws, anchor_cell: str) -> tuple[float, str] | None:
        try:
            return yahoo.ytd_value(ticker, concept, end, quarter, anchor_revenue=_num(ws[anchor_cell].value))
        except Exception:  # noqa: BLE001 - a Yahoo outage only means no fallback
            return None
