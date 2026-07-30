"""Cell Classifier — assign CellClass + writable flags from scan + sheet policy."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from openpyxl.utils import get_column_letter

from workbook_mapping.models import (
    CellClass,
    CellRecord,
    FillPriority,
    RegionSummary,
    SheetClassification,
    SheetObjectInventory,
    SheetRole,
    SheetScanMetrics,
    WritePolicy,
)
from workbook_mapping.scanner import RawCell, RawSheet, RawWorkbook
from workbook_mapping.sheet_policies import (
    ANNUAL_DATA_SHEETS,
    AS_REPORTED_SHEETS,
    CONTROL_ROWS,
    HEADER_ROWS,
    LABEL_COLS,
    LQ_STANDARDIZED_SHEETS,
    OUTPUT_SHEETS,
    PERIOD_DATA_START_COL,
    policy_for,
)

SHEET_REF_RE = re.compile(r"'([^']+)'!")


def _deps_from_formula(formula: str, known_sheets: set[str]) -> list[str]:
    refs: set[str] = set()
    for m in SHEET_REF_RE.finditer(formula):
        refs.add(m.group(1))
    for ks in known_sheets:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(ks)}!", formula):
            refs.add(ks)
    return sorted(refs)


def _preview(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str) and v.startswith("="):
        return None
    s = str(v).strip()
    return s[:120] if s else None


def _named_range_index(named_ranges: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Map (sheet, cell_or_range_token) loosely — attach names whose dest contains address."""
    idx: dict[tuple[str, str], list[str]] = defaultdict(list)
    for nr in named_ranges:
        name = nr["name"]
        for dest in nr.get("destinations") or []:
            sheet = dest.get("sheet") or ""
            coord = (dest.get("coord") or "").replace("$", "")
            if sheet and coord:
                idx[(sheet, coord)].append(name)
                # Also index top-left of ranges A1:B2
                if ":" in coord:
                    left = coord.split(":", 1)[0]
                    idx[(sheet, left)].append(name)
    return idx


