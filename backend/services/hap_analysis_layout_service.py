"""Discover a safe unused adjacent area for HAP_ANALYSIS writes."""

from __future__ import annotations

from typing import Any

from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from services.formula_utils import is_formula
from services.workbook_flag_service import HAP_ANALYSIS_LABEL, style_hap_analysis_cell


def discover_unused_column(ws: Worksheet, *, start_col: int = 7, end_col: int = 20, scan_rows: int = 40) -> int:
    """Return the first column with no occupied cells in the scan window.

    Does not hard-code a HAP column that might collide across template versions.
    """
    for col in range(start_col, end_col + 1):
        occupied = False
        for row in range(1, scan_rows + 1):
            cell = ws.cell(row, col)
            if isinstance(cell, MergedCell) or cell.value not in (None, ""):
                occupied = True
                break
        if not occupied:
            return col
    return end_col


def cell_is_occupied_or_formula(ws: Worksheet, addr: str) -> bool:
    cell = ws[addr]
    if isinstance(cell, MergedCell):
        return True
    if is_formula(cell.value):
        return True
    return cell.value not in (None, "")


class HapAnalysisLayoutService:
    """Write HAP_ANALYSIS blocks into verified unused adjacent columns."""

    def allocate(self, ws: Worksheet, *, start_col: int = 7) -> tuple[int, str]:
        col = discover_unused_column(ws, start_col=start_col)
        letter = get_column_letter(col)
        return col, letter

    def write_block(
        self,
        ws: Worksheet,
        *,
        rows: list[tuple[str, Any]],
        start_col: int | None = None,
        header: str = HAP_ANALYSIS_LABEL,
    ) -> list[str]:
        """Write label/value pairs. Never overwrite occupied/formula/source cells."""
        col = start_col or discover_unused_column(ws)
        written: list[str] = []
        label_cell = ws.cell(1, col)
        value_cell = ws.cell(1, col + 1)
        if cell_is_occupied_or_formula(ws, label_cell.coordinate) or cell_is_occupied_or_formula(
            ws, value_cell.coordinate
        ):
            col = discover_unused_column(ws, start_col=col + 2)
            label_cell = ws.cell(1, col)
            value_cell = ws.cell(1, col + 1)
        if cell_is_occupied_or_formula(ws, label_cell.coordinate) or cell_is_occupied_or_formula(
            ws, value_cell.coordinate
        ):
            return written
        label_cell.value = header
        style_hap_analysis_cell(label_cell)
        written.append(f"{ws.title}!{label_cell.coordinate}")
        row = 2
        for label, value in rows:
            while (
                cell_is_occupied_or_formula(ws, ws.cell(row, col).coordinate)
                or cell_is_occupied_or_formula(ws, ws.cell(row, col + 1).coordinate)
            ):
                row += 1
                if row > 80:
                    return written
            ws.cell(row, col).value = label
            style_hap_analysis_cell(ws.cell(row, col))
            dest = ws.cell(row, col + 1)
            dest.value = value
            style_hap_analysis_cell(dest)
            written.append(f"{ws.title}!{dest.coordinate}")
            row += 1
        return written
