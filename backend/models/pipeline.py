"""Pipeline stage and output models for the HAP analysis workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineStage(str, Enum):
    """Ordered stages in the real HAP analysis workflow."""

    CREATED = "created"
    TEMPLATE_UPLOADED = "template_uploaded"
    FILING_COLLECTION = "filing_collection"
    WORKBOOK_COMPLETION = "workbook_completion"
    WORKBOOK_VALIDATION = "workbook_validation"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    MARKET_VALUATION_ANALYSIS = "market_valuation_analysis"
    FINAL_RECOMMENDATION = "final_recommendation"
    OUTPUTS_READY = "outputs_ready"
    FAILED = "failed"


PIPELINE_STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.CREATED,
    PipelineStage.TEMPLATE_UPLOADED,
    PipelineStage.FILING_COLLECTION,
    PipelineStage.WORKBOOK_COMPLETION,
    PipelineStage.WORKBOOK_VALIDATION,
    PipelineStage.FUNDAMENTAL_ANALYSIS,
    PipelineStage.MARKET_VALUATION_ANALYSIS,
    PipelineStage.FINAL_RECOMMENDATION,
    PipelineStage.OUTPUTS_READY,
]


StageStatus = Literal[
    "pending",
    "in_progress",
    "not_implemented",
    "complete",
    "failed",
]

OutputStatus = Literal["pending", "ready", "unavailable"]


class PipelineOutputs(BaseModel):
    """Final deliverables produced by the analysis pipeline."""

    workbook: OutputStatus = "pending"
    investment_memo: OutputStatus = "pending"
    source_citations: OutputStatus = "pending"
    discrepancy_report: OutputStatus = "pending"
    verification_report: OutputStatus = "pending"


class PipelineState(BaseModel):
    """Current pipeline position for an analysis."""

    current_stage: PipelineStage = PipelineStage.CREATED
    stage_status: StageStatus = "pending"
    message: str = "Analysis created. Upload template and custom_run filter to begin."
    outputs: PipelineOutputs = Field(default_factory=PipelineOutputs)
    updated_at: str = Field(default_factory=utc_now_iso)


class PipelineStepResponse(BaseModel):
    """Response returned by each pipeline step endpoint."""

    analysis_id: str
    stage: PipelineStage
    stage_status: StageStatus
    message: str
    outputs: PipelineOutputs
    implementation_status: Literal["not_implemented", "ready"] = "not_implemented"


def default_pipeline_state() -> PipelineState:
    """Return the initial pipeline state for a newly created analysis."""
    return PipelineState()


def pipeline_message_for_stage(stage: PipelineStage) -> str:
    """Human-readable placeholder message for a pipeline stage."""
    messages = {
        PipelineStage.CREATED: (
            "Analysis created. Upload the prefilled Excel template and custom_run filter."
        ),
        PipelineStage.TEMPLATE_UPLOADED: (
            "Template and custom_run filter uploaded. Awaiting SEC filing collection."
        ),
        PipelineStage.FILING_COLLECTION: (
            "Collect last 10 years of 10-K filings, latest 10-Q, earnings release, "
            "investor presentation, and market data."
        ),
        PipelineStage.WORKBOOK_COMPLETION: (
            "Use filings and market data to validate and complete blanks in the uploaded template."
        ),
        PipelineStage.WORKBOOK_VALIDATION: (
            "Verify completed workbook values against SEC source documents."
        ),
        PipelineStage.FUNDAMENTAL_ANALYSIS: (
            "Run fundamental analysis after workbook validation succeeds."
        ),
        PipelineStage.MARKET_VALUATION_ANALYSIS: (
            "Run market, competitive, valuation, and value-creation analysis."
        ),
        PipelineStage.FINAL_RECOMMENDATION: (
            "Synthesize investment thesis, risks, and recommendation at current price."
        ),
        PipelineStage.OUTPUTS_READY: (
            "Pipeline outputs are ready: workbook, memo, citations, and reports."
        ),
        PipelineStage.FAILED: "The analysis pipeline failed.",
    }
    return messages.get(stage, "Pipeline stage in progress.")
