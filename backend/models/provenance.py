"""Cell-level provenance for every number placed in the workbook."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso

SourceType = Literal[
    "10-K",
    "10-Q",
    "SEC XBRL",
    "custom_run_filter",
    "Yahoo Finance",
    "workbook formula",
    "analyst-provided value",
    "existing_workbook_value",
    "unresolved",
]

PeriodClassification = Literal[
    "standalone_quarter",
    "year_to_date",
    "annual",
    "trailing_twelve_months",
    "unknown",
]

ConfidenceBand = Literal["high", "medium", "low"]


class CellTransformation(BaseModel):
    """Documents any transformation applied before writing a value."""

    type: str
    description: str
    input_value: Any | None = None
    output_value: Any | None = None


class CellProvenance(BaseModel):
    """
    Full explainability record for one populated or considered workbook cell.

    Every value HAP writes or proposes must have a provenance record. Cells that
    are left unchanged (formulas, existing manual inputs) are also recorded so
    no populated cell is silently modified.
    """

    # Identity
    analysis_id: str | None = None
    ticker: str | None = None
    workbook_filename: str | None = None
    cell_ref: str
    worksheet: str
    cell: str
    field_name: str | None = None
    concept: str
    period: str

    # Values
    original_workbook_value: Any | None = None
    proposed_value: Any | None = None
    value: Any | None = None  # written value (alias of proposed when filled)
    status: str = "filled"
    # filled | skipped_formula | preserved_existing | conflict | unfilled | unresolved

    # Source
    source_type: SourceType | None = None
    source_document: str | None = None
    source_url: str | None = None
    filing_type: str | None = None
    filing_year: int | None = None
    filing_date: str | None = None
    fiscal_period: str | None = None
    period_classification: PeriodClassification = "unknown"
    accession_number: str | None = None
    filing_page: str | None = None
    filing_section: str | None = None
    statement_name: str | None = None
    page: int | None = None
    xbrl_tag: str | None = None

    # Units / transforms
    original_source_value: Any | None = None
    source_unit: str | None = None
    workbook_unit: str | None = None
    transformations: list[CellTransformation] = Field(default_factory=list)

    # Confidence / explainability
    confidence: float | None = None
    confidence_band: ConfidenceBand | None = None
    reasoning: str | None = None
    failure_reason: str | None = None
    conflict_with_custom_run: bool = False
    custom_run_value: Any | None = None
    timestamp: str = Field(default_factory=utc_now_iso)

    def model_post_init(self, __context: Any) -> None:
        if self.field_name is None:
            self.field_name = self.concept
        if self.value is not None and self.proposed_value is None:
            self.proposed_value = self.value
        if self.proposed_value is not None and self.value is None and self.status == "filled":
            self.value = self.proposed_value
        if self.source_url is None and self.source_document is not None:
            self.source_url = self.source_document
        if self.confidence_band is None and self.confidence is not None:
            self.confidence_band = _band_from_score(self.confidence)


def _band_from_score(score: float) -> ConfidenceBand:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


class ProvenanceReport(BaseModel):
    """Collection of provenance records for an analysis."""

    analysis_id: str
    ticker: str
    workbook_filename: str | None = None
    entries: list[CellProvenance] = Field(default_factory=list)
    filled_count: int = 0
    blank_count: int = 0
    skipped_formula_count: int = 0
    preserved_existing_count: int = 0
    unresolved_count: int = 0
    conflict_count: int = 0
    generated_at: str = Field(default_factory=utc_now_iso)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "Filing / SEC XBRL data controls over custom_run_filter when values conflict.",
            "Formula cells are never overwritten.",
            "Populated manual-input cells are not silently replaced; conflicts are recorded.",
            "Uncertain mappings are left unresolved with low confidence.",
        ]
    )
