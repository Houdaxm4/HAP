"""Company-specific seasonality-adjusted full-year projections from YTD results."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.new_company import (
    ProjectionConfidence,
    SeasonalityComponent,
    SeasonalityProjectionReport,
)
from services.annual_period_service import detect_year_columns
from services.sec_10q_statement_service import duration_bucket

# Income - GAAP rows searched by label; LQ IS YTD is column G (7) when Bloomberg-filled.
YTD_COL = 7
PRIOR_YTD_COL = 8
STANDALONE_COL = 3
LQ_IS = "Last Quarter IS Standardized"
LQ_CF = "Last Quarter CF Standardized"

_METRICS = (
    ("revenue", "Income - GAAP", ("revenue",), "Last Quarter IS Standardized", ("revenue",),
     ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")),
    ("operating_income", "Income - GAAP", ("operating income",), "Last Quarter IS Standardized", ("operating income",),
     ("OperatingIncomeLoss",)),
    ("ebit", "Income - GAAP", ("ebit", "operating income"), "Last Quarter IS Standardized", ("operating income",),
     ("OperatingIncomeLoss",)),
    ("tax_expense", "Income - GAAP", ("income tax expense",), "Last Quarter IS Standardized", ("income tax",),
     ("IncomeTaxExpenseBenefit",)),
    ("rd_expense", "Income - GAAP", ("research and development", "research & development"), "Last Quarter IS Standardized", ("research",),
     ("ResearchAndDevelopmentExpense",)),
    ("capex", "Cash Flow - Standardized", ("capital expenditure", "acq of fixed"), "Last Quarter CF Standardized", ("capex", "fixed asset"),
     ("PaymentsToAcquirePropertyPlantAndEquipment",)),
    ("cfo", "Cash Flow - Standardized", ("cash from operating",), "Last Quarter CF Standardized", ("cash from operating", "operating activities"),
     ("NetCashProvidedByUsedInOperatingActivities",)),
    ("working_capital", "Balance Sheet - Standardized", ("working capital", "total current assets"), "Last Quarter BS Standardized", ("total current assets", "cash"),
     ()),
    ("lease_expense", "Income - GAAP", ("lease expense", "operating lease cost"), "Last Quarter IS Standardized", ("lease",),
     ("OperatingLeaseCost",)),
)

_EXCLUDED_LABELS = (
    "other operating income",
    "other operating expense",
    "other operating (income)",
)
_PREFERRED_CODES = {
    "operating income": ("IS_OPER_INC",),
    "revenue": ("SALES_REV_TURN",),
}


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _fy_int(token: str) -> int:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else 0


def _scale_usd(val: float) -> float:
    return val / 1_000_000.0 if abs(val) >= 10_000 else val


def naive_annualization_factor(quarter: int) -> float | None:
    if quarter == 2:
        return 2.0
    if quarter == 3:
        return 4.0 / 3.0
    if quarter == 1:
        return 4.0
    return None


def preferred_statement_row(ws, needles: tuple[str, ...]) -> int | None:
    """Prefer exact operating-income / revenue labels over 'Other Operating Income'."""
    best: tuple[int, int] | None = None
    for row in range(1, min(ws.max_row or 1, 90) + 1):
        lab = str(ws.cell(row, 1).value or "").strip()
        if not lab:
            continue
        code = str(ws.cell(row, 2).value or "").strip().upper()
        score = _label_score(lab, needles, code)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, row)
    return best[1] if best else None


def _label_score(lab: str, needles: tuple[str, ...], code: str = "") -> int:
    lab_n = lab.strip().lower().lstrip("+").lstrip("-").strip()
    if any(ex in lab_n for ex in _EXCLUDED_LABELS):
        return -1
    for needle in needles:
        preferred = _PREFERRED_CODES.get(needle, ())
        if code and code in preferred:
            return 100
        if lab_n == needle or lab_n == f"{needle} (loss)":
            return 90
        if lab_n.startswith(needle):
            return 70
        if needle in lab_n:
            return 40
    return 0


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
        company_facts: dict[str, Any] | None = None,
        latest_quarter_fiscal_year: str | None = None,
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
        ytd_bucket = {1: "3m", 2: "6m", 3: "9m"}.get(latest_quarter or 0)
        wb = load_workbook(workbook_path, data_only=False)
        warnings: list[str] = []
        components: list[SeasonalityComponent] = []
        try:
            layout = self._lq_layout(wb)
            current_fy = latest_quarter_fiscal_year or layout.get("fiscal_year")
            hist_years = fiscal_years[-window:] if len(fiscal_years) >= 3 else fiscal_years
            weights = self._weights(hist_years)
            for metric, annual_sheet, annual_needles, q_sheet, q_needles, sec_tags in _METRICS:
                ytd, ytd_src = self._ytd_value(
                    wb,
                    q_sheet,
                    q_needles,
                    latest_quarter or 0,
                    layout,
                    company_facts,
                    sec_tags,
                    current_fy,
                    ytd_bucket,
                )
                hist_fy: dict[str, float] = {}
                if annual_sheet in wb.sheetnames:
                    ws = wb[annual_sheet]
                    cols = detect_year_columns(ws, wb)
                    row = preferred_statement_row(ws, annual_needles)
                    for fy in hist_years:
                        col = cols.get(fy)
                        if not row or not col:
                            continue
                        fy_val = _num(ws.cell(row, col).value)
                        if fy_val is None:
                            continue
                        hist_fy[fy] = fy_val
                hist_ytd = self._historical_ytd(
                    wb,
                    q_sheet,
                    q_needles,
                    hist_years,
                    latest_quarter or 0,
                    layout,
                    company_facts,
                    sec_tags,
                    ytd_bucket,
                )
                props: dict[str, float] = {}
                exclusions: list[str] = []
                for fy, fy_val in hist_fy.items():
                    ytd_h = hist_ytd.get(fy)
                    if ytd_h is None or fy_val == 0:
                        continue
                    if fy_val < 0 or ytd_h < 0:
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
                    if metric in {"revenue", "operating_income"}:
                        missing = [fy for fy in hist_years if fy not in props]
                        warnings.append(
                            f"SEASONALITY_MISSING_YTD_FY_PAIRS: {metric} missing={missing} "
                            f"available={list(props.keys())}"
                        )
                reason = None
                if unreliable:
                    reason = "unstable or negative YTD-to-FY proportion"
                if ytd_src:
                    reason = (reason + f"; ytd_source={ytd_src}") if reason else f"ytd_source={ytd_src}"
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
                        reason=reason,
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
        elif any("HISTORY_INSUFFICIENT" in w for w in warnings if "operating_income" in w or "revenue" in w):
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
        return {fy: float(i + 1) for i, fy in enumerate(years)}

    @staticmethod
    def _find_row(ws, needles: tuple[str, ...]) -> int | None:
        return preferred_statement_row(ws, needles)

    @staticmethod
    def _lq_layout(wb) -> dict[str, Any]:
        out: dict[str, Any] = {
            "standalone_three_month": False,
            "ytd_numeric": False,
            "fiscal_year": None,
            "quarter": None,
        }
        if LQ_IS not in wb.sheetnames:
            return out
        ws = wb[LQ_IS]
        header = " ".join(str(ws.cell(r, 3).value or "") for r in range(1, 9))
        if re.search(r"3\s*months?\s*ended", header, re.I):
            out["standalone_three_month"] = True
        g_numeric = False
        for row in range(11, 40):
            if _num(ws.cell(row, YTD_COL).value) is not None:
                g_numeric = True
                break
        out["ytd_numeric"] = g_numeric
        for row in range(1, 10):
            for col in (3, 4):
                val = ws.cell(row, col).value
                if val is None:
                    continue
                if hasattr(val, "year"):
                    out["fiscal_year"] = f"FY{val.year}"
                    continue
                text = str(val)
                match = re.search(r"(20\d{2})\s*Q([1-4])", text, re.I)
                if match:
                    out["fiscal_year"] = f"FY{match.group(1)}"
                    out["quarter"] = int(match.group(2))
                    return out
        return out

    def _ytd_value(
        self,
        wb,
        sheet: str,
        needles: tuple[str, ...],
        quarter: int,
        layout: dict[str, Any],
        company_facts: dict[str, Any] | None,
        sec_tags: tuple[str, ...],
        current_fy: str | None,
        ytd_bucket: str | None,
    ) -> tuple[float | None, str | None]:
        workbook_ytd = None
        if sheet in wb.sheetnames:
            ws = wb[sheet]
            row = preferred_statement_row(ws, needles)
            if row:
                workbook_ytd = _num(ws.cell(row, YTD_COL).value)
                standalone = _num(ws.cell(row, STANDALONE_COL).value)
                if workbook_ytd is not None:
                    return workbook_ytd, f"workbook:{sheet}!G{row}"
                if quarter == 1 and standalone is not None:
                    return standalone, f"workbook:{sheet}!C{row}:q1_standalone_is_ytd"
                if standalone is not None and not layout.get("standalone_three_month"):
                    return standalone, f"workbook:{sheet}!C{row}"
        sec_ytd = self._sec_duration_value(company_facts, sec_tags, current_fy, ytd_bucket)
        if sec_ytd is not None:
            return sec_ytd, f"sec_xbrl:{ytd_bucket}:{current_fy}"
        return None, None

    def _historical_ytd(
        self,
        wb,
        sheet: str,
        needles: tuple[str, ...],
        years: list[str],
        quarter: int,
        layout: dict[str, Any],
        company_facts: dict[str, Any] | None,
        sec_tags: tuple[str, ...],
        ytd_bucket: str | None,
    ) -> dict[str, float]:
        """Historical same-period YTD. Do not seed naive quarter shares into the primary factor."""
        out: dict[str, float] = {}
        for fy in years:
            sec_val = self._sec_duration_value(company_facts, sec_tags, fy, ytd_bucket)
            if sec_val is not None:
                out[fy] = sec_val
        if layout.get("ytd_numeric") and sheet in wb.sheetnames and years:
            ws = wb[sheet]
            row = preferred_statement_row(ws, needles)
            if row:
                prior = _num(ws.cell(row, PRIOR_YTD_COL).value)
                if prior is not None and years[-1] not in out:
                    out[years[-1]] = prior
        return out

    @staticmethod
    def _sec_duration_value(
        company_facts: dict[str, Any] | None,
        tags: tuple[str, ...],
        fy: str | None,
        bucket: str | None,
    ) -> float | None:
        if not company_facts or not tags or not fy or not bucket:
            return None
        year_n = _fy_int(fy)
        facts = company_facts.get("facts") or {}
        best: tuple[int, float] | None = None
        for taxonomy in ("us-gaap", "dei", "ifrs-full"):
            tax = facts.get(taxonomy) or {}
            for tag in tags:
                payload = tax.get(tag)
                if not payload:
                    continue
                for unit, entries in (payload.get("units") or {}).items():
                    for entry in entries or []:
                        if entry.get("val") is None:
                            continue
                        form = str(entry.get("form") or "")
                        if form not in {"10-Q", "10-Q/A", "10-K", "10-K/A"}:
                            continue
                        start = entry.get("start")
                        end = entry.get("end") or ""
                        if duration_bucket(start, end) != bucket:
                            continue
                        end_year = int(end[:4]) if isinstance(end, str) and end[:4].isdigit() else None
                        start_year = None
                        if isinstance(start, str) and start[:4].isdigit():
                            start_year = int(start[:4])
                        if end_year != year_n and start_year != year_n:
                            continue
                        score = 2 if form.startswith("10-Q") else 1
                        if entry.get("fp") == f"Q{2 if bucket == '6m' else 3 if bucket == '9m' else 1}":
                            score += 1
                        val = _scale_usd(float(entry["val"]))
                        if best is None or score > best[0]:
                            best = (score, val)
        return best[1] if best else None
