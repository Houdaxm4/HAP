"""Workbook parsing models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CellRef(BaseModel):
    sheet: str
    cell: str


class WorkbookCell(BaseModel):
    sheet: str
    cell: str
    value: str | float | int | None = None
    is_formula: bool = False
    is_blank: bool = False


class WorkbookParseResult(BaseModel):
    workbook_filename: str
    worksheet_names: list[str] = Field(default_factory=list)
    visible_sheets: list[str] = Field(default_factory=list)
    blank_cells: list[WorkbookCell] = Field(default_factory=list)
    detected_ticker: str | None = None
    detected_company: str | None = None
