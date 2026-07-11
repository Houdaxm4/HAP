"""Filing collection models for SEC EDGAR downloads (no extraction)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso


class CollectFilingsRequest(BaseModel):
    """Request payload to collect filings for a ticker."""

    ticker: str
    historical_years: int = Field(default=10, ge=1, le=30)
    download_documents: bool = True


class FilingDocumentMeta(BaseModel):
    """Metadata for one SEC filing and its locally cached documents."""

    accession_number: str
    form: str
    base_form: Literal["10-K", "10-Q"]
    is_amendment: bool = False
    filing_date: str
    report_date: str | None = None
    primary_document: str | None = None
    primary_document_url: str | None = None
    index_url: str | None = None
    html_url: str | None = None
    html_path: str | None = None
    xbrl_url: str | None = None
    xbrl_path: str | None = None
    fiscal_year: int | None = None
    selected_role: Literal["latest_10k", "latest_10q", "historical_10k", "superseded"] | None = None


class FilingCollectionResult(BaseModel):
    """Result of a filing collection run for one ticker."""

    collection_id: str
    ticker: str
    cik: str
    company_name: str | None = None
    status: Literal["completed", "failed", "partial"] = "completed"
    latest_10k: FilingDocumentMeta | None = None
    latest_10q: FilingDocumentMeta | None = None
    historical_10ks: list[FilingDocumentMeta] = Field(default_factory=list)
    filings: list[FilingDocumentMeta] = Field(default_factory=list)
    cache_dir: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    error: str | None = None
    message: str = "Filings collected. No extraction performed."

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
