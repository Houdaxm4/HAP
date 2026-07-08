"""Pipeline status and stage models for HAP analysis workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso


class PipelineStage(str, Enum):
    """Ordered stages in the first production milestone."""

    UPLOAD = "upload"
    PARSE_WORKBOOK = "parse_workbook"
    PARSE_CUSTOM_RUN = "parse_custom_run"
    FETCH_SEC_FILINGS = "fetch_sec_filings"
    FILL_WORKBOOK = "fill_workbook"
    VALIDATE_WORKBOOK = "validate_workbook"
    COMPLETE = "complete"
    FAILED = "failed"


PIPELINE_STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.UPLOAD,
    PipelineStage.PARSE_WORKBOOK,
    PipelineStage.PARSE_CUSTOM_RUN,
    PipelineStage.FETCH_SEC_FILINGS,
    PipelineStage.FILL_WORKBOOK,
    PipelineStage.VALIDATE_WORKBOOK,
    PipelineStage.COMPLETE,
]


class DecisionLogEntry(BaseModel):
    """Agent execution log entry persisted on the analysis."""

    agent: str
    action: str
    detail: str
    timestamp: str = Field(default_factory=utc_now_iso)
    confidence: float | None = None
    citations: list[str] = Field(default_factory=list)


class PipelineOutputs(BaseModel):
    """Artifact paths relative to the analysis output directory."""

    completed_workbook: str | None = None
    provenance_report: str | None = None
    discrepancy_report: str | None = None
    validation_report: str | None = None
    sec_filings_manifest: str | None = None
    workbook_structure: str | None = None
    custom_run_mapping: str | None = None


class PipelineStatus(BaseModel):
    """Runtime pipeline state tracked on each analysis."""

    state: Literal["idle", "processing", "complete", "failed"] = "idle"
    current_stage: PipelineStage | None = None
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    progress_pct: int = 0
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    outputs: PipelineOutputs = Field(default_factory=PipelineOutputs)

    def to_dict(self) -> dict[str, Any]:
        """Serialize pipeline status to a JSON-friendly dict."""
        data = self.model_dump()
        if self.current_stage is not None:
            data["current_stage"] = self.current_stage.value
        data["stages_completed"] = [stage.value for stage in self.stages_completed]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PipelineStatus:
        """Deserialize pipeline status, tolerating legacy analyses without pipeline data."""
        if not data:
            return cls()
        normalized = dict(data)
        if normalized.get("current_stage"):
            normalized["current_stage"] = PipelineStage(normalized["current_stage"])
        if normalized.get("stages_completed"):
            normalized["stages_completed"] = [
                PipelineStage(stage) for stage in normalized["stages_completed"]
            ]
        return cls.model_validate(normalized)
