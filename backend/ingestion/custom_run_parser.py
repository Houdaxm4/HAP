"""Parse Bloomberg-derived Custom_Run_Filter workbooks into CustomRunData."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from ingestion.custom_run_schema import (
    KEY_VALUE_SHEETS,
    REQUIRED_WORKSHEETS,
    SHEET_ASSUMPTIONS,
    SHEET_HISTORICAL_METRICS,
    SHEET_MARKET_DATA,
    SHEET_METADATA,
    SHEET_PROPRIETARY_METRICS,
    SHEET_QUALITY_METRICS,
    SHEET_VALUATION_METRICS,
    TIME_SERIES_SHEETS,
    WORKSHEET_ALIASES,
)
from ingestion.models.custom_run_data import CustomRunData, MetricSeries


class CustomRunParseError(Exception):
    """Raised when a Custom_Run_Filter workbook cannot be parsed."""


class CustomRunParser:
    """Read the standardized Bloomberg Custom_Run_Filter workbook structure."""

    def parse(self, file_path: Path, original_filename: str) -> CustomRunData:
        suffix = file_path.suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            raise CustomRunParseError(
                "Custom_Run_Filter must be a Bloomberg-derived Excel workbook (.xlsx). "
                "Mapping CSV files are not part of the HAP v1 product specification."
            )

        workbook = load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet_map = self._resolve_sheets(workbook.sheetnames)
            missing = [name for name in REQUIRED_WORKSHEETS if name not in sheet_map]
            if missing:
                raise CustomRunParseError(
                    "Custom_Run_Filter workbook is missing required worksheets: "
                    f"{', '.join(missing)}. "
                    f"Found: {', '.join(workbook.sheetnames)}"
                )

            metadata = self._parse_key_value_sheet(workbook[sheet_map[SHEET_METADATA]])
            market_data = self._parse_key_value_sheet(
                workbook[sheet_map[SHEET_MARKET_DATA]], numeric=True
            )
            historical = self._parse_time_series_sheet(
                workbook[sheet_map[SHEET_HISTORICAL_METRICS]]
            )
            proprietary = self._parse_time_series_sheet(
                workbook[sheet_map[SHEET_PROPRIETARY_METRICS]]
            )
            valuation = self._parse_time_series_sheet(
                workbook[sheet_map[SHEET_VALUATION_METRICS]]
            )
            quality = self._parse_metric_value_sheet(
                workbook[sheet_map[SHEET_QUALITY_METRICS]]
            )
            assumptions = self._parse_key_value_sheet(
                workbook[sheet_map[SHEET_ASSUMPTIONS]], numeric=True
            )

            return CustomRunData(
                source_filename=original_filename,
                metadata=metadata,
                market_data=market_data,
                historical_metrics=historical,
                proprietary_metrics=proprietary,
                valuation_metrics=valuation,
                quality_metrics=quality,
                assumptions=assumptions,
                worksheets_found=list(workbook.sheetnames),
            )
        finally:
            workbook.close()

    def _resolve_sheets(self, sheetnames: list[str]) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for actual_name in sheetnames:
            canonical = WORKSHEET_ALIASES.get(actual_name.strip().lower(), actual_name.strip())
            resolved[canonical] = actual_name
        return resolved

    def _parse_key_value_sheet(
        self,
        sheet: Worksheet,
        *,
        numeric: bool = False,
    ) -> dict[str, float | str | None]:
        result: dict[str, float | str | None] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            field = str(row[0]).strip()
            if not field:
                continue
            raw_value = row[1] if len(row) > 1 else None
            result[field] = self._coerce_value(raw_value, numeric=numeric)
        return result

    def _parse_time_series_sheet(self, sheet: Worksheet) -> list[MetricSeries]:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []

        headers = [self._normalize_period(value) for value in rows[0][1:]]
        periods = [header for header in headers if header]
        if not periods:
            raise CustomRunParseError(
                f"Worksheet '{sheet.title}' has no period headers in row 1."
            )

        series_list: list[MetricSeries] = []
        for row in rows[1:]:
            if not row or row[0] is None:
                continue
            metric = str(row[0]).strip()
            if not metric:
                continue
            values: dict[str, float | str | None] = {}
            for index, period in enumerate(periods):
                cell_index = index + 1
                raw = row[cell_index] if cell_index < len(row) else None
                values[period] = self._coerce_value(raw, numeric=True)
            series_list.append(MetricSeries(metric=metric, values=values))
        return series_list

    def _parse_metric_value_sheet(self, sheet: Worksheet) -> list[MetricSeries]:
        """Quality metrics: metric in col A, value/score in col B."""
        series_list: list[MetricSeries] = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            metric = str(row[0]).strip()
            if not metric:
                continue
            value = self._coerce_value(row[1] if len(row) > 1 else None, numeric=True)
            series_list.append(MetricSeries(metric=metric, values={"current": value}))
        return series_list

    @staticmethod
    def _normalize_period(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        fy_match = re.match(r"^FY\s*'?(\d{2}|\d{4})$", text, re.IGNORECASE)
        if fy_match:
            year = fy_match.group(1)
            if len(year) == 2:
                year = f"20{year}"
            return f"FY{year}"
        if re.fullmatch(r"20\d{2}|19\d{2}", text):
            return f"FY{text}"
        return text

    @staticmethod
    def _coerce_value(raw: Any, *, numeric: bool = False) -> float | str | None:
        if raw is None:
            return None
        if isinstance(raw, str) and not raw.strip():
            return None
        if numeric:
            try:
                return float(raw)
            except (TypeError, ValueError):
                if isinstance(raw, str):
                    cleaned = raw.replace(",", "").replace("$", "").strip()
                    if cleaned.endswith("%"):
                        cleaned = cleaned[:-1]
                    try:
                        return float(cleaned)
                    except ValueError:
                        return raw.strip()
                return str(raw).strip()
        return str(raw).strip() if not isinstance(raw, (int, float)) else raw
