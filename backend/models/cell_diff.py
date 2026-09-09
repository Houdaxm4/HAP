"""Cell-diff report for Mode A Excel fill (M4)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CellDiffEntry(BaseModel):
    """One WRITE attempt or runtime skip/block against the Industrial Template."""

    sheet: str
    cell: str
    cell_ref: str
    original_value: Any | None = None
    new_value: Any | None = None
    metric: str | None = None
    period: str | None = None
    source: str | None = None
    confidence: float | None = None
    transformation: str | None = None
    write_decision: str
    reason: str
    mapping_id: str | None = None
    intent_id: str | None = None
    changed: bool = False


class CellDiffReport(BaseModel):
    """Machine-readable M4 cell-diff artifact (`cell_diff_report.json`)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    milestone: str = "M4"
    source_workbook: str
    completed_workbook: str
    entries: list[CellDiffEntry] = Field(default_factory=list)
    written_count: int = 0
    runtime_skip_count: int = 0
    runtime_block_count: int = 0
    m3_skip_count: int = 0
    m3_block_count: int = 0
    changed_count: int = 0
