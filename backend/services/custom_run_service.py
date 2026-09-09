"""Parse Bloomberg-derived Custom_Run_Filter workbooks (HAP v1 product input).

Layout constants are taken from production Custom_Run_Filter workbooks for
AAPL, MSFT, AMZN, and TJX (see validation_campaign/reports/CRF_REVERSE_ENGINEERING.md).
Do not invent worksheet names — production files are the source of truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.custom_run import CustomRunData, CustomRunPeriods, CustomRunSeries

# Observed identically on AAPL / MSFT / AMZN / TJX production CRF exports.
# Sheets: [<TICKER>, Summary]. Period width: 102. Numeric trailer from row 265.
_META_START = 2
_META_END = 12
_DATE_ROW = 15
_FISCAL_QUARTER_ROW = 16
_SERIES_START = 18
_FISCAL_YEAR_ROW = 146
_SERIES_END = 153  # includes post–Fiscal Year wide series band (rows 147–153)
_SCALAR_START = 158
_SCALAR_END = 261
_PE10_HEADER_ROW = 264
_PE10_DATA_START = 265

_MARKET_KEYS = {
    "Current Price (Live Price)",
    "Current Market Capitalization",
    "Current Enterprise Value (not-diluted)",
    "Current Dividend Yield",
    "Current Dividend Rate",
    "Shares Outstanding Diluted Average (MM)",
}

_VALUATION_KEYS = {
    "WACC",
    "Current PE10",
    "Current E10",
    "Current Graham Instrinsic Value",
    "Graham Instrinsic Value in 7 Years",
    "Graham Expected Annualized Return",
    "Expected Return @ Current Price",
    "Expected Return Price Plus Dividends - Given Current Price",
    "Max Current Price to Buy",
    "1st Exit Price",
    "2nd Exit Price",
    "Approximate Residual Earnings Value",
    "High Price in 10 years",
    "Low Price in 10 years",
    "ROC Greenblatt",
    "ROC - WACC",
    "EBIT TTM/EV",
    "Current Max PE10 to Enter (Lowest PE10 or 7PE10)",
}

_QUALITY_KEYS = {
    "Final Score",
    "Franchise Power",
    "Quality_FPFS",
    "P_FS",
    "P_SNOA",
    "P_ROA10",
    "P_ROC10",
    "P_CFOA10",
    "P_MG",
    "P_MS",
    "P_MM",
    "ROA10",
    "ROC10",
    "CFOA",
    "SNOA (Scaled Net Operating Assets)",
    "Profit Margin Growth",
    "Profit Margin Stability",
    "Number of Consecutive Positive Growth Margins",
    "ROCE",
    "ROCE Fiscal Year",
    "ROCE 5 Fiscal Years",
    "ROCE 10 Fiscal Years",
}


class CustomRunParseError(Exception):
    """Raised when the Custom_Run_Filter workbook cannot be parsed."""


class CustomRunService:
    """Load and parse Bloomberg Custom_Run_Filter.xlsx into CustomRunData."""

    def parse(self, file_path: Path, original_filename: str) -> CustomRunData:
        suffix = file_path.suffix.lower()
        if suffix not in {".xlsx", ".xlsm", ".xls"}:
            raise CustomRunParseError(
                f"Unsupported custom_run_filter format '{suffix}'. "
                "HAP v1 expects a Bloomberg-derived Excel workbook (.xlsx)."
            )

        workbook = load_workbook(file_path, read_only=True, data_only=True)
        try:
            if "Summary" not in workbook.sheetnames:
                raise CustomRunParseError(
                    "Custom_Run_Filter workbook is missing required worksheet 'Summary'."
                )
            ticker_sheet_name = self._resolve_ticker_sheet(workbook.sheetnames)
            # Production CRFs are ~4k rows; materialize once (read_only random .cell is unusable).
            ticker_rows = self._sheet_matrix(workbook[ticker_sheet_name])
            summary_rows = self._sheet_matrix(workbook["Summary"])

            self._assert_observed_anchors(ticker_rows)

            metadata = self._parse_meta_block(ticker_rows)
            periods = self._parse_periods(ticker_rows)
            historical = self._parse_series_block(ticker_rows, periods)
            annual_pe = self._augment_annual_pe10_e10(ticker_rows, periods, historical)
            if annual_pe:
                metadata["inputs_annual_pe10"] = annual_pe.get("PE10") or {}
                metadata["inputs_annual_e10"] = annual_pe.get("E10") or {}
            scalars = self._parse_scalar_block(ticker_rows)
            summary = self._parse_summary(summary_rows)

            ticker = str(
                metadata.get("Ticker")
                or summary.get("Ticker")
                or ticker_sheet_name
            ).strip().upper()
            company = _optional_str(metadata.get("Company") or summary.get("Company"))

            market_data = self._section_from_pools(
                summary, scalars, metadata, keys=_MARKET_KEYS
            )
            for key in list(_MARKET_KEYS):
                if key in summary and summary[key] is not None:
                    market_data[key] = summary[key]

            valuation_metrics = self._section_from_pools(
                summary, scalars, metadata, keys=_VALUATION_KEYS
            )
            quality_metrics = self._section_from_pools(
                summary, scalars, metadata, keys=_QUALITY_KEYS
            )

            proprietary = {
                key: value
                for key, value in {**scalars, **summary}.items()
                if key not in market_data
                and key not in valuation_metrics
                and key not in quality_metrics
                and key not in {"Company", "Ticker"}
            }

            assumptions: dict[str, Any] = {}
            wacc = valuation_metrics.get("WACC")
            if wacc is None:
                wacc = self._latest_series_value(historical, "WACC")
            if wacc is not None:
                assumptions["wacc"] = wacc
                valuation_metrics.setdefault("WACC", wacc)

            return CustomRunData(
                source_filename=original_filename,
                ticker=ticker,
                company=company,
                ticker_sheet_name=ticker_sheet_name,
                metadata=metadata,
                summary=summary,
                market_data=market_data,
                historical_metrics=historical,
                proprietary_metrics=proprietary,
                valuation_metrics=valuation_metrics,
                quality_metrics=quality_metrics,
                assumptions=assumptions,
                scalars=scalars,
                periods=periods,
                period_count=len(periods.fiscal_quarters),
                series_count=len(historical),
                summary_field_count=len(summary),
            )
        finally:
            workbook.close()

    @staticmethod
    def _resolve_ticker_sheet(sheetnames: list[str]) -> str:
        non_summary = [name for name in sheetnames if name != "Summary"]
        if not non_summary:
            raise CustomRunParseError(
                "Custom_Run_Filter workbook has no ticker worksheet (only Summary found)."
            )
        return non_summary[0]

    @staticmethod
    def _sheet_matrix(worksheet: Any) -> list[list[Any]]:
        """Read a worksheet once into a dense 1-indexed-friendly row list (0-based)."""
        rows: list[list[Any]] = []
        for row in worksheet.iter_rows(values_only=True):
            cells = list(row)
            last = 0
            for idx, value in enumerate(cells, start=1):
                if value is not None and not (isinstance(value, str) and value.strip() == ""):
                    last = idx
            rows.append(cells[:last])
        return rows

    @staticmethod
    def _cell(rows: list[list[Any]], row_idx: int, col_idx: int) -> Any:
        """1-based row/col access into a materialized sheet matrix."""
        if row_idx < 1 or row_idx > len(rows):
            return None
        row = rows[row_idx - 1]
        if col_idx < 1 or col_idx > len(row):
            return None
        return row[col_idx - 1]

    def _assert_observed_anchors(self, rows: list[list[Any]]) -> None:
        """Fail fast if production anchors are not present at observed rows."""
        date_label = self._cell(rows, _DATE_ROW, 1)
        fq_label = self._cell(rows, _FISCAL_QUARTER_ROW, 1)
        fy_label = self._cell(rows, _FISCAL_YEAR_ROW, 1)
        if str(date_label).strip().lower() != "date":
            raise CustomRunParseError(
                f"Expected 'date' at ticker sheet row {_DATE_ROW}, found {date_label!r}."
            )
        if str(fq_label).strip().lower() != "fiscal quarter":
            raise CustomRunParseError(
                f"Expected 'Fiscal Quarter' at ticker sheet row {_FISCAL_QUARTER_ROW}, "
                f"found {fq_label!r}."
            )
        if str(fy_label).strip().lower() != "fiscal year":
            raise CustomRunParseError(
                f"Expected 'Fiscal Year' at ticker sheet row {_FISCAL_YEAR_ROW}, "
                f"found {fy_label!r}."
            )

    def _parse_meta_block(self, rows: list[list[Any]]) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        for row_idx in range(_META_START, _META_END + 1):
            label = self._cell(rows, row_idx, 1)
            value = self._cell(rows, row_idx, 2)
            if label is None or str(label).strip() == "":
                continue
            meta[str(label).strip()] = _normalize_value(value)
        return meta

    def _parse_periods(self, rows: list[list[Any]]) -> CustomRunPeriods:
        dates = self._row_values(rows, _DATE_ROW)
        quarters = self._row_values(rows, _FISCAL_QUARTER_ROW)
        years = self._row_values(rows, _FISCAL_YEAR_ROW)
        return CustomRunPeriods(
            dates=[_stringify_period(v) for v in dates],
            fiscal_quarters=[_stringify_period(v) for v in quarters],
            fiscal_years=[_stringify_period(v) for v in years],
        )

    def _parse_series_block(
        self,
        rows: list[list[Any]],
        periods: CustomRunPeriods,
    ) -> dict[str, CustomRunSeries]:
        expected = len(periods.fiscal_quarters) or len(periods.dates)
        series: dict[str, CustomRunSeries] = {}
        for row_idx in range(_SERIES_START, _SERIES_END + 1):
            if row_idx == _FISCAL_YEAR_ROW:
                continue
            label = self._cell(rows, row_idx, 1)
            if label is None or str(label).strip() == "":
                continue
            label_text = str(label).strip()
            if label_text.lower() in {"date", "fiscal quarter", "fiscal year"}:
                continue
            values = self._row_values(rows, row_idx)
            if expected and len(values) > expected:
                values = values[:expected]
            while expected and len(values) < expected:
                values.append(None)
            numeric = [_as_float(v) for v in values]
            populated = sum(1 for v in numeric if v is not None)
            if populated == 0:
                continue
            kind = "annual_aligned" if "fiscal year" in label_text.lower() else "quarterly"
            series[label_text] = CustomRunSeries(
                label=label_text,
                values=numeric,
                kind=kind,
            )
        return series

    def _parse_scalar_block(self, rows: list[list[Any]]) -> dict[str, Any]:
        scalars: dict[str, Any] = {}
        for row_idx in range(_SCALAR_START, _SCALAR_END + 1):
            label = self._cell(rows, row_idx, 1)
            value = self._cell(rows, row_idx, 2)
            if label is None or str(label).strip() == "":
                continue
            if isinstance(label, (int, float)) and value is not None and row_idx >= _PE10_HEADER_ROW:
                break
            label_text = str(label).strip()
            if label_text.replace(".", "", 1).isdigit():
                continue
            scalars[label_text] = _normalize_value(value)
        return scalars

    def _parse_summary(self, rows: list[list[Any]]) -> dict[str, Any]:
        if not rows:
            raise CustomRunParseError("Summary worksheet is empty.")
        header_row = rows[0]
        headers = [
            str(cell).strip()
            for cell in header_row
            if cell is not None and str(cell).strip() != ""
        ]
        if not headers:
            raise CustomRunParseError("Summary worksheet is missing a header row.")
        values_row = rows[1] if len(rows) > 1 else []
        summary: dict[str, Any] = {}
        for index, header in enumerate(headers):
            raw = values_row[index] if index < len(values_row) else None
            summary[header] = _normalize_value(raw)
        return summary

    def _row_values(self, rows: list[list[Any]], row_idx: int) -> list[Any]:
        """Return values from column B onward (allow leading blanks; trim trailing)."""
        values: list[Any] = []
        # Production CRFs span ~100 quarterly columns; PE10/E10 start far right of B.
        for col in range(2, 221):
            values.append(self._cell(rows, row_idx, col))
        while values and values[-1] is None:
            values.pop()
        return values

    def _augment_annual_pe10_e10(
        self,
        rows: list[list[Any]],
        periods: CustomRunPeriods,
        historical: dict[str, CustomRunSeries],
    ) -> dict[str, dict[str, float]]:
        """Collapse quarterly PE10/E10 to fiscal-year-end annual points (not lag trailer)."""
        years = periods.fiscal_years
        result: dict[str, dict[str, float]] = {}
        if not years:
            return result
        for label, row_idx in (("E10", 132), ("PE10", 133)):
            raw = self._row_values(rows, row_idx)
            if not raw:
                existing = historical.get(label)
                raw = list(existing.values) if existing else []
            if not raw:
                continue
            annual = _collapse_to_fy_end(years, raw)
            if not annual:
                continue
            result[label] = annual
            ordered_fys = sorted(annual.keys())
            historical[f"{label} Annual"] = CustomRunSeries(
                label=f"{label} Annual",
                values=[annual[fy] for fy in ordered_fys],
                kind="annual_aligned",
            )
            if label not in historical:
                n = min(len(raw), len(years))
                historical[label] = CustomRunSeries(
                    label=label,
                    values=[_as_float(v) for v in raw[:n]],
                    kind="quarterly",
                )
        return result

    @staticmethod
    def annual_metric_by_fy(
        historical: dict[str, CustomRunSeries],
        periods: CustomRunPeriods,
        label: str,
    ) -> dict[str, float]:
        """Return {FY2016: value, ...} for a quarterly series collapsed to FY-end."""
        annual_key = f"{label} Annual"
        if annual_key in historical and historical[annual_key].kind == "annual_aligned":
            years: list[str] = []
            seen: set[str] = set()
            for y in periods.fiscal_years:
                token = _fy_token(y)
                if token and token not in seen:
                    seen.add(token)
                    years.append(token)
            series = historical[annual_key]
            out: dict[str, float] = {}
            for fy, val in zip(years, series.values):
                if val is not None:
                    out[fy] = float(val)
            if out:
                return out
        series = historical.get(label)
        if series is None:
            return {}
        return _collapse_to_fy_end(periods.fiscal_years, list(series.values))

    @staticmethod
    def _section_from_pools(
        *pools: dict[str, Any],
        keys: set[str],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in keys:
            for pool in pools:
                if key in pool and pool[key] is not None:
                    out[key] = pool[key]
                    break
        return out

    @staticmethod
    def _latest_series_value(
        historical: dict[str, CustomRunSeries],
        label: str,
    ) -> float | None:
        series = historical.get(label)
        if series is None:
            return None
        for value in reversed(series.values):
            if value is not None:
                return value
        return None


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stringify_period(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fy_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "").upper()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        return f"FY{digits[-4:]}"
    return None


def _collapse_to_fy_end(
    fiscal_years: list[str],
    values: list[Any],
) -> dict[str, float]:
    """Take the last non-null value in each fiscal year (FY-end / Q4 column)."""
    last_by_fy: dict[str, float] = {}
    for idx, year_raw in enumerate(fiscal_years):
        token = _fy_token(year_raw)
        if not token:
            continue
        if idx >= len(values):
            break
        num = _as_float(values[idx])
        if num is None:
            continue
        last_by_fy[token] = num
    return last_by_fy
