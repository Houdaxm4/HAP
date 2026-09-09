"""Semantic extraction of Expected Returns and Enterprise Value workbook outputs.

Requires Excel-recalculated cached values for formula cells. Never substitutes
Inputs!B69 (Bloomberg CRF 'Expected Return @ Current Price') for Expected
Returns!E14/F14.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import AnnualValuationOutputs
from services.annual_period_service import detect_year_columns

_WS = re.compile(r"\s+")
_FORMULA_ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")


def _norm(label: Any) -> str:
    return _WS.sub(" ", str(label or "").strip().lower())


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        if any(tok in v for tok in _FORMULA_ERRORS):
            return None
        text = v.strip().replace(",", "").replace("%", "")
        try:
            return float(text)
        except ValueError:
            return None
    return None


class AnnualValuationExtractService:
    def extract(
        self,
        workbook_path: Path,
        *,
        expected_return_validation: dict[str, Any] | None = None,
        valuation_validation: dict[str, Any] | None = None,
        recalculation_complete: bool = False,
        pe10_fiscal: float | None = None,
        pe10_fiscal_label: str | None = None,
        pe10_fiscal_as_of: str | None = None,
        pe10_current: float | None = None,
        pe10_current_as_of: str | None = None,
    ) -> AnnualValuationOutputs:
        # data_only=True reads Excel-cached calculated results after recalc.
        wb = load_workbook(workbook_path, data_only=True)
        wb_f = load_workbook(workbook_path, data_only=False)
        out = AnnualValuationOutputs(recalculation_complete=recalculation_complete)
        try:
            if pe10_fiscal is not None:
                out.pe10_fiscal_year = float(pe10_fiscal)
                out.pe10_fiscal_year_label = pe10_fiscal_label
                out.pe10_fiscal_as_of = pe10_fiscal_as_of
                out.sources["pe10_fiscal_year"] = f"Inputs historical PE10 ({pe10_fiscal_label})"
            if pe10_current is not None:
                out.current_pe10 = float(pe10_current)
                out.current_pe10_as_of = pe10_current_as_of
                out.sources["current_pe10"] = "Inputs!B65 Current PE10 (CRF)"

            if "Inputs" in wb.sheetnames:
                inp = wb["Inputs"]
                price = _num(inp["B63"].value)
                if price is not None:
                    out.current_price = price
                    out.sources["current_price"] = "Inputs!B63"
                if out.current_pe10 is None:
                    cur = _num(inp["B65"].value)
                    if cur is not None:
                        out.current_pe10 = cur
                        out.sources["current_pe10"] = "Inputs!B65"
                max_pe = _num(inp["B66"].value)
                if max_pe is not None:
                    out.max_pe10 = max_pe
                    out.sources["max_pe10"] = "Inputs!B66"
                max_buy = _num(inp["B67"].value)
                if max_buy is not None:
                    out.max_buy = max_buy
                    out.sources["max_buy"] = "Inputs!B67"
                # Distinct Bloomberg CRF metrics — never aliases for E14/F14.
                bb69 = _num(inp["B69"].value)
                if bb69 is not None:
                    out.bloomberg_expected_return_at_current_price = bb69
                    out.sources["bloomberg_expected_return_at_current_price"] = (
                        "Inputs!B69 Expected Return @ Current Price (Bloomberg CRF proprietary)"
                    )
                bb70 = _num(inp["B70"].value)
                if bb70 is not None:
                    out.bloomberg_expected_return_with_dividends_at_current_price = bb70
                    out.sources["bloomberg_expected_return_with_dividends_at_current_price"] = (
                        "Inputs!B70 Expected Return Price Plus Dividends - Given Current Price (Bloomberg CRF)"
                    )

            er_name = next((n for n in wb.sheetnames if "expected return" in n.lower()), None)
            if er_name:
                er = wb[er_name]
                e14 = _num(er["E14"].value)
                f14 = _num(er["F14"].value)
                if e14 is not None:
                    out.expected_annual_return = e14
                    out.sources["expected_annual_return"] = f"{er_name}!E14"
                elif recalculation_complete:
                    out.warnings.append(
                        "WORKBOOK_RECALCULATION_INCOMPLETE: Expected Returns!E14 has no cached numeric result."
                    )
                else:
                    out.warnings.append(
                        "WORKBOOK_RECALCULATION_INCOMPLETE: Expected Returns!E14 requires Excel recalculation."
                    )
                if f14 is not None:
                    out.expected_return_with_dividends = f14
                    out.sources["expected_return_with_dividends"] = f"{er_name}!F14"
                elif recalculation_complete:
                    out.warnings.append(
                        "WORKBOOK_RECALCULATION_INCOMPLETE: Expected Returns!F14 has no cached numeric result."
                    )
                else:
                    out.warnings.append(
                        "WORKBOOK_RECALCULATION_INCOMPLETE: Expected Returns!F14 requires Excel recalculation."
                    )

            ev_name = next((n for n in wb.sheetnames if "enterprise value" in n.lower()), None)
            if ev_name:
                ev = wb[ev_name]
                mapping = {
                    "company_value_per_share": ("B20",),
                    "enterprise_mos": ("B27",),
                    "price_at_mos": ("B32",),
                    "current_graham_intrinsic_value": ("B42",),
                    "graham_expected_annualized_return": ("B47",),
                    "graham_target_return_entry_price": ("B48",),
                    "graham_target_annualized_return": ("B53",),
                    "owner_earnings_growth": ("B6",),
                    "owner_earnings_growth_annualized": ("C6",),
                }
                for attr, cells in mapping.items():
                    for addr in cells:
                        val = _num(ev[addr].value)
                        if val is not None:
                            setattr(out, attr, val)
                            out.sources[attr] = f"{ev_name}!{addr}"
                            break
                out.graham_projection_horizon_years = 7
                # MOS entry price = current Graham IV * (1 - selected MOS), typically 25%.
                mos_threshold = _num(ev["B30"].value) if "B30" in ev else 0.25
                if mos_threshold is None:
                    mos_threshold = 0.25
                if out.current_graham_intrinsic_value is not None:
                    out.graham_margin_of_safety_entry_price = out.current_graham_intrinsic_value * (
                        1.0 - float(mos_threshold)
                    )
                    out.sources["graham_margin_of_safety_entry_price"] = (
                        f"{ev_name}!B42*(1-B30) margin-of-safety purchase price"
                    )

            # Economic returns from IC sheet / Final Metrics when cached.
            self._extract_economic_returns(wb, out)

            # Populate legacy aliases without conflating Graham entry concepts.
            out.graham_intrinsic = out.current_graham_intrinsic_value
            out.graham_expected_return = out.graham_expected_annualized_return
            # Do NOT set graham_entry to MOS price alone — leave None; report uses explicit fields.
            out.graham_entry = out.graham_target_return_entry_price

            # Cross-check only — never substitute reconstructed values as workbook proof.
            if valuation_validation:
                recon_iv = valuation_validation.get("workbook_intrinsic_value")
                if (
                    out.current_graham_intrinsic_value is not None
                    and recon_iv is not None
                    and abs(float(out.current_graham_intrinsic_value) - float(recon_iv)) > 1.0
                ):
                    out.warnings.append(
                        f"Graham IV workbook={out.current_graham_intrinsic_value:.2f} vs "
                        f"independent reconstruct={float(recon_iv):.2f}."
                    )

            self._sanity(out)
        finally:
            wb.close()
            wb_f.close()
        return out

    def _extract_economic_returns(self, wb, out: AnnualValuationOutputs) -> None:
        ic_name = next((n for n in wb.sheetnames if "nopat" in n.lower() and "roic" in n.lower()), None)
        target_col: int | None = None
        if "Inputs" in wb.sheetnames:
            try:
                cols = detect_year_columns(wb["Inputs"], wb)
                # Prefer newest FY column present on Inputs.
                if cols:
                    target_col = max(cols.values())
            except Exception:  # noqa: BLE001
                target_col = None
        if ic_name:
            ws = wb[ic_name]
            if target_col is None:
                target_col = min(ws.max_column or 12, 20)
            for row in range(1, min(ws.max_row or 1, 40) + 1):
                lab = _norm(ws.cell(row, 1).value)
                if not lab:
                    continue
                val = _num(ws.cell(row, target_col).value)
                if val is None:
                    for c in range(target_col, 2, -1):
                        val = _num(ws.cell(row, c).value)
                        if val is not None:
                            break
                if lab == "nopat" or lab.startswith("nopat "):
                    if val is not None:
                        out.nopat = val
                        out.sources["nopat"] = f"{ic_name}!{row}"
                elif "invested capital" in lab and "average" not in lab and val is not None:
                    # Prefer the total IC row (usually last matching label with value).
                    out.invested_capital = val
                    out.sources["invested_capital"] = f"{ic_name}!{row}"
                elif ("roic" in lab and "wacc" not in lab and "including" not in lab) and val is not None:
                    out.roic = val
                    out.sources["roic"] = f"{ic_name}!{row}"

        if "Final Metrics" in wb.sheetnames and target_col is not None:
            fm = wb["Final Metrics"]
            # Template: row 5 ROCE, row 8 ROIC - WACC for FY column
            roce = _num(fm.cell(5, target_col).value)
            if roce is not None:
                out.roce = roce
                out.sources["roce"] = f"Final Metrics row 5"
            rw = _num(fm.cell(8, target_col).value)
            if rw is not None:
                out.roic_wacc = rw
                out.sources["roic_wacc"] = f"Final Metrics row 8"

    @staticmethod
    def _sanity(out: AnnualValuationOutputs) -> None:
        g = out.owner_earnings_growth
        if g is not None and g <= -0.5:
            out.warnings.append(
                "OWNER_EARNINGS_GROWTH_IMPLAUSIBLE: owner-earnings growth "
                f"{g:.1%} is economically extreme; verify tax/R&D/cash-flow inputs."
            )
        ga = out.owner_earnings_growth_annualized
        if ga is not None and ga <= -0.2:
            out.warnings.append(
                "OWNER_EARNINGS_GROWTH_IMPLAUSIBLE: annualized owner-earnings growth "
                f"{ga:.1%} requires review."
            )
        # Prove B69 is not E14 when both present
        if (
            out.bloomberg_expected_return_at_current_price is not None
            and out.expected_annual_return is not None
            and abs(out.bloomberg_expected_return_at_current_price - out.expected_annual_return) > 0.02
        ):
            out.warnings.append(
                "Distinct metrics: Inputs!B69 Bloomberg Expected Return @ Current Price "
                f"({out.bloomberg_expected_return_at_current_price:.2%}) != "
                f"Expected Returns!E14 ({out.expected_annual_return:.2%})."
            )
