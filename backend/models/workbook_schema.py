"""Workbook structure models produced by the parse_workbook stage."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkbookSummary(BaseModel):
    """Summary statistics for a prefilled workbook."""

    workbook_filename: str
    worksheet_names: list[str]
    sheet_count: int
    visible_sheets: list[str]
    hidden_sheets: list[str]
    formula_count: int
    editable_cell_count: int = 0
    non_empty_cell_count: int
    named_range_count: int = 0


class CellFormatting(BaseModel):
    """
    Captured cell formatting.

    Stored so downstream stages can preserve appearance without modifying
    the source workbook. Writing values must not clear these styles.
    """

    number_format: str | None = None
    font_name: str | None = None
    font_size: float | None = None
    font_bold: bool | None = None
    font_italic: bool | None = None
    font_color: str | None = None
    fill_pattern: str | None = None
    fill_color: str | None = None
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    wrap_text: bool | None = None
    locked: bool | None = None


class CellInfo(BaseModel):
    """Metadata for a single workbook cell."""

    address: str
    row: int | None = None
    column: int | None = None
    value: Any = None
    data_type: Literal["formula", "value", "blank"] = "blank"
    formula: str | None = None
    is_formula: bool = False
    is_editable: bool = True
    formatting: CellFormatting | None = None


class NamedRangeInfo(BaseModel):
    """Named range defined in the workbook."""

    name: str
    destinations: list[str] = Field(default_factory=list)
    attr_text: str | None = None


class WorksheetInfo(BaseModel):
    """Structural summary for one worksheet."""

    name: str
    visibility: Literal["visible", "hidden", "veryHidden"] = "visible"
    index: int = 0
    dimensions: str | None = None
    max_row: int | None = None
    max_column: int | None = None
    formula_count: int = 0
    editable_cell_count: int = 0
    value_count: int = 0
    blank_count: int = 0
    non_empty_cell_count: int = 0
    formula_cells: list[CellInfo] = Field(default_factory=list)
    editable_cells: list[CellInfo] = Field(default_factory=list)
    cells: list[CellInfo] = Field(default_factory=list)


class WorkbookMetadata(BaseModel):
    """Document-level workbook properties (read-only)."""

    title: str | None = None
    subject: str | None = None
    creator: str | None = None
    description: str | None = None
    keywords: str | None = None
    category: str | None = None
    last_modified_by: str | None = None
    created: str | None = None
    modified: str | None = None
    content_status: str | None = None
    revision: str | None = None
    excel_base_date: str | None = None
    sheet_count: int = 0
    defined_name_count: int = 0


class WorkbookStructure(BaseModel):
    """Full structural JSON representation of a prefilled workbook."""

    workbook_filename: str
    metadata: WorkbookMetadata = Field(default_factory=WorkbookMetadata)
    worksheet_names: list[str] = Field(default_factory=list)
    visible_sheets: list[str] = Field(default_factory=list)
    hidden_sheets: list[str] = Field(default_factory=list)
    named_ranges: list[NamedRangeInfo] = Field(default_factory=list)
    worksheets: list[WorksheetInfo] = Field(default_factory=list)
    formula_count: int = 0
    editable_cell_count: int = 0
    non_empty_cell_count: int = 0
    # Convenience flat indexes for frontend consumers.
    formula_cells: list[str] = Field(default_factory=list)
    editable_cells: list[str] = Field(default_factory=list)
