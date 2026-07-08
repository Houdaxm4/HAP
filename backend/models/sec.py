"""SEC EDGAR filing models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilingRecord(BaseModel):
    form: str
    filing_date: str
    accession_number: str
    primary_document: str
    fiscal_year: int | None = None
    local_path: str | None = None
    source_url: str


class SecCompanyProfile(BaseModel):
    ticker: str
    cik: str
    company_name: str


class SecFilingBundle(BaseModel):
    profile: SecCompanyProfile
    ten_k_filings: list[FilingRecord] = Field(default_factory=list)
    latest_ten_q: FilingRecord | None = None
