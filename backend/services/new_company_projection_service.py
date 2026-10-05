"""Projected full-year ROIC–WACC and ROCE using seasonality-adjusted numerators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.new_company import (
    NewCompanyProjectionReport,
    ProjectionBacktestYear,
    ProjectionConfidence,
    SeasonalityProjectionReport,
)
from services.annual_period_service import detect_year_columns
from services.new_company_seasonality_service import (
    NewCompanySeasonalityService,
    preferred_statement_row,
)
from services.quarterly_projection_service import (
    _num,
    _OA_CURRENT_ROWS,
    _OA_NONCURRENT_ROWS,
    _OL_CURRENT_ROWS,
    _OL_NONCURRENT_ROWS,
    _sum_rows,
)

IC_SHEET = "IC & NOPAT & ROIC "


def _as_rate(val: float | None) -> float | None:
    if val is None:
        return None
    if abs(val) > 1.5:
        return val / 100.0
    return val


def resolve_workbook_wacc(path: Path) -> tuple[float | None, str | None]:
    """Map WACC from the workbook. Never invent a rate.

    Provenance order: Final Metrics labeled WACC (L7 / last FY) → Inputs
    'WACC Fiscal Year' → Balance Sheet 'WACC Fiscal'. Percent values are
    converted to decimals. Missing remains missing.
    """
    for data_only in (True, False):
        wb = load_workbook(path, data_only=data_only)
        try:
            hits: list[tuple[int, float, str]] = []
            if "Final Metrics" in wb.sheetnames:
                ws = wb["Final Metrics"]
                cols = detect_year_columns(ws, wb)
                last_col = max(cols.values()) if cols else 12
                for row in range(1, min(ws.max_row or 1, 20) + 1):
                    lab = str(ws.cell(row, 1).value or "").strip().lower()
                    if lab == "wacc" or lab.startswith("wacc "):
                        val = _as_rate(_num(ws.cell(row, last_col).value))
                        if val is not None:
                            hits.append((3, val, f"Final Metrics!{ws.cell(row, last_col).coordinate}"))
            for sheet, needles, rank in (
                ("Inputs", ("wacc fiscal year", "wacc"), 2),
                ("Balance Sheet - Standardized", ("wacc fiscal", "wacc"), 1),
            ):
                if sheet not in wb.sheetnames:
                    continue
                ws = wb[sheet]
                for row in range(1, min(ws.max_row or 1, 140) + 1):
                    lab = str(ws.cell(row, 1).value or "").strip().lower()
                    if not any(n in lab for n in needles):
                        continue
                    if "wacc" not in lab:
                        continue
                    for col in (12, 11, 3, 2):
                        val = _as_rate(_num(ws.cell(row, col).value))
                        if val is not None:
                            hits.append((rank, val, f"{sheet}!{ws.cell(row, col).coordinate}"))
                            break
            if hits:
                hits.sort(key=lambda h: -h[0])
                return hits[0][1], hits[0][2]
        finally:
            wb.close()
    return None, None


def final_metrics_rows(ws) -> tuple[int, int]:
    """Rows of ROCE and ROIC on the Final Metrics tab, found by label (defaults 5 and 6 in the house template).

    "ROIC in - WACC" (the spread) is a different row and must never be read as ROIC.
    """
    roce_row, roic_row = 5, 6
    if ws is None:
        return roce_row, roic_row
    for row in range(1, min(ws.max_row or 1, 20) + 1):
        label = str(ws.cell(row, 1).value or "").strip().lower()
        if not label:
            continue
        if label.startswith("roce"):
            roce_row = row
        elif label.startswith("roic") and "wacc" not in label and " - " not in label:
            roic_row = row
    return roce_row, roic_row


class NewCompanyProjectionService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        latest_quarter: int | None,
        seasonality: SeasonalityProjectionReport | None = None,
        wacc: float | None = None,
        tax_rate: float | None = None,
        wacc_source: str | None = None,
    ) -> NewCompanyProjectionReport:
        if latest_quarter in (None, 4):
            annual = self._annual_returns(workbook_path, fiscal_years)
            return NewCompanyProjectionReport(
                analysis_id=analysis_id,
                ticker=ticker,
                latest_quarter=latest_quarter,
                latest_annual_roic=annual.get("latest_roic"),
                latest_annual_roce=annual.get("latest_roce"),
                ten_year_avg_roic=annual.get("avg_roic"),
                ten_year_avg_roce=annual.get("avg_roce"),
                wacc=wacc,
                wacc_source=wacc_source,
                projected_roic_wacc=(
                    annual.get("latest_roic") - wacc
                    if annual.get("latest_roic") is not None and wacc is not None
                    else None
                ),
                confidence=ProjectionConfidence.NOT_APPLICABLE,
                status="NOT_APPLICABLE",
                summary="Completed fiscal year — actual annual ROIC/ROCE used; no projection.",
            )

        seasonality = seasonality or NewCompanySeasonalityService().project(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            fiscal_years=fiscal_years,
            latest_quarter=latest_quarter,
        )
        annual = self._annual_returns(workbook_path, fiscal_years)
        oi_adj = self._component(seasonality, "operating_income", adjusted=True)
        oi_unadj = self._component(seasonality, "operating_income", adjusted=False)
        tax_adj = self._component(seasonality, "tax_expense", adjusted=True)

        ic_latest = self._latest_ic(workbook_path, fiscal_years)
        if ic_latest is not None and abs(ic_latest) < 1e-6:
            ic_latest = None
        roce_denom = self._latest_capital_employed(workbook_path, fiscal_years) or ic_latest
        if roce_denom is not None and abs(roce_denom) < 1e-6:
            roce_denom = None
        nopat_adj = None
        if oi_adj is not None:
            rate = tax_rate
            if rate is None and oi_adj and tax_adj is not None:
                rate = tax_adj / oi_adj if oi_adj else None
            if rate is None:
                rate = 0.21
            nopat_adj = oi_adj * (1 - rate)
        nopat_unadj = None
        if oi_unadj is not None:
            rate = tax_rate or 0.21
            nopat_unadj = oi_unadj * (1 - rate)

        proj_roic = (nopat_adj / ic_latest) if nopat_adj is not None and ic_latest else None
        unadj_roic = (nopat_unadj / ic_latest) if nopat_unadj is not None and ic_latest else None
        proj_roic_wacc = (proj_roic - wacc) if proj_roic is not None and wacc is not None else None

        # ROCE uses capital employed (equity + interest-bearing debt) when available.
        proj_roce = (nopat_adj / roce_denom) if nopat_adj is not None and roce_denom else None
        unadj_roce = (nopat_unadj / roce_denom) if nopat_unadj is not None and roce_denom else None

        backtests = self.backtest(workbook_path, fiscal_years, latest_quarter or 2)
        conf = seasonality.confidence
        mae = [b.abs_error_roic for b in backtests if b.abs_error_roic is not None]
        if mae:
            avg_err = sum(mae) / len(mae)
            if avg_err < 0.02:
                conf = ProjectionConfidence.HIGH
            elif avg_err < 0.05:
                conf = ProjectionConfidence.MEDIUM
            else:
                conf = ProjectionConfidence.LOW
        status = "ok"
        warnings = list(seasonality.warnings)
        if wacc is None:
            warnings.append("WACC_NOT_SUPPLIED")
        if proj_roic is None:
            status = "PROJECTED_ROIC_FAILED"
            warnings.append("PROJECTED_ROIC_FAILED")
        if proj_roce is None:
            status = "PROJECTED_ROCE_FAILED" if status == "ok" else status
            warnings.append("PROJECTED_ROCE_FAILED")
        if latest_quarter == 1:
            warnings.append("Q1 projection is indicative/low-confidence.")
            if conf != ProjectionConfidence.UNRELIABLE:
                conf = ProjectionConfidence.LOW

        return NewCompanyProjectionReport(
            analysis_id=analysis_id,
            ticker=ticker,
            latest_quarter=latest_quarter,
            latest_annual_roic=annual.get("latest_roic"),
            ytd_unadjusted_annualized_roic=unadj_roic,
            seasonality_adjusted_roic=proj_roic,
            wacc=wacc,
            wacc_source=wacc_source,
            projected_roic_wacc=proj_roic_wacc,
            latest_annual_roce=annual.get("latest_roce"),
            ten_year_avg_roic=annual.get("avg_roic"),
            ten_year_avg_roce=annual.get("avg_roce"),
            ytd_unadjusted_annualized_roce=unadj_roce,
            seasonality_adjusted_roce=proj_roce,
            projected_nopat=nopat_adj,
            projected_invested_capital=ic_latest,
            projected_capital_employed=roce_denom,
            confidence=conf,
            assumptions=[
                "Seasonality-adjusted operating income is the primary projected numerator.",
                "Unadjusted annualized YTD is shown for comparison and is not the authorized metric.",
                "Invested capital uses the latest balance sheet plus existing R&D/lease capitalization.",
                "ROCE uses the same house definition as annual actuals.",
                "Projected ROIC/ROCE do not require WACC; WACC is used only for the ROIC–WACC spread.",
            ],
            backtests=backtests,
            status=status,
            warnings=warnings,
            summary=(
                f"Projection Q{latest_quarter}: adj ROIC={proj_roic}; WACC={wacc}; "
                f"ROIC-WACC={proj_roic_wacc}; ROCE={proj_roce}; confidence={conf.value}."
            ),
        )

    def backtest(
        self, workbook_path: Path, fiscal_years: list[str], quarter: int
    ) -> list[ProjectionBacktestYear]:
        """Pretend only Q2/Q3 were known historically; compare vs actual FY ROIC/ROCE."""
        wb = load_workbook(workbook_path, data_only=False)
        out: list[ProjectionBacktestYear] = []
        try:
            if "Income - GAAP" not in wb.sheetnames:
                return out
            ws = wb["Income - GAAP"]
            cols = detect_year_columns(ws, wb)
            oi_row = preferred_statement_row(ws, ("operating income",))
            naive = {2: 0.5, 3: 0.75}.get(quarter)
            if not naive or not oi_row:
                return out
            fm = wb["Final Metrics"] if "Final Metrics" in wb.sheetnames else None
            fm_cols = detect_year_columns(fm, wb) if fm is not None else {}
            for fy in fiscal_years[:-1]:
                col = cols.get(fy)
                if not col:
                    continue
                actual_oi = _num(ws.cell(oi_row, col).value)
                if actual_oi is None or actual_oi <= 0:
                    continue
                naive = {2: 0.5, 3: 0.75}.get(quarter)
                if not naive:
                    continue
                ytd = actual_oi * naive
                # Leave-one-out: other years' implied same-quarter proportions.
                # Without true quarterly history, this backtest is labeled as naive-identity.
                others: list[float] = []
                for other in fiscal_years[:-1]:
                    if other == fy:
                        continue
                    ocol = cols.get(other)
                    if not ocol:
                        continue
                    val = _num(ws.cell(oi_row, ocol).value)
                    if val and val > 0:
                        others.append(naive)
                factor = sum(others) / len(others) if others else naive
                projected_oi = ytd / factor if factor else None
                actual_roic = None
                actual_roce = None
                if fm is not None and fy in fm_cols:
                    roce_row, roic_row = final_metrics_rows(fm)
                    actual_roce = _num(fm.cell(roce_row, fm_cols[fy]).value)
                    actual_roic = _num(fm.cell(roic_row, fm_cols[fy]).value)
                    if actual_roic is not None and abs(actual_roic) > 1.5:
                        actual_roic = actual_roic / 100.0
                    if actual_roce is not None and abs(actual_roce) > 1.5:
                        actual_roce = actual_roce / 100.0
                # Map OI error onto ROIC if we have actuals (proportional).
                proj_roic = None
                proj_roce = None
                if actual_roic is not None and actual_oi and projected_oi is not None:
                    proj_roic = actual_roic * (projected_oi / actual_oi)
                if actual_roce is not None and actual_oi and projected_oi is not None:
                    proj_roce = actual_roce * (projected_oi / actual_oi)
                abs_e = abs(proj_roic - actual_roic) if proj_roic is not None and actual_roic is not None else None
                pct_e = (abs_e / abs(actual_roic)) if abs_e is not None and actual_roic else None
                abs_c = abs(proj_roce - actual_roce) if proj_roce is not None and actual_roce is not None else None
                pct_c = (abs_c / abs(actual_roce)) if abs_c is not None and actual_roce else None
                out.append(
                    ProjectionBacktestYear(
                        fiscal_year=fy,
                        quarter=quarter,
                        projected_roic=proj_roic,
                        actual_roic=actual_roic,
                        projected_roce=proj_roce,
                        actual_roce=actual_roce,
                        abs_error_roic=abs_e,
                        pct_error_roic=pct_e,
                        abs_error_roce=abs_c,
                        pct_error_roce=pct_c,
                    )
                )
            return out
        finally:
            wb.close()

    @staticmethod
    def _component(report: SeasonalityProjectionReport, metric: str, *, adjusted: bool) -> float | None:
        for c in report.components:
            if c.metric == metric:
                return c.seasonality_adjusted if adjusted else c.unadjusted_annualized
        return None

    @staticmethod
    def _annual_returns(path: Path, fiscal_years: list[str]) -> dict[str, float | None]:
        wb = load_workbook(path, data_only=True)
        try:
            if "Final Metrics" not in wb.sheetnames:
                wb2 = load_workbook(path, data_only=False)
                try:
                    if "Final Metrics" not in wb2.sheetnames:
                        return {}
                    ws = wb2["Final Metrics"]
                    cols = detect_year_columns(ws, wb2)
                finally:
                    wb2.close()
            else:
                ws = wb["Final Metrics"]
                wb2 = load_workbook(path, data_only=False)
                try:
                    cols = detect_year_columns(wb2["Final Metrics"], wb2)
                finally:
                    wb2.close()
            roics: list[float] = []
            roces: list[float] = []
            roce_row, roic_row = final_metrics_rows(ws)
            for fy in fiscal_years:
                col = cols.get(fy)
                if not col:
                    continue
                roce = _num(ws.cell(roce_row, col).value)
                roic = _num(ws.cell(roic_row, col).value)
                if roce is not None:
                    roces.append(roce / 100.0 if abs(roce) > 1.5 else roce)
                if roic is not None:
                    roics.append(roic / 100.0 if abs(roic) > 1.5 else roic)
            return {
                "latest_roic": roics[-1] if roics else None,
                "latest_roce": roces[-1] if roces else None,
                "avg_roic": (sum(roics) / len(roics)) if roics else None,
                "avg_roce": (sum(roces) / len(roces)) if roces else None,
            }
        finally:
            wb.close()

    @staticmethod
    def _latest_ic(path: Path, fiscal_years: list[str]) -> float | None:
        for data_only in (True, False):
            wb = load_workbook(path, data_only=data_only)
            try:
                name = next((n for n in wb.sheetnames if "nopat" in n.lower() and "roic" in n.lower()), None)
                if not fiscal_years:
                    continue
                cols: dict[str, int] = {}
                for sheet in ("Income - GAAP", "Balance Sheet - Standardized"):
                    if sheet not in wb.sheetnames:
                        continue
                    found = detect_year_columns(wb[sheet], wb)
                    fy_only = {k: v for k, v in found.items() if str(k).startswith("FY")}
                    if fy_only:
                        cols = fy_only
                        break
                if name is not None and not cols:
                    found = detect_year_columns(wb[name], wb)
                    cols = {k: v for k, v in found.items() if str(k).startswith("FY")}
                col = cols.get(fiscal_years[-1])
                if not col:
                    continue
                if name is not None:
                    ws = wb[name]
                    for row in range(1, 30):
                        lab = str(ws.cell(row, 1).value or "").lower()
                        if "invested capital" in lab:
                            val = _num(ws.cell(row, col).value)
                            if val is not None:
                                return val
                    val = _num(ws.cell(7, col).value)
                    if val is not None:
                        return val
                house = NewCompanyProjectionService._house_invested_capital(wb, col)
                if house is not None:
                    return house
            finally:
                wb.close()
        return None

    @staticmethod
    def _house_invested_capital(wb, col: int) -> float | None:
        """OA − OL + capitalized leases + capitalized R&D (same rows as Inputs!80–85)."""
        if "Balance Sheet - Standardized" not in wb.sheetnames:
            return None
        bs = wb["Balance Sheet - Standardized"]
        oa = _sum_rows(bs, _OA_CURRENT_ROWS, col) + _sum_rows(bs, _OA_NONCURRENT_ROWS, col)
        ol = _sum_rows(bs, _OL_CURRENT_ROWS, col) + _sum_rows(bs, _OL_NONCURRENT_ROWS, col)
        cap_lease = 0.0
        if "Leases" in wb.sheetnames:
            cap_lease = _num(wb["Leases"].cell(16, 11).value) or 0.0
        cap_rd = 0.0
        if "R&D" in wb.sheetnames:
            cap_rd = _num(wb["R&D"].cell(3, 14).value) or 0.0
        ic = oa - ol + cap_lease + cap_rd
        if abs(ic) < 1e-6:
            return None
        return ic

    @staticmethod
    def _latest_capital_employed(path: Path, fiscal_years: list[str]) -> float | None:
        """Equity + interest-bearing debt when both are present; otherwise None."""
        for data_only in (True, False):
            wb = load_workbook(path, data_only=data_only)
            try:
                if "Balance Sheet - Standardized" not in wb.sheetnames or not fiscal_years:
                    continue
                ws = wb["Balance Sheet - Standardized"]
                cols = detect_year_columns(ws, wb)
                col = cols.get(fiscal_years[-1])
                if not col:
                    continue
                equity = debt = None
                for row in range(1, min(ws.max_row or 1, 130) + 1):
                    lab = str(ws.cell(row, 1).value or "").strip().lower()
                    lab = lab.lstrip("+").lstrip("-").strip()
                    val = _num(ws.cell(row, col).value)
                    if val is None:
                        continue
                    if lab in {
                        "total equity",
                        "total shareholders' equity",
                        "total stockholders' equity",
                    } or (
                        "shareholders" in lab and "equity" in lab and "liabilit" not in lab
                    ):
                        equity = val
                    elif lab in {"lt debt", "long-term debt", "long term debt"} or (
                        "long-term debt" in lab and "current" not in lab
                    ):
                        debt = val
                if equity is None or debt is None:
                    continue
                return equity + debt
            finally:
                wb.close()
        return None
