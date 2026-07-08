"""Cell-level provenance for every number placed in the workbook."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CellTransformation(BaseModel):
    """Documents any transformation applied before writing a value."""

    type: str
    description: str
    input_value: Any | None = None
    output_value: Any | None = None


class CellProvenance(BaseModel):
    """
    Full explainability record for one populated workbook cell.

    Designed to power the side-panel UX: value, source filing, page, XBRL tag,
    transformations, and reasoning for the mapping.
    """

    cell_ref: str
    worksheet: str
    cell: str
    concept: str
    period: str
    value: Any | None = None
    status: str = "filled"
    source_document: str | None = None
    filing_type: str | None = None
    filing_year: int | None = None
    filing_date: str | None = None
    accession_number: str | None = None
    page: int | None = None
    xbrl_tag: str | None = None
    confidence: float | None = None
    transformations: list[CellTransformation] = Field(default_factory=list)
    reasoning: str | None = None
    failure_reason: str | None = None


class ProvenanceReport(BaseModel):
    """Collection of provenance records for an analysis."""

    analysis_id: str
    ticker: str
    entries: list[CellProvenance] = Field(default_factory=list)
    filled_count: int = 0
    blank_count: int = 0
    skipped_formula_count: int = 0
