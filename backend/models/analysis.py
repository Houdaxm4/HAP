"""Analysis data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from models.pipeline import PipelineState, default_pipeline_state


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


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
    pipeline: PipelineState = Field(default_factory=default_pipeline_state)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the analysis to a plain dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Analysis:
        """Deserialize an analysis from a plain dictionary."""
        return cls.model_validate(data)
