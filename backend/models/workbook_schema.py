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
    non_empty_cell_count: int


class CellInfo(BaseModel):
    """Metadata for a single workbook cell."""

    address: str
    value: Any = None
    data_type: Literal["formula", "value", "blank"] = "blank"
    formula: str | None = None
    is_formula: bool = False


class NamedRangeInfo(BaseModel):
    """Named range defined in the workbook."""

    name: str
    destinations: list[str] = Field(default_factory=list)


class WorksheetInfo(BaseModel):
    """Structural summary for one worksheet."""

    name: str
    visibility: Literal["visible", "hidden", "veryHidden"] = "visible"
    formula_count: int = 0
    value_count: int = 0
    blank_count: int = 0
    non_empty_cell_count: int = 0
    cells: list[CellInfo] = Field(default_factory=list)


class WorkbookStructure(BaseModel):
    """Full structural parse of a prefilled workbook."""

    workbook_filename: str
    worksheet_names: list[str] = Field(default_factory=list)
    visible_sheets: list[str] = Field(default_factory=list)
    hidden_sheets: list[str] = Field(default_factory=list)
    named_ranges: list[NamedRangeInfo] = Field(default_factory=list)
    worksheets: list[WorksheetInfo] = Field(default_factory=list)
    formula_count: int = 0
    non_empty_cell_count: int = 0
