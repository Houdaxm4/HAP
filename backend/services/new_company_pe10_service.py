"""Ten-year PE10/E10 extraction from Bloomberg CRF using exact field identities."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.new_company import NewCompanyPe10Report, Pe10Observation
from services.annual_inputs_service import AnnualInputsService
from services.annual_period_service import detect_workbook_years, detect_year_columns
from services.current_data_refresh_service import CurrentDataRefreshService
from services.custom_run_service import CustomRunService

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9]+")
_NEAREST_TOLERANCE_DAYS = 45

# Exact normalized identities — never substring-match E10 inside PE10.
FIELD_IDENTITIES = {
    "pe10_fiscal_year": frozenset({"pe10", "pe 10"}),
    "e10_fiscal_year": frozenset({"e10", "e 10"}),
    "stock_price_fiscal_year": frozenset({"stock price", "price", "share price"}),
    "pe10_current": frozenset({"current pe10"}),
    "e10_current": frozenset({"current e10"}),
    "stock_price_current": frozenset({"current price", "current stock price"}),
    "source_as_of_date": frozenset({"as of", "as-of date", "as of date"}),
}


def _norm(label: Any) -> str:
    text = _WS.sub(" ", str(label or "").strip().lower())
    return _PUNCT.sub(" ", text).strip()


def exact_field_identity(label: Any) -> str | None:
    """Map a workbook/CRF label to a canonical field identity with exact tokens."""
    raw = _norm(label)
    if not raw:
        return None
    compact = raw.replace(" ", "")
    has_current = "current" in raw.split() or raw.startswith("current ")
    if has_current:
        if compact == "currentpe10" or raw == "current pe10":
            return "pe10_current"
        if compact == "currente10" or raw == "current e10":
            return "e10_current"
        if "price" in raw:
            return "stock_price_current"
        return None
    # Exact compact match only — "e10" must not match "pe10".
    if compact == "pe10":
        return "pe10_fiscal_year"
    if compact == "e10":
        return "e10_fiscal_year"
    if raw in FIELD_IDENTITIES["stock_price_fiscal_year"]:
        return "stock_price_fiscal_year"
    if raw in FIELD_IDENTITIES["source_as_of_date"]:
        return "source_as_of_date"
    return None


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return None


def _fy_end(token: str) -> datetime:
    year = int("".join(ch for ch in token if ch.isdigit()) or 0)
    return datetime(year, 12, 31)


class NewCompanyPe10Service:
    """Populate all ten historical PE10/E10 columns plus current values from CRF."""

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        custom_run_path: Path | None,
        fiscal_years: list[str],
        live_price: float | None = None,
        fy_end_dates: dict[str, str] | None = None,
        nearest_tolerance_days: int = _NEAREST_TOLERANCE_DAYS,
    ) -> NewCompanyPe10Report:
        CurrentDataRefreshService().apply(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            custom_run_path=custom_run_path,
            live_price=live_price,
        )

        fy_pe: dict[str, tuple[float, str | None, int | None]] = {}
        fy_e10: dict[str, tuple[float, str | None, int | None]] = {}
        fy_price: dict[str, float] = {}
        current_pe = current_e10 = current_price = None
        current_as_of = None
        warnings: list[str] = []
        duplicates: list[str] = []
        zeros: list[str] = []
        crf_data = None
        crf_failed = False

        if custom_run_path and Path(custom_run_path).exists():
            try:
                crf_data = CustomRunService().parse(Path(custom_run_path), Path(custom_run_path).name)
            except Exception as exc:  # noqa: BLE001
                crf_data = None
                crf_failed = True
                warnings.append(f"TEN_YEAR_PE10_COVERAGE_INCOMPLETE: CRF parse failed ({exc}).")
        elif custom_run_path:
            crf_failed = True
            warnings.append("TEN_YEAR_PE10_COVERAGE_INCOMPLETE: CRF path missing.")

        if fy_end_dates is None:
            warnings.append(
                "PE10_PERIOD_NOTE: fiscal year-end dates not supplied; nearest-date matching "
                "assumes calendar 31 Dec unless a dated CRF series is used."
            )

        if crf_data is not None:
            annual_pe = dict((crf_data.metadata or {}).get("inputs_annual_pe10") or {})
            annual_e10 = dict((crf_data.metadata or {}).get("inputs_annual_e10") or {})
            current_pe = _safe_float(crf_data.scalar("Current PE10"))
            current_e10 = _safe_float(crf_data.scalar("Current E10"))
            current_price = _safe_float(
                crf_data.scalar("Current Price (Live Price)", "Current Price")
            )
            current_as_of = (
                crf_data.scalar("As Of", "As-Of Date")
                or (crf_data.periods.dates[-1] if crf_data.periods.dates else None)
            )
            dated_pe = self._dated_series(crf_data, "PE10")
            dated_e10 = self._dated_series(crf_data, "E10")
            dated_px = self._dated_series(crf_data, "Price") or self._dated_series(crf_data, "Stock Price")
            seen_obs: dict[str, str] = {}
            for fy in fiscal_years:
                target = _parse_date((fy_end_dates or {}).get(fy)) or _fy_end(fy)
                pe_val, pe_date, pe_delta, pe_src = self._match_year(
                    fy, annual_pe, dated_pe, target, nearest_tolerance_days, role="pe10_fiscal_year"
                )
                e_val, e_date, e_delta, e_src = self._match_year(
                    fy, annual_e10, dated_e10, target, nearest_tolerance_days, role="e10_fiscal_year"
                )
                px_val, _, _, _ = self._match_year(
                    fy, {}, dated_px, target, nearest_tolerance_days, role="stock_price_fiscal_year"
                )
                if pe_val == 0:
                    zeros.append(f"{fy}:pe10")
                    pe_val = None
                    warnings.append(f"PE10 {fy}: zero treated as missing, not written.")
                if e_val == 0:
                    zeros.append(f"{fy}:e10")
                    e_val = None
                    warnings.append(f"E10 {fy}: zero treated as missing, not written.")
                if pe_delta is not None and abs(pe_delta) > nearest_tolerance_days:
                    warnings.append(
                        f"PE10_FISCAL_DATE_MISMATCH: {fy} nearest CRF date {pe_date} "
                        f"differs by {pe_delta} days (tolerance {nearest_tolerance_days})."
                    )
                    pe_val = None
                if e_delta is not None and abs(e_delta) > nearest_tolerance_days:
                    warnings.append(
                        f"E10_FISCAL_DATE_MISMATCH: {fy} nearest CRF date {e_date} "
                        f"differs by {e_delta} days (tolerance {nearest_tolerance_days})."
                    )
                    e_val = None
                if pe_date and pe_date in seen_obs:
                    duplicates.append(f"{fy}|{seen_obs[pe_date]}")
                elif pe_date:
                    seen_obs[pe_date] = fy
                if pe_val is not None:
                    fy_pe[fy] = (pe_val, pe_date or pe_src, pe_delta)
                if e_val is not None:
                    fy_e10[fy] = (e_val, e_date or e_src, e_delta)
                if px_val is not None:
                    fy_price[fy] = px_val

        pe_obs: list[Pe10Observation] = []
        e_obs: list[Pe10Observation] = []
        wb = load_workbook(workbook_path, data_only=False)
        try:
            if "Inputs" not in wb.sheetnames:
                warnings.append("TEN_YEAR_PE10_COVERAGE_INCOMPLETE: Inputs sheet missing.")
            else:
                ws = wb["Inputs"]
                cols = detect_year_columns(ws, wb)
                if not any(str(k).startswith("FY") for k in cols):
                    cols = detect_workbook_years(workbook_path)
                pe_row = self._find_row(ws, "pe10_fiscal_year") or 57
                e_row = self._find_row(ws, "e10_fiscal_year") or 58
                px_row = self._find_row(ws, "stock_price_fiscal_year")
                for fy in fiscal_years:
                    col = cols.get(fy)
                    pe = fy_pe.get(fy)
                    e10 = fy_e10.get(fy)
                    if col and pe:
                        cell = ws.cell(pe_row, col)
                        if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                            cell.value = pe[0]
                        pe_obs.append(
                            Pe10Observation(
                                fiscal_year=fy,
                                field_role="pe10_fiscal_year",
                                value=pe[0],
                                stock_price=fy_price.get(fy),
                                as_of_date=pe[1],
                                observation_date=pe[1],
                                date_difference_days=pe[2],
                                nearest_date_rule="fiscal_year_end_or_nearest_crf_observation",
                                source_label=f"PE10 Annual {fy}",
                                target_cell=f"{get_column_letter(col)}{pe_row}",
                            )
                        )
                    else:
                        pe_obs.append(
                            Pe10Observation(
                                fiscal_year=fy,
                                field_role="pe10_fiscal_year",
                                missing=True,
                                warning="TEN_YEAR_PE10_COVERAGE_INCOMPLETE",
                                target_cell=f"{get_column_letter(col)}{pe_row}" if col else None,
                            )
                        )
                    if col and e10:
                        cell = ws.cell(e_row, col)
                        if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                            cell.value = e10[0]
                        e_obs.append(
                            Pe10Observation(
                                fiscal_year=fy,
                                field_role="e10_fiscal_year",
                                value=e10[0],
                                as_of_date=e10[1],
                                observation_date=e10[1],
                                date_difference_days=e10[2],
                                nearest_date_rule="fiscal_year_end_or_nearest_crf_observation",
                                source_label=f"E10 Annual {fy}",
                                target_cell=f"{get_column_letter(col)}{e_row}",
                            )
                        )
                    else:
                        e_obs.append(
                            Pe10Observation(
                                fiscal_year=fy,
                                field_role="e10_fiscal_year",
                                missing=True,
                                warning="TEN_YEAR_E10_COVERAGE_INCOMPLETE",
                                target_cell=f"{get_column_letter(col)}{e_row}" if col else None,
                            )
                        )
                    if col and px_row and fy in fy_price:
                        cell = ws.cell(px_row, col)
                        if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                            cell.value = fy_price[fy]
                wb.save(workbook_path)
        finally:
            wb.close()

        missing_pe = [o.fiscal_year for o in pe_obs if o.missing]
        missing_e = [o.fiscal_year for o in e_obs if o.missing]
        if missing_pe:
            warnings.append("TEN_YEAR_PE10_COVERAGE_INCOMPLETE: " + ", ".join(str(x) for x in missing_pe))
        if missing_e:
            warnings.append("TEN_YEAR_E10_COVERAGE_INCOMPLETE: " + ", ".join(str(x) for x in missing_e))

        if (
            current_pe is not None
            and pe_obs
            and any(o.value is not None and o.value != current_pe for o in pe_obs)
        ):
            warnings.append(
                "PE10_PERIOD_NOTE: current PE10 and fiscal-year PE10 differ because they "
                "represent different as-of dates — informational, not a mismatch."
            )
        wb2 = load_workbook(workbook_path, data_only=False)
        try:
            if "Inputs" in wb2.sheetnames:
                iws = wb2["Inputs"]
                cols = detect_year_columns(iws, wb2)
                pe_rows: list[int] = []
                for row in range(1, min(iws.max_row or 1, 90) + 1):
                    if exact_field_identity(iws.cell(row, 1).value) == "pe10_fiscal_year":
                        pe_rows.append(row)
                if len(pe_rows) >= 2:
                    r_a, r_b = pe_rows[0], pe_rows[1]
                    for fy in fiscal_years:
                        col = cols.get(fy)
                        if not col:
                            continue
                        a = _safe_float(iws.cell(r_a, col).value)
                        b = _safe_float(iws.cell(r_b, col).value)
                        if a is not None and b is not None and a != b:
                            warnings.append(
                                f"PE10_CROSS_SHEET_MISMATCH: {fy} Inputs row {r_a}={a} vs row {r_b}={b} "
                                "(same metric and date)."
                            )
        finally:
            wb2.close()

        status = "ok"
        if missing_pe or missing_e or crf_failed:
            status = "incomplete"
        return NewCompanyPe10Report(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year_pe10=pe_obs,
            fiscal_year_e10=e_obs,
            current_pe10=Pe10Observation(
                field_role="pe10_current",
                value=current_pe,
                as_of_date=str(current_as_of) if current_as_of else None,
                source_label="Current PE10",
                target_cell="Inputs!B65",
                missing=current_pe is None,
            ),
            current_e10=Pe10Observation(
                field_role="e10_current",
                value=current_e10,
                as_of_date=str(current_as_of) if current_as_of else None,
                source_label="Current E10",
                missing=current_e10 is None,
            ),
            current_stock_price=Pe10Observation(
                field_role="stock_price_current",
                value=current_price,
                as_of_date=str(current_as_of) if current_as_of else None,
                source_label="Current Price",
                target_cell="Inputs!B63",
                missing=current_price is None,
            ),
            chronology_ok=fiscal_years == sorted(fiscal_years),
            duplicate_periods=duplicates,
            zero_as_missing=zeros,
            warnings=warnings,
            status=status,
            summary=(
                f"PE10/E10: {len(fiscal_years) - len(missing_pe)}/{len(fiscal_years)} PE10; "
                f"{len(fiscal_years) - len(missing_e)}/{len(fiscal_years)} E10; "
                f"current_pe10={current_pe}."
            ),
        )

    @staticmethod
    def _dated_series(crf_data, label: str) -> list[tuple[datetime, float]]:
        series = crf_data.historical_metrics.get(label)
        if series is None:
            return []
        dates = crf_data.periods.dates
        out: list[tuple[datetime, float]] = []
        for idx, val in enumerate(series.values):
            if not isinstance(val, (int, float)):
                continue
            dt = _parse_date(dates[idx]) if idx < len(dates) else None
            if dt is None:
                continue
            out.append((dt, float(val)))
        return out

    @staticmethod
    def _match_year(
        fy: str,
        annual: dict[Any, Any],
        dated: list[tuple[datetime, float]],
        target: datetime,
        tolerance: int,
        *,
        role: str,
    ) -> tuple[float | None, str | None, int | None, str | None]:
        looked = AnnualInputsService._lookup_fy(annual, fy)
        if looked is not None:
            return float(looked), target.date().isoformat(), 0, f"{role} annual map"
        if not dated:
            return None, None, None, None
        best = min(dated, key=lambda item: abs((item[0] - target).days))
        delta = (best[0] - target).days
        return best[1], best[0].date().isoformat(), delta, "nearest_crf_observation"

    @staticmethod
    def _find_row(ws, identity: str) -> int | None:
        for row in range(1, min(ws.max_row or 1, 90) + 1):
            matched = exact_field_identity(ws.cell(row, 1).value)
            if matched == identity:
                return row
        return None


def _safe_float(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None
