"""Analysis data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso
from models.pipeline import DecisionLogEntry, PipelineStatus


class CreateAnalysisRequest(BaseModel):
    """Payload for creating a new analysis."""

    company: str
    ticker: str
    analysis_type: str


class CreateAnalysisResponse(BaseModel):
    """Response returned after analysis creation."""

    analysis_id: str
    status: Literal["created"] = "created"


class UploadedFileMetadata(BaseModel):
    """Metadata for a single uploaded workbook file."""

    filename: str
    stored_filename: str
    size_bytes: int
    uploaded_at: str


class AnalysisFiles(BaseModel):
    """Uploaded file references for an analysis."""

    prefilled_workbook: UploadedFileMetadata | None = None
    previous_workbook: UploadedFileMetadata | None = None
    custom_run_filter: UploadedFileMetadata | None = None


class Analysis(BaseModel):
    """Full analysis record persisted as JSON."""

    analysis_id: str
    company: str
    ticker: str
    analysis_type: str
    status: str = "created"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    files: AnalysisFiles = Field(default_factory=AnalysisFiles)
    pipeline: PipelineStatus = Field(default_factory=PipelineStatus)
    decision_log: list[DecisionLogEntry] = Field(default_factory=list)
    cik: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the analysis to a plain dictionary."""
        data = self.model_dump()
        data["pipeline"] = self.pipeline.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Analysis:
        """Deserialize an analysis from a plain dictionary."""
        normalized = dict(data)
        if "pipeline" in normalized:
            normalized["pipeline"] = PipelineStatus.from_dict(normalized["pipeline"])
        return cls.model_validate(normalized)

    @property
    def is_pipeline_complete(self) -> bool:
        """True only when required pipeline and analysis-engine outputs exist."""
        outputs = self.pipeline.outputs
        return (
            self.pipeline.state == "complete"
            and outputs.completed_workbook is not None
            and outputs.provenance_report is not None
            and outputs.validation_report is not None
            and outputs.company_financial_model is not None
            and outputs.analysis_engine_result is not None
        )