class CellClassifier:
    """Classify all non-blank cells on a sheet; summarize empty regions."""

    def classify_sheet(
        self,
        raw: RawSheet,
        *,
        known_sheets: set[str],
        named_ranges: list[dict[str, Any]],
        nr_index: dict[tuple[str, str], list[str]],
    ) -> SheetClassification:
        pol = policy_for(raw.name)
        role = SheetRole(pol["role"])
        write_policy = WritePolicy(pol["write_policy"])
        fill_priority = FillPriority(pol["fill_priority"])
        sheet_protected = bool(raw.protection.get("sheet"))

        formula_n = sum(1 for c in raw.cells if c.is_formula)
        const_n = len(raw.cells) - formula_n
        used_area = max(raw.used_max_row, 0) * max(raw.used_max_column, 0)
        blank_n = max(0, used_area - len(raw.cells))
        nonblank = len(raw.cells)
        formula_ratio = (formula_n / nonblank) if nonblank else 0.0

        cells: list[CellRecord] = []
        control_addrs: list[str] = []
        class_counts: dict[str, int] = defaultdict(int)

        hidden_row_set = set(raw.hidden_rows)
        hidden_col_letters = set(raw.hidden_columns)

        for rc in raw.cells:
            record = self._classify_cell(
                rc,
                sheet_name=raw.name,
                role=role,
                write_policy=write_policy,
                fill_priority=fill_priority,
                sheet_protected=sheet_protected,
                known_sheets=known_sheets,
                nr_index=nr_index,
                hidden_row_set=hidden_row_set,
                hidden_col_letters=hidden_col_letters,
            )
            cells.append(record)
            class_counts[record.classification.value] += 1
            if record.notes and "control" in (record.notes or "").lower():
                control_addrs.append(record.address)
            if raw.name in ANNUAL_DATA_SHEETS and rc.row in CONTROL_ROWS and rc.column == 3:
                control_addrs.append(record.address)

        control_addrs = sorted(set(control_addrs))

        # Empty region summary for used range (not every empty cell)
        regions: list[RegionSummary] = []
        if blank_n > 0 and raw.used_max_row and raw.used_max_column:
            regions.append(
                RegionSummary(
                    sheet=raw.name,
                    classification=CellClass.EMPTY,
                    writable=False,
                    start_row=1,
                    end_row=raw.used_max_row,
                    start_col=1,
                    end_col=raw.used_max_column,
                    cell_count=blank_n,
                    notes="Blank cells inside computed used range (aggregated; not enumerated).",
                )
            )

        writable_regions = self._writable_regions(raw.name, cells, fill_priority)
        do_not_write = self._do_not_write_notes(raw.name, write_policy, fill_priority, formula_n)

        objects = SheetObjectInventory(
            merged_cells=raw.merged_cells,
            tables=raw.tables,
            charts=raw.charts,
            data_validations=raw.data_validations,
            conditional_formatting=raw.conditional_formatting,
            freeze_panes=raw.freeze_panes,
            hidden_rows=raw.hidden_rows,
            hidden_columns=raw.hidden_columns,
            protection=raw.protection,
        )

        metrics = SheetScanMetrics(
            declared_max_row=raw.declared_max_row,
            declared_max_column=raw.declared_max_column,
            used_max_row=raw.used_max_row,
            used_max_column=raw.used_max_column,
            nonblank_cells=nonblank,
            formula_cells=formula_n,
            constant_cells=const_n,
            blank_in_used_range=blank_n,
            formula_ratio=round(formula_ratio, 4),
        )

        return SheetClassification(
            name=raw.name,
            index=raw.index,
            state=raw.state,
            role=role,
            write_policy=write_policy,
            fill_priority=fill_priority,
            purpose=pol["purpose"],
            control_cells=control_addrs,
            outbound_sheet_dependencies=dict(raw.outbound_deps.most_common(40)),
            metrics=metrics,
            objects=objects,
            cells=cells,
            regions=regions,
            writable_candidate_regions=writable_regions,
            do_not_write_notes=do_not_write,
        )

    def _classify_cell(
        self,
        rc: RawCell,
        *,
        sheet_name: str,
        role: SheetRole,
        write_policy: WritePolicy,
        fill_priority: FillPriority,
        sheet_protected: bool,
        known_sheets: set[str],
        nr_index: dict[tuple[str, str], list[str]],
        hidden_row_set: set[int],
        hidden_col_letters: set[str],
    ) -> CellRecord:
        col_letter = get_column_letter(rc.column)
        nrs = list(nr_index.get((sheet_name, rc.address), []))
        # Also match bare address without sheet quirks
        nrs = sorted(set(nrs))

        notes_parts: list[str] = []
        if rc.number_format and rc.number_format not in ("General", "0"):
            notes_parts.append(f"num_fmt={rc.number_format}")

        # Protected sheet overrides
        if sheet_protected:
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.PROTECTED,
                writable=False,
                value_preview=_preview(rc.value),
                formula=str(rc.value)[:500] if rc.is_formula else None,
                named_ranges=nrs,
                dependencies=_deps_from_formula(str(rc.value), known_sheets) if rc.is_formula else [],
                notes="Sheet protection enabled",
            )

        if rc.row in hidden_row_set or col_letter in hidden_col_letters:
            # Still classify content but mark reserved/helper
            notes_parts.append("hidden_row_or_col")

        # Named range destination emphasis
        if nrs and not rc.is_formula:
            # keep going for finer class; attach names
            notes_parts.append("named_range_target")

        if rc.is_formula:
            deps = _deps_from_formula(str(rc.value), known_sheets)
            if sheet_name in OUTPUT_SHEETS or role == SheetRole.OUTPUT:
                klass = CellClass.OUTPUT
            else:
                klass = CellClass.FORMULA
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=klass,
                writable=False,
                formula=str(rc.value)[:500],
                named_ranges=nrs,
                dependencies=deps,
                notes="; ".join(notes_parts) or None,
            )

        # Constants
        # Control labels / values on annual sheets
        if sheet_name in ANNUAL_DATA_SHEETS:
            if rc.row in CONTROL_ROWS and rc.column == 1:
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.HELPER,
                    writable=False,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="control_label",
                )
            if rc.row in CONTROL_ROWS and rc.column == 3:
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.WRITABLE_INPUT,
                    writable=True,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="control_value (Ticker/Start Year/End Year)",
                )
            if rc.row in HEADER_ROWS and rc.column >= PERIOD_DATA_START_COL:
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.HELPER,
                    writable=False,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="period_header",
                )
            if rc.column in LABEL_COLS:
                # CapIQ codes / line labels
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.HELPER,
                    writable=False,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="label_or_concept_code",
                )
            if rc.column >= PERIOD_DATA_START_COL and fill_priority == FillPriority.P0:
                # Period body constants — HAP may overwrite from CFM
                if "hidden_row_or_col" in notes_parts:
                    return CellRecord(
                        sheet=sheet_name,
                        address=rc.address,
                        row=rc.row,
                        column=rc.column,
                        classification=CellClass.RESERVED,
                        writable=False,
                        value_preview=_preview(rc.value),
                        named_ranges=nrs,
                        notes="; ".join(notes_parts),
                    )
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.WRITABLE_INPUT,
                    writable=True,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="; ".join(notes_parts) or "annual_period_value",
                )

        if sheet_name in AS_REPORTED_SHEETS:
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.HISTORICAL_DATA,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts) or "as_reported_do_not_map_v0",
            )

        if sheet_name in LQ_STANDARDIZED_SHEETS:
            if rc.is_formula:
                pass  # handled above
            if rc.column in LABEL_COLS or (isinstance(rc.value, str) and not _is_numberish(rc.value)):
                return CellRecord(
                    sheet=sheet_name,
                    address=rc.address,
                    row=rc.row,
                    column=rc.column,
                    classification=CellClass.HELPER,
                    writable=False,
                    value_preview=_preview(rc.value),
                    named_ranges=nrs,
                    notes="; ".join(notes_parts) or "lq_label",
                )
            # LQ values — candidates later (P1) but not writable until mapping exists
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.HISTORICAL_DATA,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts) or "lq_standardized_deferred_P1",
            )

        if role == SheetRole.META:
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.READ_ONLY,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts) or "meta",
            )

        if role == SheetRole.HELPER:
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.HELPER,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts) or None,
            )

        if write_policy == WritePolicy.READ_ONLY:
            klass = CellClass.OUTPUT if sheet_name in OUTPUT_SHEETS else CellClass.READ_ONLY
            # Constants on formula sheets that aren't formulas are unusual — mark read-only
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=klass,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts) or "sheet_read_only_policy",
            )

        # Default hybrid leftovers
        if "hidden_row_or_col" in notes_parts:
            return CellRecord(
                sheet=sheet_name,
                address=rc.address,
                row=rc.row,
                column=rc.column,
                classification=CellClass.RESERVED,
                writable=False,
                value_preview=_preview(rc.value),
                named_ranges=nrs,
                notes="; ".join(notes_parts),
            )

        return CellRecord(
            sheet=sheet_name,
            address=rc.address,
            row=rc.row,
            column=rc.column,
            classification=CellClass.READ_ONLY,
            writable=False,
            value_preview=_preview(rc.value),
            named_ranges=nrs,
            notes="; ".join(notes_parts) or "default_read_only",
        )

    def _writable_regions(
        self,
        sheet_name: str,
        cells: list[CellRecord],
        fill_priority: FillPriority,
    ) -> list[RegionSummary]:
        writable = [c for c in cells if c.writable]
        if not writable:
            return []
        rows = [c.row for c in writable]
        cols = [c.column for c in writable]
        return [
            RegionSummary(
                sheet=sheet_name,
                classification=CellClass.WRITABLE_INPUT,
                writable=True,
                start_row=min(rows),
                end_row=max(rows),
                start_col=min(cols),
                end_col=max(cols),
                cell_count=len(writable),
                notes=f"Bounding box of writable cells; fill_priority={fill_priority.value}",
            )
        ]

    def _do_not_write_notes(
        self,
        sheet_name: str,
        write_policy: WritePolicy,
        fill_priority: FillPriority,
        formula_n: int,
    ) -> list[str]:
        notes = []
        if write_policy == WritePolicy.READ_ONLY:
            notes.append("Entire sheet write_policy=Read-only — HAP must not write any cells.")
        if fill_priority == FillPriority.NEVER:
            notes.append("fill_priority=Never.")
        if fill_priority == FillPriority.P1:
            notes.append("Deferred to P1 (LQ) — do not include in M2 v0.1 annual mapping.")
        if formula_n:
            notes.append(f"{formula_n} formula cells are never writable.")
        if sheet_name in AS_REPORTED_SHEETS:
            notes.append("As-reported LQ content is Historical Data for Mode A v0.")
        return notes


def _is_numberish(v: Any) -> bool:
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


class WorkbookClassifier:
    def __init__(self) -> None:
        self._cell = CellClassifier()

    def classify(self, raw: RawWorkbook) -> list[SheetClassification]:
        known = set(raw.sheetnames)
        nr_index = _named_range_index(raw.named_ranges)
        return [
            self._cell.classify_sheet(
                sheet,
                known_sheets=known,
                named_ranges=raw.named_ranges,
                nr_index=nr_index,
            )
            for sheet in raw.sheets
        ]
