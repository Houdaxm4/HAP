"""Parse and validate custom_run filter files (CSV or XLSX)."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.custom_run import (
    CustomRunEntry,
    CustomRunMapping,
    CustomRunValidationIssue,
    CustomRunValidationReport,
)
from models.workbook_schema import WorkbookStructure

REQUIRED_COLUMNS = {"worksheet", "cell", "concept", "period"}
OPTIONAL_COLUMNS = {
    "workbook",
    "xbrl_tag",
    "unit",
    "notes",
    "ticker",
    "fiscal_date",
    "value",
    "sheet",  # alias for worksheet
}

# FY2024, FY24, 2024FY
ANNUAL_PERIOD_RE = re.compile(r"^(?:FY\s*'?(\d{2}|\d{4})|(\d{4})\s*FY)$", re.IGNORECASE)
# Q1 2024 | Q1'24 | 2024Q1 | 2024-Q1 | 2024 Q1 | 1Q2024
QUARTER_PERIOD_RE = re.compile(
    r"^(?:"
    r"Q([1-4])\s*'?\s*(\d{2}|\d{4})"
    r"|(\d{4})\s*[-/ ]?\s*Q([1-4])"
    r"|([1-4])Q\s*'?\s*(\d{2}|\d{4})"
    r")$",
    re.IGNORECASE,
)
YEAR_ONLY_RE = re.compile(r"^(\d{4})$")
PERIOD_ALIASES = {
    "latest_annual": "latest_annual",
    "latest_year": "latest_annual",
    "latest_fy": "latest_annual",
    "latest_quarter": "latest_quarter",
    "latest_q": "latest_quarter",
    "ttm": "ttm",
    "ytd": "ytd",
}


class CustomRunParseError(Exception):
    """Raised when the custom_run filter cannot be parsed or validated."""


class CustomRunService:
    """Load and validate custom_run mapping files."""

    def parse(self, file_path: Path, original_filename: str) -> CustomRunMapping:
        """Parse a custom_run filter from CSV or Excel."""
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            entries, columns = self._parse_csv(file_path)
        elif suffix in {".xlsx", ".xlsm", ".xls"}:
            entries, columns = self._parse_xlsx(file_path)
        else:
            raise CustomRunParseError(
                f"Unsupported custom_run format '{suffix}'. Use CSV or XLSX."
            )

        if not entries:
            raise CustomRunParseError("custom_run filter contains no mapping rows.")

        return CustomRunMapping(
            source_filename=original_filename,
            entry_count=len(entries),
            columns_found=sorted(columns),
            entries=entries,
        )

    def validate(
        self,
        mapping: CustomRunMapping,
        *,
        analysis_id: str,
        ticker: str,
        structure: WorkbookStructure | None = None,
    ) -> CustomRunValidationReport:
        """
        Validate custom_run_filter contents and produce a report.

        Checks required columns, ticker consistency, fiscal dates, quarter
        sequence, duplicate periods, missing quarters, and numeric consistency.
        Does not populate or modify any workbook template.
        """
        checks: list[CustomRunValidationIssue] = []
        expected_ticker = ticker.strip().upper()

        checks.extend(self._check_required_columns(mapping))
        checks.extend(self._check_ticker(mapping, expected_ticker))
        checks.extend(self._check_fiscal_dates(mapping))
        checks.extend(self._check_duplicate_periods(mapping))
        checks.extend(self._check_quarter_sequence(mapping))
        checks.extend(self._check_missing_quarters(mapping))
        checks.extend(self._check_numeric_consistency(mapping))
        if structure is not None:
            checks.extend(self._check_workbook_references(mapping, structure))

        pass_count = sum(1 for check in checks if check.status == "pass")
        warn_count = sum(1 for check in checks if check.status == "warn")
        fail_count = sum(1 for check in checks if check.status == "fail")
        is_valid = fail_count == 0
        summary = (
            f"custom_run_filter validation {'passed' if is_valid else 'failed'} "
            f"with {pass_count} pass, {warn_count} warn, {fail_count} fail "
            f"across {mapping.entry_count} rows. Template was not populated."
        )

        return CustomRunValidationReport(
            analysis_id=analysis_id,
            ticker=expected_ticker,
            source_filename=mapping.source_filename,
            entry_count=mapping.entry_count,
            columns_found=mapping.columns_found,
            checks=checks,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            is_valid=is_valid,
            summary=summary,
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
        issues = self._check_workbook_references(mapping, structure)
        failures = [issue for issue in issues if issue.status == "fail"]
        if failures:
            raise CustomRunParseError(failures[0].message)

    def _check_required_columns(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        columns = {name.lower() for name in mapping.columns_found}
        # Accept sheet as alias for worksheet.
        normalized = set(columns)
        if "sheet" in normalized:
            normalized.add("worksheet")
        missing = sorted(REQUIRED_COLUMNS - normalized)
        if missing:
            return [
                CustomRunValidationIssue(
                    check_type="required_columns",
                    status="fail",
                    message=f"Missing required columns: {', '.join(missing)}",
                    details={"missing": missing, "found": mapping.columns_found},
                )
            ]
        return [
            CustomRunValidationIssue(
                check_type="required_columns",
                status="pass",
                message=(
                    "Required columns present: "
                    + ", ".join(sorted(REQUIRED_COLUMNS))
                ),
                details={"found": mapping.columns_found},
            )
        ]

    def _check_ticker(
        self,
        mapping: CustomRunMapping,
        expected_ticker: str,
    ) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        ticker_values: list[tuple[int | None, str]] = []

        for entry in mapping.entries:
            if entry.ticker:
                ticker_values.append((entry.row_number, entry.ticker.upper()))
            if entry.concept.strip().lower() == "ticker" and entry.period:
                # Phase-1 style ticker row may store symbol in period/value fields.
                ticker_values.append((entry.row_number, entry.period.strip().upper()))

        if not ticker_values:
            issues.append(
                CustomRunValidationIssue(
                    check_type="ticker",
                    status="warn",
                    message=(
                        f"No ticker column/rows found in custom_run_filter; "
                        f"using analysis ticker '{expected_ticker}'."
                    ),
                    details={"analysis_ticker": expected_ticker},
                )
            )
            return issues

        mismatches = [
            (row_number, value)
            for row_number, value in ticker_values
            if value != expected_ticker
        ]
        if mismatches:
            row_number, value = mismatches[0]
            issues.append(
                CustomRunValidationIssue(
                    check_type="ticker",
                    status="fail",
                    message=(
                        f"Ticker '{value}' in custom_run_filter does not match "
                        f"analysis ticker '{expected_ticker}'."
                    ),
                    row_number=row_number,
                    details={
                        "analysis_ticker": expected_ticker,
                        "filter_tickers": sorted({item[1] for item in ticker_values}),
                    },
                )
            )
        else:
            issues.append(
                CustomRunValidationIssue(
                    check_type="ticker",
                    status="pass",
                    message=f"Ticker matches analysis ticker '{expected_ticker}'.",
                    details={"analysis_ticker": expected_ticker},
                )
            )
        return issues

    def _check_fiscal_dates(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        invalid_periods = 0
        invalid_dates = 0

        for entry in mapping.entries:
            if entry.concept.strip().lower() == "ticker":
                continue

            parsed = self.parse_period(entry.period)
            if parsed is None:
                invalid_periods += 1
                issues.append(
                    CustomRunValidationIssue(
                        check_type="fiscal_dates",
                        status="fail",
                        message=f"Unrecognized fiscal period '{entry.period}'.",
                        row_number=entry.row_number,
                        concept=entry.concept,
                        period=entry.period,
                        cell_ref=f"{entry.worksheet}!{entry.cell}",
                    )
                )
            else:
                entry.fiscal_year = parsed.get("fiscal_year")
                entry.fiscal_quarter = parsed.get("fiscal_quarter")
                entry.is_annual = bool(parsed.get("is_annual"))
                entry.period_alias = parsed.get("alias")

            if entry.fiscal_date:
                if self._parse_fiscal_date(entry.fiscal_date) is None:
                    invalid_dates += 1
                    issues.append(
                        CustomRunValidationIssue(
                            check_type="fiscal_dates",
                            status="fail",
                            message=f"Invalid fiscal_date '{entry.fiscal_date}'.",
                            row_number=entry.row_number,
                            concept=entry.concept,
                            period=entry.period,
                            cell_ref=f"{entry.worksheet}!{entry.cell}",
                        )
                    )

        if invalid_periods == 0 and invalid_dates == 0:
            issues.append(
                CustomRunValidationIssue(
                    check_type="fiscal_dates",
                    status="pass",
                    message="All fiscal periods/dates are recognizable.",
                )
            )
        return issues

    def _check_duplicate_periods(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        concept_period: dict[tuple[str, str], list[CustomRunEntry]] = defaultdict(list)
        cell_targets: dict[tuple[str, str], list[CustomRunEntry]] = defaultdict(list)

        for entry in mapping.entries:
            if entry.concept.strip().lower() == "ticker":
                continue
            concept_period[(entry.concept.lower(), entry.period.upper())].append(entry)
            cell_targets[(entry.worksheet.lower(), entry.cell.upper())].append(entry)

        duplicates = 0
        for (concept, period), rows in concept_period.items():
            if len(rows) <= 1:
                continue
            duplicates += 1
            issues.append(
                CustomRunValidationIssue(
                    check_type="duplicate_periods",
                    status="fail",
                    message=(
                        f"Duplicate concept/period '{rows[0].concept}' / '{rows[0].period}' "
                        f"appears {len(rows)} times."
                    ),
                    concept=rows[0].concept,
                    period=rows[0].period,
                    row_number=rows[0].row_number,
                    details={"row_numbers": [row.row_number for row in rows]},
                )
            )

        for (_sheet, _cell), rows in cell_targets.items():
            if len(rows) <= 1:
                continue
            duplicates += 1
            issues.append(
                CustomRunValidationIssue(
                    check_type="duplicate_periods",
                    status="fail",
                    message=(
                        f"Duplicate target cell {rows[0].worksheet}!{rows[0].cell} "
                        f"appears {len(rows)} times."
                    ),
                    cell_ref=f"{rows[0].worksheet}!{rows[0].cell}",
                    row_number=rows[0].row_number,
                    details={"row_numbers": [row.row_number for row in rows]},
                )
            )

        if duplicates == 0:
            issues.append(
                CustomRunValidationIssue(
                    check_type="duplicate_periods",
                    status="pass",
                    message="No duplicate concept/period or target-cell mappings.",
                )
            )
        return issues

    def _check_quarter_sequence(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        by_concept: dict[str, list[tuple[int, int, CustomRunEntry]]] = defaultdict(list)

        for entry in mapping.entries:
            if entry.fiscal_year is None or entry.fiscal_quarter is None:
                continue
            by_concept[entry.concept.lower()].append(
                (entry.fiscal_year, entry.fiscal_quarter, entry)
            )

        if not by_concept:
            issues.append(
                CustomRunValidationIssue(
                    check_type="quarter_sequence",
                    status="pass",
                    message="No quarterly periods to sequence-check.",
                )
            )
            return issues

        sequence_failures = 0
        for concept, points in by_concept.items():
            ordered = sorted(points, key=lambda item: (item[0], item[1]))
            # Appearance order in file should not go backwards in fiscal time
            # when multiple quarters are listed for the same concept.
            appearance = [
                (entry.fiscal_year, entry.fiscal_quarter)
                for entry in mapping.entries
                if entry.concept.lower() == concept
                and entry.fiscal_year is not None
                and entry.fiscal_quarter is not None
            ]
            if appearance != sorted(appearance):
                sequence_failures += 1
                issues.append(
                    CustomRunValidationIssue(
                        check_type="quarter_sequence",
                        status="warn",
                        message=(
                            f"Quarter sequence for '{ordered[0][2].concept}' is not "
                            "chronological in the filter file."
                        ),
                        concept=ordered[0][2].concept,
                        details={
                            "appearance_order": [
                                f"Q{quarter} {year}" for year, quarter in appearance
                            ],
                            "expected_order": [
                                f"Q{quarter} {year}" for year, quarter, _ in ordered
                            ],
                        },
                    )
                )

        if sequence_failures == 0:
            issues.append(
                CustomRunValidationIssue(
                    check_type="quarter_sequence",
                    status="pass",
                    message="Quarter sequences are chronological where present.",
                )
            )
        return issues

    def _check_missing_quarters(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        by_concept_year: dict[tuple[str, int], set[int]] = defaultdict(set)
        labels: dict[str, str] = {}

        for entry in mapping.entries:
            if entry.fiscal_year is None or entry.fiscal_quarter is None:
                continue
            key = (entry.concept.lower(), entry.fiscal_year)
            by_concept_year[key].add(entry.fiscal_quarter)
            labels[entry.concept.lower()] = entry.concept

        missing_count = 0
        for (concept_key, year), quarters in sorted(by_concept_year.items()):
            if len(quarters) <= 1:
                continue
            expected = set(range(min(quarters), max(quarters) + 1))
            missing = sorted(expected - quarters)
            if not missing:
                continue
            missing_count += 1
            issues.append(
                CustomRunValidationIssue(
                    check_type="missing_quarters",
                    status="warn",
                    message=(
                        f"Missing quarter(s) for '{labels[concept_key]}' in FY{year}: "
                        + ", ".join(f"Q{q}" for q in missing)
                    ),
                    concept=labels[concept_key],
                    period=f"FY{year}",
                    details={
                        "year": year,
                        "present_quarters": sorted(quarters),
                        "missing_quarters": missing,
                    },
                )
            )

        if missing_count == 0:
            issues.append(
                CustomRunValidationIssue(
                    check_type="missing_quarters",
                    status="pass",
                    message="No missing quarters detected in provided ranges.",
                )
            )
        return issues

    def _check_numeric_consistency(self, mapping: CustomRunMapping) -> list[CustomRunValidationIssue]:
        issues: list[CustomRunValidationIssue] = []
        has_value_column = "value" in {name.lower() for name in mapping.columns_found}

        if not has_value_column:
            issues.append(
                CustomRunValidationIssue(
                    check_type="numeric_consistency",
                    status="pass",
                    message="No value column present; numeric consistency checks skipped.",
                )
            )
            return issues

        non_numeric = [
            entry
            for entry in mapping.entries
            if entry.value is None
            and self._raw_value_present(entry)
        ]
        # value already coerced; if column existed but parse failed we stored None
        # Track via notes? Better: keep invalid markers during parse.
        # For now, entries with value column empty are fine; invalid strings raise at parse.

        annual_vs_quarters: dict[tuple[str, int], dict[str, Any]] = {}
        for entry in mapping.entries:
            if entry.value is None or entry.fiscal_year is None:
                continue
            key = (entry.concept.lower(), entry.fiscal_year)
            bucket = annual_vs_quarters.setdefault(
                key,
                {"label": entry.concept, "annual": None, "quarters": {}},
            )
            if entry.is_annual:
                bucket["annual"] = entry.value
            elif entry.fiscal_quarter is not None:
                bucket["quarters"][entry.fiscal_quarter] = entry.value

        inconsistencies = 0
        for (_concept, year), bucket in annual_vs_quarters.items():
            annual = bucket["annual"]
            quarters: dict[int, float] = bucket["quarters"]
            if annual is None or len(quarters) < 2:
                continue
            quarter_sum = sum(quarters.values())
            # Allow 1% relative tolerance or absolute 0.01
            tolerance = max(abs(annual) * 0.01, 0.01)
            if abs(quarter_sum - annual) > tolerance:
                inconsistencies += 1
                issues.append(
                    CustomRunValidationIssue(
                        check_type="numeric_consistency",
                        status="warn",
                        message=(
                            f"Numeric inconsistency for '{bucket['label']}' FY{year}: "
                            f"sum of quarters ({quarter_sum}) vs annual ({annual})."
                        ),
                        concept=bucket["label"],
                        period=f"FY{year}",
                        details={
                            "annual_value": annual,
                            "quarter_values": quarters,
                            "quarter_sum": quarter_sum,
                        },
                    )
                )

        # Unit consistency: same concept should not mix units.
        units_by_concept: dict[str, set[str]] = defaultdict(set)
        labels: dict[str, str] = {}
        for entry in mapping.entries:
            if entry.unit:
                units_by_concept[entry.concept.lower()].add(entry.unit.lower())
                labels[entry.concept.lower()] = entry.concept
        for concept_key, units in units_by_concept.items():
            if len(units) > 1:
                inconsistencies += 1
                issues.append(
                    CustomRunValidationIssue(
                        check_type="numeric_consistency",
                        status="warn",
                        message=(
                            f"Mixed units for concept '{labels[concept_key]}': "
                            + ", ".join(sorted(units))
                        ),
                        concept=labels[concept_key],
                        details={"units": sorted(units)},
                    )
                )

        if inconsistencies == 0:
            issues.append(
                CustomRunValidationIssue(
                    check_type="numeric_consistency",
                    status="pass",
                    message="Numeric values and units are consistent where provided.",
                )
            )
        return issues

    def _check_workbook_references(
        self,
        mapping: CustomRunMapping,
        structure: WorkbookStructure,
    ) -> list[CustomRunValidationIssue]:
        sheet_names = set(structure.worksheet_names)
        missing = [
            entry
            for entry in mapping.entries
            if entry.worksheet not in sheet_names
        ]
        if missing:
            preview = ", ".join(
                sorted({f"{entry.worksheet}!{entry.cell}" for entry in missing})[:5]
            )
            extra = len({entry.worksheet for entry in missing}) 
            return [
                CustomRunValidationIssue(
                    check_type="workbook_reference",
                    status="fail",
                    message=(
                        "custom_run_filter references worksheets missing from the workbook: "
                        f"{preview}"
                        + (f" (+{extra - 1} sheets)" if extra > 1 else "")
                    ),
                    details={
                        "missing_sheets": sorted({entry.worksheet for entry in missing}),
                        "workbook_sheets": structure.worksheet_names,
                    },
                )
            ]
        return [
            CustomRunValidationIssue(
                check_type="workbook_reference",
                status="pass",
                message="All custom_run_filter worksheets exist in the uploaded workbook.",
            )
        ]

    @staticmethod
    def _raw_value_present(entry: CustomRunEntry) -> bool:
        return False

    @classmethod
    def parse_period(cls, period: str) -> dict[str, Any] | None:
        """Parse a period label into fiscal year / quarter components."""
        text = period.strip()
        if not text:
            return None

        alias = PERIOD_ALIASES.get(text.lower())
        if alias:
            return {"alias": alias, "is_annual": alias == "latest_annual"}

        match = ANNUAL_PERIOD_RE.match(text)
        if match:
            year = cls._normalize_year(match.group(1) or match.group(2))
            return {"fiscal_year": year, "is_annual": True}

        match = QUARTER_PERIOD_RE.match(text.replace(" ", ""))
        if not match:
            match = QUARTER_PERIOD_RE.match(text)
        if match:
            groups = match.groups()
            if groups[0] and groups[1]:
                quarter = int(groups[0])
                year = cls._normalize_year(groups[1])
            elif groups[2] and groups[3]:
                year = cls._normalize_year(groups[2])
                quarter = int(groups[3])
            else:
                quarter = int(groups[4])
                year = cls._normalize_year(groups[5])
            return {
                "fiscal_year": year,
                "fiscal_quarter": quarter,
                "is_annual": False,
            }

        match = YEAR_ONLY_RE.match(text)
        if match:
            return {"fiscal_year": int(match.group(1)), "is_annual": True}

        return None

    @staticmethod
    def _normalize_year(raw: str) -> int:
        year = int(raw)
        if year < 100:
            return 2000 + year
        return year

    @staticmethod
    def _parse_fiscal_date(value: str) -> date | None:
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_csv(self, file_path: Path) -> tuple[list[CustomRunEntry], set[str]]:
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CustomRunParseError("custom_run CSV is missing a header row.")
            columns = {name.strip().lower() for name in reader.fieldnames if name}
            self._assert_required_columns(columns)
            entries: list[CustomRunEntry] = []
            for index, row in enumerate(reader, start=2):
                if self._row_has_data(row):
                    entries.append(self._row_to_entry(row, row_number=index))
            return entries, columns

    def _parse_xlsx(self, file_path: Path) -> tuple[list[CustomRunEntry], set[str]]:
        workbook = load_workbook(file_path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                raise CustomRunParseError("custom_run workbook is empty.")
            headers = [str(value).strip().lower() if value is not None else "" for value in rows[0]]
            header_index = {header: index for index, header in enumerate(headers) if header}
            columns = set(header_index)
            self._assert_required_columns(columns)
            entries: list[CustomRunEntry] = []
            for row_number, row in enumerate(rows[1:], start=2):
                row_dict = {
                    header: row[index] if index < len(row) else None
                    for header, index in header_index.items()
                }
                if self._row_has_data(row_dict):
                    entries.append(self._row_to_entry(row_dict, row_number=row_number))
            return entries, columns
        finally:
            workbook.close()

    @staticmethod
    def _assert_required_columns(columns: set[str]) -> None:
        normalized = set(columns)
        if "sheet" in normalized:
            normalized.add("worksheet")
        missing = REQUIRED_COLUMNS - normalized
        if missing:
            raise CustomRunParseError(
                f"custom_run filter missing required columns: {', '.join(sorted(missing))}"
            )

    @staticmethod
    def _row_has_data(row: dict[str, object | None]) -> bool:
        return any(value is not None and str(value).strip() != "" for value in row.values())

    def _row_to_entry(self, row: dict[str, object | None], row_number: int | None = None) -> CustomRunEntry:
        normalized = {key.strip().lower(): value for key, value in row.items() if key}
        worksheet = normalized.get("worksheet", normalized.get("sheet"))
        try:
            period_raw = normalized["period"]
            period = "" if period_raw is None else str(period_raw).strip()
            return CustomRunEntry(
                workbook=str(normalized.get("workbook") or "prefilled_workbook").strip(),
                worksheet=str(worksheet).strip(),
                cell=str(normalized["cell"]).strip().upper(),
                concept=str(normalized["concept"]).strip(),
                period=period,
                xbrl_tag=self._optional_str(normalized.get("xbrl_tag")),
                unit=self._optional_str(normalized.get("unit")),
                notes=self._optional_str(normalized.get("notes")),
                ticker=self._optional_str(normalized.get("ticker")),
                fiscal_date=self._format_fiscal_date(normalized.get("fiscal_date")),
                value=self._optional_float(normalized.get("value")),
                row_number=row_number,
            )
        except (KeyError, TypeError) as exc:
            raise CustomRunParseError(f"Invalid custom_run row: missing {exc}") from exc

    @staticmethod
    def _optional_str(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _format_fiscal_date(cls, value: object | None) -> str | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_float(value: object | None) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise CustomRunParseError(f"Invalid numeric value '{value}' in custom_run_filter.") from exc
