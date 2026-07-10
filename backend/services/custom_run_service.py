"""Parse and validate custom_run filter files (CSV or XLSX)."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import load_workbook

from models.custom_run import CustomRunEntry, CustomRunMapping
from models.workbook_schema import WorkbookStructure

REQUIRED_COLUMNS = {"worksheet", "cell", "concept", "period"}
OPTIONAL_COLUMNS = {"workbook", "xbrl_tag", "unit", "notes"}


class CustomRunParseError(Exception):
    """Raised when the custom_run filter cannot be parsed or validated."""


class CustomRunService:
    """Load and validate custom_run mapping files."""

    def parse(self, file_path: Path, original_filename: str) -> CustomRunMapping:
        """Parse a custom_run filter from CSV or Excel."""
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            entries = self._parse_csv(file_path)
        elif suffix in {".xlsx", ".xlsm", ".xls"}:
            entries = self._parse_xlsx(file_path)
        else:
            raise CustomRunParseError(
                f"Unsupported custom_run format '{suffix}'. Use CSV or XLSX."
            )

        if not entries:
            raise CustomRunParseError("custom_run filter contains no mapping rows.")

        return CustomRunMapping(
            source_filename=original_filename,
            entry_count=len(entries),
            entries=entries,
        )

    def validate_against_workbook(
        self,
        mapping: CustomRunMapping,
        structure: WorkbookStructure,
    ) -> None:
        """
        Ensure every custom_run mapping targets a worksheet that exists.

        Raises CustomRunParseError when worksheet references are invalid.
        """
        sheet_names = set(structure.worksheet_names)
        missing_sheets: list[str] = []
        for entry in mapping.entries:
            if entry.worksheet not in sheet_names:
                missing_sheets.append(f"{entry.worksheet}!{entry.cell}")

        if missing_sheets:
            unique = sorted(set(missing_sheets))
            preview = ", ".join(unique[:5])
            suffix = f" (+{len(unique) - 5} more)" if len(unique) > 5 else ""
            raise CustomRunParseError(
                "custom_run_filter references worksheets missing from the workbook: "
                f"{preview}{suffix}"
            )

    def _parse_csv(self, file_path: Path) -> list[CustomRunEntry]:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CustomRunParseError("custom_run CSV is missing a header row.")
            columns = {name.strip().lower() for name in reader.fieldnames}
            missing = REQUIRED_COLUMNS - columns
            if missing:
                raise CustomRunParseError(
                    f"custom_run CSV missing required columns: {', '.join(sorted(missing))}"
                )
            return [self._row_to_entry(row) for row in reader if self._row_has_data(row)]

    def _parse_xlsx(self, file_path: Path) -> list[CustomRunEntry]:
        workbook = load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                raise CustomRunParseError("custom_run workbook is empty.")
            headers = [str(value).strip().lower() if value is not None else "" for value in rows[0]]
            header_index = {header: index for index, header in enumerate(headers) if header}
            missing = REQUIRED_COLUMNS - set(header_index)
            if missing:
                raise CustomRunParseError(
                    f"custom_run workbook missing required columns: {', '.join(sorted(missing))}"
                )
            entries: list[CustomRunEntry] = []
            for row in rows[1:]:
                row_dict = {
                    header: row[index] if index < len(row) else None
                    for header, index in header_index.items()
                }
                if self._row_has_data(row_dict):
                    entries.append(self._row_to_entry(row_dict))
            return entries
        finally:
            workbook.close()

    @staticmethod
    def _row_has_data(row: dict[str, object | None]) -> bool:
        return any(value is not None and str(value).strip() != "" for value in row.values())

    def _row_to_entry(self, row: dict[str, object | None]) -> CustomRunEntry:
        normalized = {key.strip().lower(): value for key, value in row.items() if key}
        try:
            return CustomRunEntry(
                workbook=str(normalized.get("workbook") or "prefilled_workbook").strip(),
                worksheet=str(normalized["worksheet"]).strip(),
                cell=str(normalized["cell"]).strip().upper(),
                concept=str(normalized["concept"]).strip(),
                period=str(normalized["period"]).strip(),
                xbrl_tag=self._optional_str(normalized.get("xbrl_tag")),
                unit=self._optional_str(normalized.get("unit")),
                notes=self._optional_str(normalized.get("notes")),
            )
        except KeyError as exc:
            raise CustomRunParseError(f"Invalid custom_run row: missing {exc}") from exc

    @staticmethod
    def _optional_str(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
