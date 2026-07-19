"""Canonical company financial model assembled by the ingestion layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ingestion.models.custom_run_data import CustomRunData
from models.common import utc_now_iso


class SecStatementValue(BaseModel):
    """One SEC-sourced statement fact."""

    concept: str
    period: str
    value: float
    xbrl_tag: str
    taxonomy: str
    form: str
    filed: str
    accession_number: str | None = None
    unit: str | None = None


class CompanyFinancialModel(BaseModel):
    """
    Canonical financial model consumed by AnalysisEngine.

    SEC statement facts are authoritative for financial statements.
    Custom_Run provides proprietary analytics, historical metrics, and market data.
    """

    analysis_id: str
    ticker: str
    company_name: str
    cik: str | None = None
    custom_run: CustomRunData
    sec_filings_manifest: dict[str, Any] = Field(default_factory=dict)
    sec_statement_values: list[SecStatementValue] = Field(default_factory=list)
    market_data: dict[str, float | str | None] = Field(default_factory=dict)
    proprietary_metrics: dict[str, dict[str, float | str | None]] = Field(default_factory=dict)
    historical_metrics: dict[str, dict[str, float | str | None]] = Field(default_factory=dict)
    valuation_metrics: dict[str, dict[str, float | str | None]] = Field(default_factory=dict)
    quality_metrics: dict[str, float | str | None] = Field(default_factory=dict)
    assumptions: dict[str, float | str | None] = Field(default_factory=dict)
    built_at: str = Field(default_factory=utc_now_iso)
