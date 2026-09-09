"""Annual Inputs: carry historical analyst Inputs; map new-FY PE10/E10 from CRF; refresh current data."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.annual_update import AnnualInputsReport, Pe10Provenance
from services.annual_period_service import detect_workbook_years, detect_year_columns
from services.current_data_refresh_service import CurrentDataRefreshService
from services.custom_run_service import CustomRunService

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9]+")
_PE10_MISMATCH_TOL = 0.05  # absolute PE points


def _norm(label: Any) -> str:
    text = _WS.sub(" ", str(label or "").strip().lower())
    return _PUNCT.sub(" ", text).strip()


def _cell_coordinate(cell: Any, *, row: int, col: int) -> str:
    """Resolve A1 address for read-only EmptyCell / ReadOnlyCell tuples."""
    coord = getattr(cell, "coordinate", None)
    if coord:
        return coord
    cell_row = getattr(cell, "row", None)
    cell_col = getattr(cell, "column", None)
    if cell_row is not None and cell_col is not None:
        return f"{get_column_letter(cell_col)}{cell_row}"
    return f"{get_column_letter(col)}{row}"


def _fy_token(fy: str) -> str:
    return fy if str(fy).startswith("FY") else f"FY{fy}"


class AnnualInputsService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        custom_run_path: Path | None,
        new_fiscal_year: str | None,
        live_price: float | None = None,
    ) -> AnnualInputsReport:
        pe10: Pe10Provenance | None = None
        e10: Pe10Provenance | None = None
        pe10_current: Pe10Provenance | None = None
        mismatch: str | None = None
        historical = 0

        refresh = CurrentDataRefreshService().apply(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            custom_run_path=custom_run_path,
            live_price=live_price,
        )

        if custom_run_path and Path(custom_run_path).exists() and new_fiscal_year:
            pe10, e10, pe10_current, mismatch = self._fill_pe10_e10(
                workbook_path, Path(custom_run_path), new_fiscal_year
            )

        wb = load_workbook(workbook_path, data_only=False)
        try:
            if "Inputs" in wb.sheetnames:
                cols = detect_year_columns(wb["Inputs"], wb)
                if not any(k.startswith("FY") for k in cols):
                    cols = detect_workbook_years(workbook_path)
                fy_keys = [k for k in cols if k.startswith("FY")]
                new_fy = new_fiscal_year or (max(fy_keys) if fy_keys else None)
                for fy, col in cols.items():
                    if not str(fy).startswith("FY") or fy == new_fy:
                        continue
                    for row in range(1, min(wb["Inputs"].max_row or 1, 130) + 1):
                        val = wb["Inputs"].cell(row, col).value
                        if val not in (None, "") and not (
                            isinstance(val, str) and val.startswith("=")
                        ):
                            historical += 1
        finally:
            wb.close()

        pe10_status = "mapped" if pe10 and pe10.source_value is not None else "missing"
        return AnnualInputsReport(
            analysis_id=analysis_id,
            ticker=ticker,
            historical_carried=historical,
            pe10=pe10,
            e10=e10,
            pe10_current=pe10_current,
            pe10_mismatch=mismatch,
            current_data_refreshed=len(refresh.entries),
            summary=(
                f"Inputs: historical value cells={historical}; "
                f"PE10_FY={pe10_status}; "
                f"PE10_current={'mapped' if pe10_current and pe10_current.source_value is not None else 'from_refresh'}; "
                f"{refresh.summary}"
            ),
        )

    def _fill_pe10_e10(
        self, workbook_path: Path, crf_path: Path, new_fy: str
    ) -> tuple[Pe10Provenance | None, Pe10Provenance | None, Pe10Provenance | None, str | None]:
        """Write fiscal-year PE10/E10 from CRF annual series; keep current PE10 separate."""
        token = _fy_token(new_fy)
        annual_pe: dict[Any, Any] = {}
        annual_e10: dict[Any, Any] = {}
        crf_data = None
        try:
            crf_data = CustomRunService().parse(crf_path, crf_path.name)
            annual_pe = dict((crf_data.metadata or {}).get("inputs_annual_pe10") or {})
            annual_e10 = dict((crf_data.metadata or {}).get("inputs_annual_e10") or {})
        except Exception:  # noqa: BLE001 — fall back to direct CRF scan
            crf_data = None

        pe_fy_val = self._lookup_fy(annual_pe, token)
        e10_fy_val = self._lookup_fy(annual_e10, token)

        current_pe = crf_data.scalar("Current PE10") if crf_data is not None else None
        if current_pe is None:
            current_pe = self._scan_crf_scalar(crf_path, prefer_current=True)

        # Fallback: if annual map missing this FY, use nearest FY-end PE10 series — never Current PE10.
        if pe_fy_val is None:
            pe_fy_val = self._scan_crf_fy_series(crf_path, token, label_key="pe10")
        if e10_fy_val is None:
            e10_fy_val = self._scan_crf_fy_series(crf_path, token, label_key="e10")

        wb = load_workbook(workbook_path, data_only=False)
        pe10_prov = e10_prov = current_prov = None
        mismatch = None
        try:
            if "Inputs" not in wb.sheetnames:
                return None, None, None, "ANNUAL_PE10_REQUIRED_INPUT_MISSING"
            ws = wb["Inputs"]
            cols = detect_year_columns(ws, wb)
            if not any(k.startswith("FY") for k in cols):
                cols = detect_workbook_years(workbook_path)
            col = cols.get(token)
            if col is None:
                fy_cols = {k: v for k, v in cols.items() if str(k).startswith("FY")}
                col = max(fy_cols.values()) if fy_cols else None
            if col is None:
                return None, None, None, "ANNUAL_PE10_REQUIRED_INPUT_MISSING"

            pe_row = self._find_label_row(ws, {"pe10", "pe 10"}, skip_current=True) or 57
            e10_row = self._find_label_row(ws, {"e10", "e 10"}, skip_current=True) or 58

            if isinstance(pe_fy_val, (int, float)):
                cell = ws.cell(pe_row, col)
                if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                    cell.value = float(pe_fy_val)
                pe10_prov = Pe10Provenance(
                    target_cell=f"{get_column_letter(col)}{pe_row}",
                    source_workbook=str(crf_path),
                    source_sheet=(crf_data.ticker if crf_data else None) or crf_path.stem,
                    source_label=f"PE10 Annual {token}",
                    source_value=float(pe_fy_val),
                    transformation="CRF fiscal-year-end PE10 (not Current PE10)",
                    field_role="pe10_fiscal_year",
                    fiscal_year=token,
                )
            else:
                pe10_prov = Pe10Provenance(
                    target_cell=f"{get_column_letter(col)}{pe_row}",
                    source_workbook=str(crf_path),
                    source_label="PE10 Annual missing",
                    source_value=None,
                    transformation="ANNUAL_PE10_REQUIRED_INPUT_MISSING",
                    field_role="pe10_fiscal_year",
                    fiscal_year=token,
                )

            if isinstance(e10_fy_val, (int, float)):
                cell = ws.cell(e10_row, col)
                if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                    cell.value = float(e10_fy_val)
                e10_prov = Pe10Provenance(
                    target_cell=f"{get_column_letter(col)}{e10_row}",
                    source_workbook=str(crf_path),
                    source_label=f"E10 Annual {token}",
                    source_value=float(e10_fy_val),
                    transformation="CRF fiscal-year-end E10",
                    field_role="e10_fiscal_year",
                    fiscal_year=token,
                )

            # Current PE10 lives in B65 (current-data block); refresh service usually writes it.
            cur_cell = ws["B65"]
            cur_val = cur_cell.value if isinstance(cur_cell.value, (int, float)) else None
            if cur_val is None and isinstance(current_pe, (int, float)):
                if not (isinstance(cur_cell.value, str) and cur_cell.value.startswith("=")):
                    cur_cell.value = float(current_pe)
                    cur_val = float(current_pe)
            if isinstance(cur_val, (int, float)):
                current_prov = Pe10Provenance(
                    target_cell="B65",
                    source_workbook=str(crf_path),
                    source_label="Current PE10",
                    source_value=float(cur_val),
                    transformation="CRF current/as-of PE10",
                    field_role="pe10_current",
                )

            # Fiscal-year vs current PE10 are different metrics when as-of dates differ.
            if (
                pe10_prov
                and isinstance(pe10_prov.source_value, (int, float))
                and isinstance(cur_val, (int, float))
            ):
                pe10_prov.as_of_date = pe10_prov.as_of_date or (
                    f"fiscal-year-end {token}" if token else None
                )
                if current_prov:
                    current_prov.as_of_date = current_prov.as_of_date or "CRF as-of / current"
                mismatch = (
                    f"PE10_PERIOD_NOTE: {token} fiscal-year PE10="
                    f"{float(pe10_prov.source_value):.4f} as of {pe10_prov.as_of_date}; "
                    f"current PE10={float(cur_val):.4f} as of "
                    f"{(current_prov.as_of_date if current_prov else 'current')}. "
                    f"Distinct metrics — not PE10_CROSS_SHEET_MISMATCH."
                )

            wb.save(workbook_path)
        finally:
            wb.close()
        return pe10_prov, e10_prov, current_prov, mismatch

    @staticmethod
    def _lookup_fy(annual: dict[Any, Any], token: str) -> float | None:
        if token in annual and isinstance(annual[token], (int, float)):
            return float(annual[token])
        year = token.replace("FY", "")
        for key, val in annual.items():
            if str(key).replace(" ", "").upper() in {token, year, f"FY{year}"} and isinstance(
                val, (int, float)
            ):
                return float(val)
        return None

    @staticmethod
    def _find_label_row(ws, keys: set[str], *, skip_current: bool) -> int | None:
        wanted = {k.replace(" ", "") for k in keys}
        for row in range(1, min(ws.max_row or 1, 90) + 1):
            label = _norm(ws.cell(row, 1).value)
            if not label:
                continue
            if skip_current and "current" in label:
                continue
            compact = label.replace(" ", "")
            # Exact / token match only — avoid "e10" matching inside "pe10".
            if compact in wanted:
                return row
            tokens = set(label.split())
            if tokens & keys:
                return row
        return None

    @staticmethod
    def _scan_crf_scalar(crf_path: Path, *, prefer_current: bool) -> float | None:
        crf = load_workbook(crf_path, data_only=True, read_only=True)
        try:
            ws = crf[crf.sheetnames[0]]
            for row_idx, row in enumerate(
                ws.iter_rows(min_row=150, max_row=min(ws.max_row or 1, 230), min_col=1, max_col=2),
                start=150,
            ):
                lab = _norm(row[0].value)
                if not lab:
                    continue
                if prefer_current and "current" in lab and "pe10" in lab.replace(" ", ""):
                    val = row[1].value if len(row) > 1 else None
                    if isinstance(val, (int, float)):
                        return float(val)
            return None
        finally:
            crf.close()

    @staticmethod
    def _scan_crf_fy_series(crf_path: Path, token: str, *, label_key: str) -> float | None:
        """Last-resort: find historical PE10/E10 row (not Current) with a numeric value."""
        crf = load_workbook(crf_path, data_only=True, read_only=True)
        try:
            ws = crf[crf.sheetnames[0]]
            for row in ws.iter_rows(min_row=120, max_row=min(ws.max_row or 1, 160), min_col=1, max_col=8):
                lab = _norm(row[0].value)
                if not lab:
                    continue
                compact = lab.replace(" ", "")
                if label_key not in compact:
                    continue
                if "current" in lab or "min" in lab or "max" in lab or "percentile" in lab:
                    continue
                if lab not in {"pe10", "e10"} and compact not in {"pe10", "e10"}:
                    continue
                for cell in row[1:]:
                    if isinstance(cell.value, (int, float)):
                        return float(cell.value)
            return None
        finally:
            crf.close()
