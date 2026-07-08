"""Deep workbook parsing and safe value-only writes."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from models.provenance import CellProvenance
from models.workbook_schema import (
    CellInfo,
    NamedRangeInfo,
    WorkbookStructure,
    WorkbookSummary,
    WorksheetInfo,
)

CELL_REF_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_ ]+)!([A-Z]+[0-9]+)$")


class WorkbookParseError(Exception):
    """Raised when a workbook cannot be parsed safely."""


class WorkbookService:
    """Inspect, parse, and safely update Excel workbooks."""

    def read_summary(self, workbook_path: Path, original_filename: str) -> WorkbookSummary:
        """Return high-level workbook statistics without modifying the file."""
        structure = self.parse_structure(workbook_path, original_filename)
        return WorkbookSummary(
            workbook_filename=structure.workbook_filename,
            worksheet_names=structure.worksheet_names,
            sheet_count=len(structure.worksheet_names),
            visible_sheets=structure.visible_sheets,
            hidden_sheets=structure.hidden_sheets,
            formula_count=structure.formula_count,
            non_empty_cell_count=structure.non_empty_cell_count,
        )

    def parse_structure(self, workbook_path: Path, original_filename: str) -> WorkbookStructure:
        """
        Parse workbook structure: worksheets, formulas, values, named ranges.

        The workbook is opened read-only and is not modified.
        """
        workbook = load_workbook(workbook_path, read_only=False, data_only=False)
        try:
            worksheets: list[WorksheetInfo] = []
            visible_sheets: list[str] = []
            hidden_sheets: list[str] = []
            formula_count = 0
            non_empty_cell_count = 0

            for name in workbook.sheetnames:
                sheet = workbook[name]
                visibility = self._sheet_visibility(sheet)
                if visibility == "visible":
                    visible_sheets.append(name)
                else:
                    hidden_sheets.append(name)

                cells: list[CellInfo] = []
                sheet_formula_count = 0
                sheet_value_count = 0
                sheet_blank_count = 0

                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.value is None or str(cell.value).strip() == "":
                            sheet_blank_count += 1
                            cells.append(
                                CellInfo(
                                    address=cell.coordinate,
                                    data_type="blank",
                                    is_formula=False,
                                )
                            )
                            continue

                        non_empty_cell_count += 1
                        if cell.data_type == "f":
                            sheet_formula_count += 1
                            formula_count += 1
                            cells.append(
                                CellInfo(
                                    address=cell.coordinate,
                                    value=cell.value,
                                    data_type="formula",
                                    formula=str(cell.value),
                                    is_formula=True,
                                )
                            )
                        else:
                            sheet_value_count += 1
                            cells.append(
                                CellInfo(
                                    address=cell.coordinate,
                                    value=cell.value,
                                    data_type="value",
                                    is_formula=False,
                                )
                            )

                worksheets.append(
                    WorksheetInfo(
                        name=name,
                        visibility=visibility,
                        formula_count=sheet_formula_count,
                        value_count=sheet_value_count,
                        blank_count=sheet_blank_count,
                        non_empty_cell_count=sheet_value_count + sheet_formula_count,
                        cells=cells,
                    )
                )

            named_ranges = self._parse_named_ranges(workbook)

            return WorkbookStructure(
                workbook_filename=original_filename,
                worksheet_names=list(workbook.sheetnames),
                visible_sheets=visible_sheets,
                hidden_sheets=hidden_sheets,
                named_ranges=named_ranges,
                worksheets=worksheets,
                formula_count=formula_count,
                non_empty_cell_count=non_empty_cell_count,
            )
        finally:
            workbook.close()

    def write_values(
        self,
        source_workbook_path: Path,
        destination_workbook_path: Path,
        provenance_entries: list[CellProvenance],
    ) -> tuple[int, int, int]:
        """
        Copy the source workbook and write only value cells from provenance.

        Returns (filled_count, blank_count, skipped_formula_count).
        Never overwrites formula cells.
        """
        destination_workbook_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_workbook_path, destination_workbook_path)

        workbook = load_workbook(destination_workbook_path)
        try:
            filled_count = 0
            blank_count = 0
            skipped_formula_count = 0

            for entry in provenance_entries:
                sheet = self._get_sheet(workbook, entry.worksheet)
                cell = sheet[entry.cell]

                if cell.data_type == "f" or (
                    isinstance(cell.value, str) and str(cell.value).startswith("=")
                ):
                    entry.status = "skipped_formula"
                    entry.failure_reason = "Cell contains a formula and was not overwritten."
                    skipped_formula_count += 1
                    continue

                if entry.value is None or entry.status != "filled":
                    blank_count += 1
                    continue

                cell.value = entry.value
                filled_count += 1

            workbook.save(destination_workbook_path)
            return filled_count, blank_count, skipped_formula_count
        finally:
            workbook.close()

    def get_cell_value(self, workbook_path: Path, worksheet: str, cell: str) -> Any:
        """Read a single cell value from a workbook."""
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            sheet = self._get_sheet(workbook, worksheet)
            return sheet[cell.upper()].value
        finally:
            workbook.close()

    def cell_contains_formula(self, structure: WorkbookStructure, worksheet: str, cell: str) -> bool:
        """Return True if the target cell is a formula in the parsed structure."""
        for sheet in structure.worksheets:
            if sheet.name != worksheet:
                continue
            for cell_info in sheet.cells:
                if cell_info.address == cell.upper():
                    return cell_info.is_formula
        return False

    @staticmethod
    def make_cell_ref(worksheet: str, cell: str) -> str:
        """Build a stable cell reference key used in provenance and validation."""
        return f"{worksheet}!{cell.upper()}"

    @staticmethod
    def parse_cell_ref(cell_ref: str) -> tuple[str, str]:
        """Split a cell reference into worksheet and cell address."""
        match = CELL_REF_PATTERN.match(cell_ref)
        if not match:
            raise WorkbookParseError(f"Invalid cell reference: {cell_ref}")
        return match.group(1), match.group(2)

    @staticmethod
    def _get_sheet(workbook: Any, worksheet_name: str) -> Worksheet:
        if worksheet_name not in workbook.sheetnames:
            raise WorkbookParseError(f"Worksheet '{worksheet_name}' not found in workbook.")
        return workbook[worksheet_name]

    @staticmethod
    def _sheet_visibility(sheet: Worksheet) -> str:
        state = sheet.sheet_state
        if state == "veryHidden":
            return "veryHidden"
        if state == "hidden":
            return "hidden"
        return "visible"

    @staticmethod
    def _parse_named_ranges(workbook: Any) -> list[NamedRangeInfo]:
        named_ranges: list[NamedRangeInfo] = []
        defined_names = getattr(workbook, "defined_names", None)
        if defined_names is None:
            return named_ranges

        for name in defined_names:
            definition = defined_names[name]
            destinations: list[str] = []
            if definition is not None:
                for worksheet_title, coordinate in definition.destinations:
                    destinations.append(f"{worksheet_title}!{coordinate}")
            named_ranges.append(NamedRangeInfo(name=name, destinations=destinations))
        return named_ranges
