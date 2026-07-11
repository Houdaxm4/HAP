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
    filing_collection_id: str | None = None
    financial_statements_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the analysis to a plain dictionary."""
        data = self.model_dump()
        data["pipeline"] = self.pipeline.to_dict()
        data["is_pipeline_complete"] = self.is_pipeline_complete
        data["is_trusted_model_complete"] = self.is_trusted_model_complete
        data["artifacts_available"] = self.artifacts_available
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Analysis:
        """Deserialize an analysis from a plain dictionary."""
        normalized = dict(data)
        # Drop computed fields if present in stored JSON.
        normalized.pop("is_pipeline_complete", None)
        normalized.pop("is_trusted_model_complete", None)
        normalized.pop("artifacts_available", None)
        if "pipeline" in normalized:
            normalized["pipeline"] = PipelineStatus.from_dict(normalized["pipeline"])
        return cls.model_validate(normalized)

    @property
    def is_pipeline_complete(self) -> bool:
        """
        True when the infrastructure pipeline has finished and is waiting
        for filing collection / trusted-model continuation.
        """
        from models.pipeline import PipelineStage

        return (
            self.pipeline.state in {"waiting", "complete"}
            and PipelineStage.WAITING_FOR_FILING_COLLECTION in self.pipeline.stages_completed
            and self.pipeline.outputs.workbook_structure is not None
            and self.pipeline.outputs.custom_run_mapping is not None
            and self.pipeline.outputs.custom_run_validation_report is not None
        )

    @property
    def is_trusted_model_complete(self) -> bool:
        """
        True when the trusted financial model milestone is done:

        - completed workbook artifact exists
        - provenance report exists
        - validation report exists
        - no critical validation errors
        """
        from models.pipeline import PipelineStage

        outputs = self.pipeline.outputs
        return (
            self.pipeline.state == "complete"
            and self.pipeline.current_stage == PipelineStage.COMPLETE
            and outputs.completed_workbook is not None
            and outputs.provenance_report is not None
            and outputs.validation_report is not None
            and self.pipeline.validation_status in {"passed", "passed_with_warnings"}
            and self.pipeline.critical_issue_count == 0
        )

    @property
    def artifacts_available(self) -> dict[str, bool]:
        """Artifact availability flags for API / frontend consumers."""
        outputs = self.pipeline.outputs
        return {
            "workbook_structure": outputs.workbook_structure is not None,
            "custom_run_mapping": outputs.custom_run_mapping is not None,
            "custom_run_validation_report": outputs.custom_run_validation_report is not None,
            "sec_filings_manifest": outputs.sec_filings_manifest is not None,
            "completed_workbook": outputs.completed_workbook is not None,
            "provenance_report": outputs.provenance_report is not None,
            "validation_report": outputs.validation_report is not None,
            "discrepancy_report": outputs.discrepancy_report is not None,
            "financial_statements": outputs.financial_statements is not None,
        }
