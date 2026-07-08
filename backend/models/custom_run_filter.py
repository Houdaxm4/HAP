"""custom_run_filter parsing models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilterMapping(BaseModel):
    sheet: str
    cell: str
    concept: str
    period: str = "latest_annual"
    source: str = "sec_xbrl"


class CustomRunFilterParseResult(BaseModel):
    filename: str
    mappings: list[FilterMapping] = Field(default_factory=list)
    ticker_override: str | None = None
    company_override: str | None = None
