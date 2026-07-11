"""Pipeline status and stage models for HAP analysis workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso


class PipelineStage(str, Enum):
    """Ordered stages for infrastructure + trusted financial model milestones."""

    WORKBOOK_UPLOADED = "workbook_uploaded"
    WORKBOOK_PARSED = "workbook_parsed"
    CUSTOM_RUN_FILTER_UPLOADED = "custom_run_filter_uploaded"
    CUSTOM_RUN_FILTER_VALIDATED = "custom_run_filter_validated"
    WAITING_FOR_FILING_COLLECTION = "waiting_for_filing_collection"
    # Trusted financial model stages (phase 2)
    FILINGS_FETCHED = "filings_fetched"
    PROVENANCE_RECORDED = "provenance_recorded"
    WORKBOOK_VALIDATED = "workbook_validated"
    VALIDATION_REPORT_GENERATED = "validation_report_generated"
    PROVENANCE_REPORT_GENERATED = "provenance_report_generated"
    COMPLETE = "complete"
    FAILED = "failed"


PIPELINE_STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.WORKBOOK_UPLOADED,
    PipelineStage.WORKBOOK_PARSED,
    PipelineStage.CUSTOM_RUN_FILTER_UPLOADED,
    PipelineStage.CUSTOM_RUN_FILTER_VALIDATED,
    PipelineStage.WAITING_FOR_FILING_COLLECTION,
    PipelineStage.FILINGS_FETCHED,
    PipelineStage.PROVENANCE_RECORDED,
    PipelineStage.WORKBOOK_VALIDATED,
    PipelineStage.VALIDATION_REPORT_GENERATED,
    PipelineStage.PROVENANCE_REPORT_GENERATED,
    PipelineStage.COMPLETE,
]

PIPELINE_STAGE_LABELS: dict[PipelineStage, str] = {
    PipelineStage.WORKBOOK_UPLOADED: "Workbook uploaded",
    PipelineStage.WORKBOOK_PARSED: "Workbook parsed",
    PipelineStage.CUSTOM_RUN_FILTER_UPLOADED: "custom_run_filter uploaded",
    PipelineStage.CUSTOM_RUN_FILTER_VALIDATED: "custom_run_filter validated",
    PipelineStage.WAITING_FOR_FILING_COLLECTION: "Waiting for filing collection",
    PipelineStage.FILINGS_FETCHED: "Filings fetched",
    PipelineStage.PROVENANCE_RECORDED: "Provenance recorded",
    PipelineStage.WORKBOOK_VALIDATED: "Workbook validated",
    PipelineStage.VALIDATION_REPORT_GENERATED: "Validation report generated",
    PipelineStage.PROVENANCE_REPORT_GENERATED: "Provenance report generated",
    PipelineStage.COMPLETE: "Complete",
    PipelineStage.FAILED: "Failed",
}


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
    company_facts: str | None = None
    workbook_structure: str | None = None
    custom_run_mapping: str | None = None
    custom_run_validation_report: str | None = None
    filing_collection: str | None = None
    financial_statements: str | None = None


class PipelineStatus(BaseModel):
    """Runtime pipeline state tracked on each analysis."""

    state: Literal["idle", "processing", "waiting", "complete", "failed"] = "idle"
    current_stage: PipelineStage | None = None
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    progress_pct: int = 0
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    outputs: PipelineOutputs = Field(default_factory=PipelineOutputs)
    # Trusted-model validation summary (populated after validate stage)
    validation_status: Literal["passed", "passed_with_warnings", "failed"] | None = None
    critical_issue_count: int = 0
    warning_issue_count: int = 0
    informational_issue_count: int = 0

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
            try:
                normalized["current_stage"] = PipelineStage(normalized["current_stage"])
            except ValueError:
                # Legacy stage names from earlier milestones — treat as unknown/idle.
                normalized["current_stage"] = None
        if normalized.get("stages_completed"):
            stages: list[PipelineStage] = []
            for stage in normalized["stages_completed"]:
                try:
                    stages.append(PipelineStage(stage))
                except ValueError:
                    continue
            normalized["stages_completed"] = stages
        # Map legacy "complete" without waiting stage to waiting when appropriate.
        if normalized.get("state") == "complete" and not normalized.get("current_stage"):
            normalized["state"] = "waiting"
        return cls.model_validate(normalized)
