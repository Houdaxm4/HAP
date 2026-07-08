"""Phase 1 pipeline result models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.custom_run_filter import CustomRunFilterParseResult
from models.sec import FilingRecord, SecCompanyProfile
from models.workbook_parse import WorkbookParseResult


class FillRecord(BaseModel):
    sheet: str
    cell: str
    concept: str
    period: str
    value: float | int | str
    source: str
    xbrl_tag: str | None = None


class Phase1Result(BaseModel):
    resolved_ticker: str
    company_profile: SecCompanyProfile
    workbook_parse: WorkbookParseResult
    filter_parse: CustomRunFilterParseResult
    filings: list[FilingRecord] = Field(default_factory=list)
    fills_applied: list[FillRecord] = Field(default_factory=list)
    completed_workbook_path: str | None = None
    validation_passed: bool = False
    validation_message: str = ""
