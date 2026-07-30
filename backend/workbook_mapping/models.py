"""Pydantic models for the Workbook Manifest (M1.5)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CellClass(str, Enum):
    WRITABLE_INPUT = "Writable Input"
    FORMULA = "Formula"
    READ_ONLY = "Read-only"
    HISTORICAL_DATA = "Historical Data"
    OUTPUT = "Output"
    HELPER = "Helper"
    NAMED_RANGE = "Named Range"
    PROTECTED = "Protected"
    EMPTY = "Empty"
    RESERVED = "Reserved"


class SheetRole(str, Enum):
    DATA = "Data"
    FORMULA = "Formula"
    HYBRID = "Hybrid"
    CONTROL = "Control"
    META = "Meta"
    HELPER = "Helper"
    OUTPUT = "Output"


class WritePolicy(str, Enum):
    WRITABLE = "Writable"
    READ_ONLY = "Read-only"
    HYBRID = "Hybrid"


class FillPriority(str, Enum):
    P0 = "P0"  # annual statement inputs — map first
    P1 = "P1"  # LQ standardized — later
    P2 = "P2"  # leave to Excel / optional
    NEVER = "Never"


class CellRecord(BaseModel):
    sheet: str
    address: str
    row: int
    column: int
    classification: CellClass
    writable: bool
    value_preview: str | None = None
    formula: str | None = None
    named_ranges: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    notes: str | None = None


class RegionSummary(BaseModel):
    """Compact description of a contiguous classified region."""

    sheet: str
    classification: CellClass
    writable: bool
    start_row: int
    end_row: int
    start_col: int
    end_col: int
    cell_count: int
    notes: str | None = None


class SheetObjectInventory(BaseModel):
    merged_cells: list[str] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    data_validations: list[dict[str, Any]] = Field(default_factory=list)
    conditional_formatting: list[dict[str, Any]] = Field(default_factory=list)
    freeze_panes: str | None = None
    hidden_rows: list[int] = Field(default_factory=list)
    hidden_columns: list[str] = Field(default_factory=list)
    protection: dict[str, Any] = Field(default_factory=dict)


class SheetScanMetrics(BaseModel):
    declared_max_row: int | None = None
    declared_max_column: int | None = None
    used_max_row: int = 0
    used_max_column: int = 0
    nonblank_cells: int = 0
    formula_cells: int = 0
    constant_cells: int = 0
    blank_in_used_range: int = 0
    formula_ratio: float = 0.0


class SheetClassification(BaseModel):
    name: str
    index: int
    state: str  # visible | hidden | veryHidden
    role: SheetRole
    write_policy: WritePolicy
    fill_priority: FillPriority
    purpose: str
    control_cells: list[str] = Field(default_factory=list)
    outbound_sheet_dependencies: dict[str, int] = Field(default_factory=dict)
    metrics: SheetScanMetrics
    objects: SheetObjectInventory
    # Dense cell records: non-blank + control + named-range targets + sampled empties
    cells: list[CellRecord] = Field(default_factory=list)
    # Region rollups for empties / large bands
    regions: list[RegionSummary] = Field(default_factory=list)
    writable_candidate_regions: list[RegionSummary] = Field(default_factory=list)
    do_not_write_notes: list[str] = Field(default_factory=list)


class NamedRangeRecord(BaseModel):
    name: str
    attr_text: str | None = None
    destinations: list[dict[str, str]] = Field(default_factory=list)
    broken: bool = False


class WorkbookProtection(BaseModel):
    workbook_locked: bool = False
    structure_locked: bool = False
    windows_locked: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)


class WorkbookStatistics(BaseModel):
    worksheets: int = 0
    used_cells_nonblank: int = 0
    writable_cells: int = 0
    formula_cells: int = 0
    read_only_cells: int = 0
    protected_cells: int = 0
    historical_data_cells: int = 0
    output_cells: int = 0
    helper_cells: int = 0
    empty_cells_in_used_ranges: int = 0
    reserved_cells: int = 0
    named_range_cells: int = 0
    merged_ranges: int = 0
    named_ranges: int = 0
    tables: int = 0
    charts: int = 0
    data_validation_rules: int = 0
    conditional_formatting_rules: int = 0
    hidden_rows: int = 0
    hidden_columns: int = 0
    classification_counts: dict[str, int] = Field(default_factory=dict)
    sheets_by_role: dict[str, int] = Field(default_factory=dict)
    sheets_by_write_policy: dict[str, int] = Field(default_factory=dict)


class SuiteSheetFingerprint(BaseModel):
    ticker: str
    sheet_names: list[str]
    roles: dict[str, str]
    write_policies: dict[str, str]
    fill_priorities: dict[str, str]


class WorkbookManifest(BaseModel):
    """Single source of truth for Industrial Template structure (M1.5+)."""

    schema_version: str = "1.0.0"
    milestone: str = "M1.5"
    template_family: str = "Industrial Template"
    template_version_filename: str | None = None
    template_version_sheet: str | None = None
    baseline_ticker: str
    source_filename: str
    source_sha256: str
    generated_at: str
    workbook_protection: WorkbookProtection
    named_ranges: list[NamedRangeRecord] = Field(default_factory=list)
    sheets: list[SheetClassification] = Field(default_factory=list)
    statistics: WorkbookStatistics
    dependency_edges: list[dict[str, Any]] = Field(default_factory=list)
    suite_fingerprints: list[SuiteSheetFingerprint] = Field(default_factory=list)
    suite_structure_identical: bool = False
    assumptions: list[str] = Field(default_factory=list)
    consumers: list[str] = Field(
        default_factory=lambda: [
            "Mapping Engine (M2)",
            "Mapping Validator",
            "Fill Engine (M3/M4)",
            "Workbook Validator",
            "Report Generator",
        ]
    )
