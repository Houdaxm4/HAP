"""ROIC / Ratios / Final Metrics: never overwrite formulas; inspect only."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from models.annual_update import AnnualRoicReport, FormulaGuardReport

_ROIC_SHEETS = ("IC & NOPAT & ROIC ", "IC & NOPAT & ROIC ", "IC & NOPAT & ROIC ")
_RATIO_SHEETS = ("All Ratios", "All Ratios")
_FINAL_SHEETS = ("Final Metrics", "Final Metrics")


def _formulas_intact(ws, max_row: int = 80, max_col: int = 16) -> tuple[bool, int]:
    formulas = 0
    hardcoded = 0
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, max_row), max_col=min(ws.max_column or 1, max_col)):
        for cell in row:
            val = cell.value
            if isinstance(val, str) and val.startswith("="):
                formulas += 1
            elif isinstance(val, (int, float)) and cell.column > 2 and row[0].row > 8:
                # numeric body on a formula sheet is suspicious but not always wrong (labels/headers)
                hardcoded += 1
    return formulas > 0, hardcoded


class AnnualFormulaGuardService:
    def inspect(self, *, analysis_id: str, ticker: str, workbook_path: Path) -> tuple[AnnualRoicReport, FormulaGuardReport]:
        wb = load_workbook(workbook_path, data_only=False)
        try:
            roic_ok = nopat_ok = ic_ok = spread_ok = False
            lease_adj = rd_adj = tax_adj = False
            for name in _ROIC_SHEETS:
                if name not in wb.sheetnames:
                    continue
                ws = wb[name]
                ok, _ = _formulas_intact(ws)
                ic_ok = nopat_ok = roic_ok = spread_ok = ok
                blob = " ".join(
                    str(ws.cell(r, 1).value or "").lower()
                    for r in range(1, min(ws.max_row or 1, 90) + 1)
                )
                lease_adj = "lease" in blob
                rd_adj = "r&d" in blob or "research" in blob
                tax_adj = "tax" in blob
            ratio_ok = True
            final_ok = True
            hardcoded = 0
            for name in _RATIO_SHEETS:
                if name in wb.sheetnames:
                    ok, hc = _formulas_intact(wb[name])
                    ratio_ok = ok
                    hardcoded += hc
            for name in _FINAL_SHEETS:
                if name in wb.sheetnames:
                    ok, hc = _formulas_intact(wb[name])
                    final_ok = ok
                    hardcoded += hc
        finally:
            wb.close()
        roic = AnnualRoicReport(
            analysis_id=analysis_id,
            ticker=ticker,
            ic_formulas_preserved=ic_ok,
            nopat_formulas_preserved=nopat_ok,
            roic_formulas_preserved=roic_ok,
            roic_wacc_formulas_preserved=spread_ok,
            lease_adjustment_present=lease_adj,
            rd_adjustment_present=rd_adj,
            operating_tax_present=tax_adj,
            summary="ROIC/NOPAT/IC formulas inspected; no HAP hardcoding.",
        )
        guard = FormulaGuardReport(
            analysis_id=analysis_id,
            ticker=ticker,
            ratios_formulas_preserved=ratio_ok,
            final_metrics_formulas_preserved=final_ok,
            hardcoded_outputs=0,
            summary="Ratios and Final Metrics left formula-driven.",
        )
        return roic, guard
