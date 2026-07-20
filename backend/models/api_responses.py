"""API response DTOs — presentation serialization of persisted analysis + engine fields.

No analytical calculations. Fields are either analysis metadata or projections of
persisted AnalysisEngineResult properties (never invented aliases).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.analysis import Analysis, AnalysisFiles
from models.pipeline import DecisionLogEntry, PipelineOutputs, PipelineStatus


class AnalysisSummaryResponse(BaseModel):
    """Dashboard / list row — metadata plus engine analytical fields when present."""

    analysis_id: str
    company: str
    ticker: str
    analysis_type: str
    status: str
    pipeline_state: Literal["idle", "processing", "complete", "failed"]
    progress_pct: int = Field(ge=0, le=100)
    current_stage: str | None = None
    pipeline_error: str | None = None
    is_complete: bool
    created_at: str
    updated_at: str
    recommendation: str | None = None
    recommendation_label: str | None = None
    business_quality_score: float | None = None
    investment_attractiveness_score: float | None = None


class AnalysisDetailResponse(AnalysisSummaryResponse):
    """Detail page metadata — artifacts are fetched separately via outputs API."""

    files: AnalysisFiles = Field(default_factory=AnalysisFiles)
    pipeline: PipelineStatus = Field(default_factory=PipelineStatus)
    decision_log: list[DecisionLogEntry] = Field(default_factory=list)
    cik: str | None = None
    outputs: PipelineOutputs = Field(default_factory=PipelineOutputs)
    has_engine_result: bool = False
    has_validation_report: bool = False


def build_summary_response(
    analysis: Analysis,
    engine_result: dict[str, Any] | None = None,
) -> AnalysisSummaryResponse:
    """Serialize analysis metadata and optional persisted engine analytical fields."""
    recommendation = None
    recommendation_label = None
    business_quality_score = None
    investment_attractiveness_score = None

    if engine_result is not None:
        rec = engine_result.get("recommendation") or {}
        bq = engine_result.get("business_quality") or {}
        ia = engine_result.get("investment_attractiveness") or {}
        recommendation = rec.get("recommendation")
        recommendation_label = rec.get("recommendation_label")
        business_quality_score = bq.get("score")
        investment_attractiveness_score = ia.get("score")

    current_stage = (
        analysis.pipeline.current_stage.value
        if analysis.pipeline.current_stage is not None
        else None
    )
    return AnalysisSummaryResponse(
        analysis_id=analysis.analysis_id,
        company=analysis.company,
        ticker=analysis.ticker,
        analysis_type=analysis.analysis_type,
        status=analysis.status,
        pipeline_state=analysis.pipeline.state,
        progress_pct=analysis.pipeline.progress_pct,
        current_stage=current_stage,
        pipeline_error=analysis.pipeline.error,
        is_complete=analysis.is_pipeline_complete,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        recommendation=recommendation,
        recommendation_label=recommendation_label,
        business_quality_score=business_quality_score,
        investment_attractiveness_score=investment_attractiveness_score,
    )


def build_detail_response(
    analysis: Analysis,
    engine_result: dict[str, Any] | None = None,
) -> AnalysisDetailResponse:
    """Serialize detail metadata. Engine/validation JSON remain separate artifacts."""
    summary = build_summary_response(analysis, engine_result)
    outputs = analysis.pipeline.outputs
    return AnalysisDetailResponse(
        **summary.model_dump(),
        files=analysis.files,
        pipeline=analysis.pipeline,
        decision_log=list(analysis.decision_log),
        cik=analysis.cik,
        outputs=outputs,
        has_engine_result=outputs.analysis_engine_result is not None,
        has_validation_report=outputs.validation_report is not None,
    )


def load_engine_result_dict(output_service: Any, analysis: Analysis) -> dict[str, Any] | None:
    """Load persisted analysis_engine_result.json if the pipeline recorded it."""
    if analysis.pipeline.outputs.analysis_engine_result is None:
        return None
    path = output_service.artifact_path(analysis.analysis_id, "analysis_engine_result.json")
    if not path.exists():
        return None
    return output_service.read_json(analysis.analysis_id, "analysis_engine_result.json")
