"""custom_run filter mapping models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CustomRunEntry(BaseModel):
    """
    One row from the custom_run filter file.

    Tells HAP exactly which workbook cell to populate and which financial
    concept / reporting period to source from SEC filings.
    """

    workbook: str = "prefilled_workbook"
    worksheet: str
    cell: str
    concept: str
    period: str
    xbrl_tag: str | None = None
    unit: str | None = None
    notes: str | None = None


class CustomRunMapping(BaseModel):
    """Parsed custom_run filter for an analysis."""

    source_filename: str
    entry_count: int
    entries: list[CustomRunEntry] = Field(default_factory=list)
