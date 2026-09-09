"""Post-completion validation of prefilled workbook values against SEC."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PrefillValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    DISCREPANCY = "DISCREPANCY"
    SKIPPED = "SKIPPED"


class PrefillValidationEntry(BaseModel):
    """Compare an already-present workbook value to the SEC/CFM candidate."""

    intent_id: str | None = None
    mapping_id: str | None = None
    sheet: str
    cell: str
    cell_ref: str
    metric: str
    period: str
    status: PrefillValidationStatus
    workbook_value: Any | None = None
    sec_value: Any | None = None
    difference: float | None = None
    difference_pct: float | None = None
    source_evidence: str | None = None
    reason: str
    correction_applied: bool = False


class PrefillValidationReport(BaseModel):
    """Statement prefilled-value validation (feeds validation_report / discrepancy)."""

    analysis_id: str
    ticker: str
    schema_version: str = "1.0.0"
    entries: list[PrefillValidationEntry] = Field(default_factory=list)
    validated_count: int = 0
    discrepancy_count: int = 0
    skipped_count: int = 0
    summary: str = ""
