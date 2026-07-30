"""Pydantic schema for CFM ↔ Workbook mapping specification (M2)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CellDisposition(str, Enum):
    MAPPED = "Mapped"
    INTENTIONALLY_EMPTY = "Intentionally Empty"
    UNSUPPORTED = "Unsupported"
    FUTURE_FEATURE = "Future Feature"


class TimeDimension(str, Enum):
    ANNUAL_FY = "annual_fy"
    CONTROL = "control"
    POINT = "point"
    NONE = "none"


class MappingEntry(BaseModel):
    """One explicit, reproducible CFM → workbook binding."""

    mapping_id: str
    cfm_path: str
    metric_name: str
    sheet: str
    row: int
    columns: list[str]
    expected_label: str | None = None
    label_cell: str | None = None
    time_dimension: TimeDimension = TimeDimension.ANNUAL_FY
    unit: str = "USD_millions"
    data_type: str = "float"
    transformation: str | None = None
    validation_rules: list[str] = Field(default_factory=list)
    write_priority: int = 100
    fill_priority: str = "P0"
    notes: str | None = None


class PeriodColumnMap(BaseModel):
    sheet: str
    header_row: int
    date_row: int | None = None
    columns: dict[str, str]  # "C" -> "FY2016" (canonical FY token)


class WritableCellDisposition(BaseModel):
    sheet: str
    address: str
    row: int
    column: int
    disposition: CellDisposition
    reason: str
    mapping_id: str | None = None


class UnmappedCfmMetric(BaseModel):
    cfm_path: str
    reason: str
    suggested_action: str | None = None


class CoverageStats(BaseModel):
    total_cfm_metrics: int
    mapped_cfm_metrics: int
    unmapped_cfm_metrics: int
    cfm_coverage_pct: float
    total_writable_workbook_cells: int
    mapped_writable_cells: int
    intentionally_empty_writable_cells: int
    unsupported_writable_cells: int
    future_feature_writable_cells: int
    unexplained_writable_cells: int
    writable_coverage_explained_pct: float


class MappingSpecification(BaseModel):
    schema_version: str = "1.0.0"
    milestone: str = "M2"
    template_family: str = "Industrial Template"
    manifest_schema_version: str
    manifest_source: str
    baseline_ticker: str
    generated_at: str
    period_column_maps: list[PeriodColumnMap]
    mappings: list[MappingEntry]
    writable_dispositions: list[WritableCellDisposition]
    unmapped_cfm_metrics: list[UnmappedCfmMetric]
    coverage: CoverageStats
    assumptions: list[str] = Field(default_factory=list)
    consumers: list[str] = Field(
        default_factory=lambda: [
            "Mapping Engine (M3)",
            "Mapping Validator",
            "Fill Engine (M4)",
        ]
    )
