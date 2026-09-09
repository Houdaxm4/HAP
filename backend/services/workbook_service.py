"""Deep workbook parsing and safe value-only writes."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterator

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from models.provenance import CellProvenance
from models.workbook_schema import (
    CellInfo,
    NamedRangeInfo,
    WorkbookStructure,
    WorkbookSummary,
    WorksheetInfo,
)
from settings import parse_cache_dir

CELL_REF_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_ ]+)!([A-Z]+[0-9]+)$")

# Bump when parse output semantics change (invalidates disk cache).
PARSER_SCHEMA_VERSION = "2.0.0"

# Caps for declared dimensions inflated by far-right formatting (e.g. max_column=16382).
MAX_SCAN_ROWS = 400
MAX_SCAN_COLS = 80

PARSE_CACHE_DIR = parse_cache_dir()


class WorkbookParseError(Exception):
    """Raised when a workbook cannot be parsed safely."""


def workbook_sha256(workbook_path: Path) -> str:
    """Content hash used for parse-cache keys."""
    return hashlib.sha256(Path(workbook_path).read_bytes()).hexdigest()


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_formula_cell(cell: Any, value: Any) -> bool:
    if getattr(cell, "data_type", None) == "f":
        return True
    return isinstance(value, str) and value.startswith("=")


def _iter_candidate_cells(sheet: Worksheet) -> Iterator[Any]:
    """
    Iterate cells that may hold content without walking inflated max_column ranges.

    Prefer openpyxl's sparse cell map when present; otherwise scan within safe caps.
    """
    cells_map = getattr(sheet, "_cells", None)
    if cells_map:
        # Sparse map includes style-only empties; caller filters blanks.
        yield from cells_map.values()
        return

    max_r = min(sheet.max_row or 1, MAX_SCAN_ROWS)
    max_c = min(sheet.max_column or 1, MAX_SCAN_COLS)
    for row in sheet.iter_rows(min_row=1, max_row=max_r, max_col=max_c):
        yield from row


def _meaningful_used_bounds(
    nonempty_coords: list[tuple[int, int]], sheet: Worksheet
) -> tuple[int, int]:
    """Used range from nonempty cells, capped; falls back to capped declared dims."""
    if nonempty_coords:
        used_r = max(r for r, _ in nonempty_coords)
        used_c = max(c for _, c in nonempty_coords)
        return used_r, used_c
    return (
        min(sheet.max_row or 0, MAX_SCAN_ROWS),
        min(sheet.max_column or 0, MAX_SCAN_COLS),
    )


class WorkbookService:
    """Inspect, parse, and safely update Excel workbooks."""

    def __init__(self, cache_dir: Path | None = None, use_cache: bool = True) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else parse_cache_dir()
        self.use_cache = use_cache
        # In-process memo: (sha256, schema) -> structure.
        self._memory_cache: dict[tuple[str, str], WorkbookStructure] = {}
        self.parse_call_count = 0
        self.cache_hit_count = 0
        self.last_parse_timings: dict[str, float | str] = {}

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

    def cache_path_for(self, sha256: str) -> Path:
        return self.cache_dir / f"{sha256}_{PARSER_SCHEMA_VERSION}.json"

    def parse_structure(
        self,
        workbook_path: Path,
        original_filename: str,
        *,
        use_cache: bool | None = None,
    ) -> WorkbookStructure:
        """
        Parse workbook structure: worksheets, formulas, values, named ranges.

        The workbook is opened and not modified.
        Blank cells inside the used range are counted but not enumerated (aggregated),
        so manifests stay small when Excel reports inflated max_column values.
        """
        self.parse_call_count += 1
        path = Path(workbook_path)
        timings: dict[str, float | str] = {}
        t_all = time.perf_counter()

        t0 = time.perf_counter()
        digest = workbook_sha256(path)
        timings["hash_ms"] = (time.perf_counter() - t0) * 1000.0
        cache_enabled = self.use_cache if use_cache is None else use_cache
        cache_key = (digest, PARSER_SCHEMA_VERSION)

        if cache_enabled and cache_key in self._memory_cache:
            self.cache_hit_count += 1
            cached = self._memory_cache[cache_key].model_copy(deep=True)
            cached.workbook_filename = original_filename
            timings["cache"] = "memory"
            timings["total_ms"] = (time.perf_counter() - t_all) * 1000.0
            self.last_parse_timings = timings
            return cached

        disk_path = self.cache_path_for(digest)
        if cache_enabled and disk_path.exists():
            t0 = time.perf_counter()
            try:
                with disk_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                structure = WorkbookStructure.model_validate(payload)
                structure.workbook_filename = original_filename
                self._memory_cache[cache_key] = structure.model_copy(deep=True)
                self.cache_hit_count += 1
                timings["cache"] = "disk"
                timings["deserialize_ms"] = (time.perf_counter() - t0) * 1000.0
                timings["total_ms"] = (time.perf_counter() - t_all) * 1000.0
                self.last_parse_timings = timings
                return structure
            except Exception:  # noqa: BLE001 — corrupt cache: reparse
                try:
                    disk_path.unlink(missing_ok=True)
                except OSError:
                    pass

        structure = self._parse_structure_uncached(path, original_filename, timings)
        timings["total_ms"] = (time.perf_counter() - t_all) * 1000.0
        timings["cache"] = "miss"
        self.last_parse_timings = timings

        if cache_enabled:
            self._memory_cache[cache_key] = structure.model_copy(deep=True)
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                with disk_path.open("w", encoding="utf-8") as handle:
                    json.dump(structure.model_dump(), handle, indent=2, default=str)
            except OSError:
                pass

        return structure

    def _parse_structure_uncached(
        self,
        workbook_path: Path,
        original_filename: str,
        timings: dict[str, float | str],
    ) -> WorkbookStructure:
        t0 = time.perf_counter()
        workbook = load_workbook(workbook_path, read_only=False, data_only=False)
        timings["load_ms"] = (time.perf_counter() - t0) * 1000.0
        try:
            t_scan = time.perf_counter()
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
                nonempty_coords: list[tuple[int, int]] = []

                for cell in _iter_candidate_cells(sheet):
                    value = cell.value
                    if _is_blank(value):
                        continue
                    nonempty_coords.append((cell.row, cell.column))
                    non_empty_cell_count += 1
                    address = cell.coordinate
                    if _is_formula_cell(cell, value):
                        sheet_formula_count += 1
                        formula_count += 1
                        cells.append(
                            CellInfo(
                                address=address,
                                value=value,
                                data_type="formula",
                                formula=str(value),
                                is_formula=True,
                            )
                        )
                    else:
                        sheet_value_count += 1
                        cells.append(
                            CellInfo(
                                address=address,
                                value=value,
                                data_type="value",
                                is_formula=False,
                            )
                        )

                used_r, used_c = _meaningful_used_bounds(nonempty_coords, sheet)
                used_area = max(used_r, 0) * max(used_c, 0)
                sheet_blank_count = max(0, used_area - (sheet_value_count + sheet_formula_count))

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

            timings["scan_ms"] = (time.perf_counter() - t_scan) * 1000.0

            t_nr = time.perf_counter()
            named_ranges = self._parse_named_ranges(workbook)
            timings["named_ranges_ms"] = (time.perf_counter() - t_nr) * 1000.0

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
        target = cell.upper()
        for sheet in structure.worksheets:
            if sheet.name != worksheet:
                continue
            for cell_info in sheet.cells:
                if cell_info.address == target:
                    return cell_info.is_formula
            return False
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


__all__ = [
    "WorkbookService",
    "WorkbookParseError",
    "PARSER_SCHEMA_VERSION",
    "workbook_sha256",
    "get_column_letter",
]
