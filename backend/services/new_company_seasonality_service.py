"""Company-specific seasonality-adjusted full-year projections from YTD results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.new_company import (
    ProjectionConfidence,
    SeasonalityComponent,
    SeasonalityProjectionReport,
)
from services.annual_period_service import detect_year_columns

# Income - GAAP rows searched by label; LQ IS YTD is column G (7).
YTD_COL = 7
LQ_IS = "Last Quarter IS Standardized"
LQ_CF = "Last Quarter CF Standardized"

_METRICS = (
    ("revenue", "Income - GAAP", ("revenue",), "Last Quarter IS Standardized", ("revenue",)),
    ("operating_income", "Income - GAAP", ("operating income",), "Last Quarter IS Standardized", ("operating income",)),
    ("ebit", "Income - GAAP", ("ebit", "operating income"), "Last Quarter IS Standardized", ("operating income",)),
    ("tax_expense", "Income - GAAP", ("income tax expense",), "Last Quarter IS Standardized", ("income tax",)),
    ("rd_expense", "Income - GAAP", ("research and development", "research & development"), "Last Quarter IS Standardized", ("research",)),
    ("capex", "Cash Flow - Standardized", ("capital expenditure", "acq of fixed"), "Last Quarter CF Standardized", ("capex", "fixed asset")),
    ("cfo", "Cash Flow - Standardized", ("cash from operating",), "Last Quarter CF Standardized", ("cash from operating", "operating activities")),
    ("working_capital", "Balance Sheet - Standardized", ("working capital", "total current assets"), "Last Quarter BS Standardized", ("total current assets", "cash")),
    ("lease_expense", "Income - GAAP", ("lease expense", "operating lease cost"), "Last Quarter IS Standardized", ("lease",)),
)


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _fy_int(token: str) -> int:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else 0


def naive_annualization_factor(quarter: int) -> float | None:
    if quarter == 2:
        return 2.0
    if quarter == 3:
        return 4.0 / 3.0
    if quarter == 1:
        return 4.0
    return None


class NewCompanySeasonalityService:
    """Project FY = YTD / historical YTD-to-FY proportion; never blind *2 / *4/3 as primary."""

    def project(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        latest_quarter: int | None,
        window: int = 5,
    ) -> SeasonalityProjectionReport:
        if latest_quarter in (None, 4):
            return SeasonalityProjectionReport(
                analysis_id=analysis_id,
                ticker=ticker,
                latest_quarter=latest_quarter,
                ytd_period_length="full_year" if latest_quarter == 4 else None,
                confidence=ProjectionConfidence.NOT_APPLICABLE,
                summary="Full fiscal year available or quarter unidentified; no YTD projection.",
            )

        ytd_label = {1: "3M", 2: "6M_YTD", 3: "9M_YTD"}.get(latest_quarter or 0, "YTD")
        wb = load_workbook(workbook_path, data_only=False)
        warnings: list[str] = []
        components: list[SeasonalityComponent] = []
        try:
            hist_years = fiscal_years[-window:] if len(fiscal_years) >= 3 else fiscal_years
            # Recency weights: most recent year heaviest.
            weights = self._weights(hist_years)
            for metric, annual_sheet, annual_needles, q_sheet, q_needles in _METRICS:
                ytd = self._ytd_value(wb, q_sheet, q_needles)
                hist_ytd: dict[str, float] = {}
                hist_fy: dict[str, float] = {}
                props: dict[str, float] = {}
                exclusions: list[str] = []
                if annual_sheet in wb.sheetnames:
                    ws = wb[annual_sheet]
                    cols = detect_year_columns(ws, wb)
                    row = self._find_row(ws, annual_needles)
                    for fy in hist_years:
                        col = cols.get(fy)
                        if not row or not col:
                            continue
                        fy_val = _num(ws.cell(row, col).value)
                        if fy_val is None:
                            continue
                        hist_fy[fy] = fy_val
                        # Approximate historical YTD as same-quarter share of that year when LQ history absent.
                        # Prefer explicit quarterly history columns if present on annual sheet (unused here).
                hist_ytd = self._historical_ytd(wb, q_sheet, q_needles, hist_years, latest_quarter or 0, hist_fy)
                for fy, fy_val in hist_fy.items():
                    ytd_h = hist_ytd.get(fy)
                    if ytd_h is None or fy_val == 0:
                        continue
                    if fy_val < 0 or ytd_h < 0:
                        # Unstable / negative denominator — do not use mechanically.
                        exclusions.append(fy)
                        continue
                    prop = ytd_h / fy_val
                    if prop <= 0.05 or prop > 1.5:
                        exclusions.append(fy)
                        continue
                    props[fy] = prop
                selected = None
                if props:
                    wsum = 0.0
                    acc = 0.0
                    for fy, prop in props.items():
                        w = weights.get(fy, 1.0)
                        acc += prop * w
                        wsum += w
                    selected = acc / wsum if wsum else None
                unreliable = selected is None or (ytd is not None and selected is not None and abs(selected) < 1e-6)
                unadj = None
                adj = None
                factor = naive_annualization_factor(latest_quarter or 0)
                if ytd is not None and factor:
                    unadj = ytd * factor
                if ytd is not None and selected not in (None, 0) and not unreliable:
                    adj = ytd / selected
                elif ytd is not None and unreliable:
                    warnings.append(f"SEASONALITY_PROJECTION_UNRELIABLE: {metric}")
                if len(props) < 3 and latest_quarter in {2, 3}:
                    warnings.append(f"SEASONALITY_HISTORY_INSUFFICIENT: {metric}")
                components.append(
                    SeasonalityComponent(
                        metric=metric,
                        ytd_value=ytd,
                        historical_ytd=hist_ytd,
                        historical_full_year=hist_fy,
                        proportions=props,
                        weights={k: weights.get(k, 0.0) for k in props},
                        selected_factor=selected,
                        unadjusted_annualized=unadj,
                        seasonality_adjusted=adj,
                        exclusions=exclusions,
                        unreliable=unreliable,
                        reason=None if not unreliable else "unstable or negative YTD-to-FY proportion",
                    )
                )
        finally:
            wb.close()

        conf = ProjectionConfidence.MEDIUM
        if latest_quarter == 1:
            conf = ProjectionConfidence.LOW
            warnings.append("Q1 projection is indicative only (low confidence).")
        if any(c.unreliable for c in components if c.metric in {"operating_income", "revenue"}):
            conf = ProjectionConfidence.UNRELIABLE
        elif any("HISTORY_INSUFFICIENT" in w for w in warnings):
            conf = ProjectionConfidence.LOW
        elif all(
            c.selected_factor and 0.3 <= c.selected_factor <= 0.95
            for c in components
            if c.metric in {"revenue", "operating_income"} and c.ytd_value is not None
        ):
            conf = ProjectionConfidence.HIGH if latest_quarter in {2, 3} else conf

        return SeasonalityProjectionReport(
            analysis_id=analysis_id,
            ticker=ticker,
            latest_quarter=latest_quarter,
            ytd_period_length=ytd_label,
            historical_comparison_years=hist_years if fiscal_years else [],
            components=components,
            confidence=conf,
            warnings=warnings,
            summary=(
                f"Seasonality Q{latest_quarter}: {len(components)} components; "
                f"confidence={conf.value}; warnings={len(warnings)}."
            ),
        )

    @staticmethod
    def _weights(years: list[str]) -> dict[str, float]:
        n = len(years)
        # Recent years heavier: 1,2,...,n
        return {fy: float(i + 1) for i, fy in enumerate(years)}

    @staticmethod
    def _find_row(ws, needles: tuple[str, ...]) -> int | None:
        for row in range(1, min(ws.max_row or 1, 90) + 1):
            lab = str(ws.cell(row, 1).value or "").strip().lower()
            if lab and any(n in lab for n in needles) and not lab.startswith(" "):
                return row
        return None

    def _ytd_value(self, wb, sheet: str, needles: tuple[str, ...]) -> float | None:
        if sheet not in wb.sheetnames:
            return None
        ws = wb[sheet]
        row = self._find_row(ws, needles)
        if not row:
            return None
        return _num(ws.cell(row, YTD_COL).value) or _num(ws.cell(row, 3).value)

    def _historical_ytd(
        self,
        wb,
        sheet: str,
        needles: tuple[str, ...],
        years: list[str],
        quarter: int,
        hist_fy: dict[str, float],
    ) -> dict[str, float]:
        """Use prior-year YTD on the LQ sheet when present.

        Do not seed naive quarter shares into the primary seasonality factor.
        """
        out: dict[str, float] = {}
        prior_ytd = None
        if sheet in wb.sheetnames:
            ws = wb[sheet]
            row = self._find_row(ws, needles)
            if row:
                prior_ytd = _num(ws.cell(row, 8).value)  # H = prior YTD on Industrial Template
        if prior_ytd is not None and years:
            out[years[-1]] = prior_ytd
        return out
