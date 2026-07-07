"""Read-only workbook inspection using openpyxl."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel


class WorkbookSummary(BaseModel):
    """Summary statistics for a prefilled workbook."""

    workbook_filename: str
    worksheet_names: list[str]
    sheet_count: int
    visible_sheets: list[str]
    hidden_sheets: list[str]
    formula_count: int
    non_empty_cell_count: int


class WorkbookService:
    """Inspect Excel workbooks without modifying them."""

    def read_summary(self, workbook_path: Path, original_filename: str) -> WorkbookSummary:
        """
        Read workbook metadata and cell statistics.

        The workbook is opened read-only and is not modified.
        """
        workbook = load_workbook(workbook_path, read_only=False, data_only=False)

        try:
            worksheet_names = list(workbook.sheetnames)
            visible_sheets: list[str] = []
            hidden_sheets: list[str] = []
            formula_count = 0
            non_empty_cell_count = 0

            for name in worksheet_names:
                sheet = workbook[name]
                if self._is_hidden(sheet):
                    hidden_sheets.append(name)
                else:
                    visible_sheets.append(name)

                formula_count += self._count_formulas(sheet)
                non_empty_cell_count += self._count_non_empty_cells(sheet)

            return WorkbookSummary(
                workbook_filename=original_filename,
                worksheet_names=worksheet_names,
                sheet_count=len(worksheet_names),
                visible_sheets=visible_sheets,
                hidden_sheets=hidden_sheets,
                formula_count=formula_count,
                non_empty_cell_count=non_empty_cell_count,
            )
        finally:
            workbook.close()

    @staticmethod
    def _is_hidden(sheet: Worksheet) -> bool:
        """Return True when the worksheet is hidden or very hidden."""
        state = sheet.sheet_state
        return state in ("hidden", "veryHidden")

    @staticmethod
    def _count_formulas(sheet: Worksheet) -> int:
        """Count cells that contain formulas."""
        count = 0
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    count += 1
        return count

    @staticmethod
    def _count_non_empty_cells(sheet: Worksheet) -> int:
        """Count cells with a non-null, non-empty value."""
        count = 0
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None and str(cell.value).strip() != "":
                    count += 1
        return count
