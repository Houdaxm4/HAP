"""Ten-year share-repurchase dollars and shares, with derivation and analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.new_company import (
    BuybackAbsenceClass,
    BuybackAnalysis,
    BuybackYearResult,
    NewCompanyBuybackReport,
)
from services.annual_period_service import detect_year_columns
from services.sec_service import SecService

_DOLLAR_TAGS = (
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfEquity",
    "TreasuryStockValueAcquiredCostMethod",
    "StockRepurchasedDuringPeriodValue",
)
_SHARE_TAGS = (
    "StockRepurchasedDuringPeriodShares",
    "TreasuryStockSharesAcquired",
    "CommonStockSharesRepurchased",
)
_AVG_PRICE_TAGS = (
    "TreasuryStockAcquiredAverageCostPerShare",
    "StockRepurchasedDuringPeriodAverageCostPerShare",
)
_BEGIN_SHARES = ("CommonStockSharesOutstanding",)
_WAS_DILUTED = ("WeightedAverageNumberOfDilutedSharesOutstanding",)
_SBC_TAGS = ("AllocatedShareBasedCompensationExpense", "ShareBasedCompensation")
_FCF_PROXY = ("NetCashProvidedByUsedInOperatingActivities",)
_CAPEX = ("PaymentsToAcquirePropertyPlantAndEquipment",)


def _scale(val: float, *, shares: bool = False) -> float:
    if shares:
        return val / 1_000_000.0 if abs(val) >= 10_000 else val
    return val / 1_000_000.0 if abs(val) >= 10_000 else val


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


class NewCompanyBuybackService:
    DOLLARS_DEFINITION = (
        "gross_common_stock_repurchase_cash_outflow excluding employee tax-withholding "
        "when separately disclosed; includes excise tax only when the filing includes it "
        "in repurchase cost."
    )

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        market_cap: float | None = None,
        intrinsic_value: float | None = None,
    ) -> NewCompanyBuybackReport:
        sec = SecService()
        years: list[BuybackYearResult] = []
        warnings: list[str] = []
        sbc_total = 0.0
        fcf_total = 0.0
        dollars_total = 0.0

        for fy in fiscal_years:
            dollars, d_src = self._fact(sec, company_facts, fy, _DOLLAR_TAGS, scale=True)
            shares, s_src = self._fact(sec, company_facts, fy, _SHARE_TAGS, scale=True, shares=True)
            avg, a_src = self._fact(sec, company_facts, fy, _AVG_PRICE_TAGS, scale=False)
            begin, _ = self._fact(sec, company_facts, fy, _BEGIN_SHARES, scale=True, shares=True)
            was, _ = self._fact(sec, company_facts, fy, _WAS_DILUTED, scale=True, shares=True)
            sbc, _ = self._fact(sec, company_facts, fy, _SBC_TAGS, scale=True)
            cfo, _ = self._fact(sec, company_facts, fy, _FCF_PROXY, scale=True)
            capex, _ = self._fact(sec, company_facts, fy, _CAPEX, scale=True)
            derived = False
            formula = None
            if shares is None and dollars is not None and avg not in (None, 0):
                shares = dollars / avg
                derived = True
                formula = "repurchase_dollars / average_repurchase_price"
                s_src = f"derived:{a_src}"
            absence = None
            if dollars is None and shares is None:
                absence = BuybackAbsenceClass.NOT_DISCLOSED
                warnings.append(f"BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: {fy}")
                warnings.append(f"BUYBACK_SHARES_COVERAGE_INCOMPLETE: {fy}")
            elif dollars == 0 and (shares is None or shares == 0):
                absence = BuybackAbsenceClass.REPORTED_ZERO
            if dollars is None and shares is not None:
                warnings.append(f"BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: {fy}")
            if shares is None and dollars is not None and not derived:
                warnings.append(f"BUYBACK_SHARES_COVERAGE_INCOMPLETE: {fy}")
            if derived:
                warnings.append(f"BUYBACK_SHARES_DERIVED: {fy}")

            year_warnings: list[str] = []
            if begin is not None and shares is not None and was is not None:
                # Ending ≈ WAS as a coarse check only; do not use Δshares as buybacks.
                pass
            if sbc:
                sbc_total += sbc
            fcf = None
            if cfo is not None:
                fcf = cfo - abs(capex or 0.0)
                fcf_total += fcf
            if dollars:
                dollars_total += dollars

            years.append(
                BuybackYearResult(
                    fiscal_year=fy,
                    dollars=dollars,
                    shares=shares,
                    average_price=avg if avg is not None else (
                        (dollars / shares) if dollars and shares else None
                    ),
                    dollars_source=d_src,
                    shares_source=s_src,
                    shares_derived=derived,
                    derivation_formula=formula,
                    dollars_definition=self.DOLLARS_DEFINITION,
                    exclusions=[
                        "employee_share_withholding_when_separately_disclosed",
                        "share_issuance_proceeds",
                        "acquisition_related_share_activity",
                        "change_in_shares_outstanding_not_used_as_buyback",
                    ],
                    beginning_shares=begin,
                    ending_shares=was,
                    absence_class=absence,
                    confidence=0.5 if derived else (0.85 if dollars is not None else 0.2),
                    warnings=year_warnings,
                )
            )

        first_was = next((y.ending_shares for y in years if y.ending_shares is not None), None)
        last_was = next((y.ending_shares for y in reversed(years) if y.ending_shares is not None), None)
        share_chg = None
        if first_was is not None and last_was is not None:
            share_chg = last_was - first_was
        cum_shares = sum(y.shares or 0.0 for y in years)
        sbc_offset = bool(sbc_total and dollars_total and sbc_total > 0.25 * dollars_total)
        funded = None
        if dollars_total:
            if fcf_total >= dollars_total:
                funded = "free_cash_flow"
            elif fcf_total > 0:
                funded = "free_cash_flow_and_cash_balances"
            else:
                funded = "cash_balances_or_debt"
        vs_iv = None
        prices = [y.average_price for y in years if y.average_price]
        if intrinsic_value and prices:
            avg_px = sum(prices) / len(prices)
            vs_iv = "created_per_share_value" if avg_px < intrinsic_value else "likely_destroyed_per_share_value"
        analysis = BuybackAnalysis(
            cumulative_dollars=dollars_total or None,
            cumulative_shares=cum_shares or None,
            diluted_share_count_change=share_chg,
            sbc_offset_material=sbc_offset,
            funded_by=funded,
            value_created_or_destroyed=vs_iv,
            notes=[
                "Large repurchase dollars are not by themselves shareholder-friendly.",
                "Change in shares outstanding is not used as the buyback measure.",
            ]
            + (["Stock-based compensation materially offset share reduction."] if sbc_offset else []),
        )
        self._write_inputs(workbook_path, years)
        complete = all(
            y.absence_class in {BuybackAbsenceClass.REPORTED_ZERO, BuybackAbsenceClass.NOT_APPLICABLE}
            or (y.dollars is not None and (y.shares is not None or y.shares_derived))
            or y.absence_class == BuybackAbsenceClass.NOT_DISCLOSED
            for y in years
        )
        return NewCompanyBuybackReport(
            analysis_id=analysis_id,
            ticker=ticker,
            years=years,
            analysis=analysis,
            complete=complete,
            warnings=warnings,
            summary=(
                f"Buybacks: cumulative_dollars={dollars_total}; cumulative_shares={cum_shares}; "
                f"sbc_offset={sbc_offset}; funded_by={funded}."
            ),
        )

    @staticmethod
    def _fact(
        sec: SecService,
        company_facts: dict[str, Any] | None,
        fy: str,
        tags: tuple[str, ...],
        *,
        scale: bool,
        shares: bool = False,
    ) -> tuple[float | None, str | None]:
        if not company_facts:
            return None, None
        for tag in tags:
            fact = sec.find_fact(company_facts, tag, fy, xbrl_tag_hint=tag)
            if fact is None or fact.value is None:
                continue
            val = float(fact.value)
            if scale:
                val = _scale(val, shares=shares)
            return val, f"sec_xbrl:{tag}"
        return None, None

    @staticmethod
    def _write_inputs(path: Path, years: list[BuybackYearResult]) -> None:
        wb = load_workbook(path, data_only=False)
        try:
            if "Inputs" not in wb.sheetnames:
                return
            ws = wb["Inputs"]
            cols = detect_year_columns(ws, wb)
            d_row = s_row = None
            for row in range(1, min(ws.max_row or 1, 130) + 1):
                lab = str(ws.cell(row, 1).value or "").strip().lower()
                if lab in {"buybacks", "share repurchases", "repurchase of common stock"}:
                    d_row = row
                if lab in {"shares repurchased", "buyback shares"}:
                    s_row = row
            for y in years:
                col = cols.get(y.fiscal_year)
                if not col:
                    continue
                if d_row and y.dollars is not None:
                    cell = ws.cell(d_row, col)
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        if cell.value in (None, ""):
                            cell.value = y.dollars
                if s_row and y.shares is not None:
                    cell = ws.cell(s_row, col)
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        if cell.value in (None, ""):
                            cell.value = y.shares
            wb.save(path)
        finally:
            wb.close()
