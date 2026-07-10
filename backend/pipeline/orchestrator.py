"""HAP pipeline orchestrator for the infrastructure milestone (pre-SEC)."""

from __future__ import annotations

from models.analysis import Analysis
from models.common import utc_now_iso
from models.pipeline import (
    PIPELINE_STAGE_LABELS,
    DecisionLogEntry,
    PipelineStage,
    PipelineStatus,
)
from pipeline.stages.parse_workbook import ParseWorkbookStage
from pipeline.stages.validate_custom_run import ValidateCustomRunStage
from services.analysis_service import AnalysisService
from services.custom_run_service import CustomRunParseError
from services.file_service import FileService
from services.output_service import OutputService
from services.workbook_service import WorkbookParseError


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""


class PipelineOrchestrator:
    """
    Run the infrastructure workflow:

    Workbook uploaded → Workbook parsed → custom_run_filter uploaded →
    custom_run_filter validated → Waiting for filing collection

    SEC downloading and AI extraction are intentionally not implemented yet.
    """

    STAGE_PROGRESS: dict[PipelineStage, int] = {
        PipelineStage.WORKBOOK_UPLOADED: 20,
        PipelineStage.WORKBOOK_PARSED: 40,
        PipelineStage.CUSTOM_RUN_FILTER_UPLOADED: 60,
        PipelineStage.CUSTOM_RUN_FILTER_VALIDATED: 80,
        PipelineStage.WAITING_FOR_FILING_COLLECTION: 100,
    }

    def __init__(
        self,
        analysis_service: AnalysisService | None = None,
        file_service: FileService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.analysis_service = analysis_service or AnalysisService()
        self.file_service = file_service or FileService()
        self.output_service = output_service or OutputService()
        self.parse_workbook_stage = ParseWorkbookStage(output_service=self.output_service)
        self.validate_custom_run_stage = ValidateCustomRunStage(
            output_service=self.output_service
        )

    def run(self, analysis_id: str) -> Analysis:
        """Execute infrastructure pipeline stages sequentially."""
        analysis = self.analysis_service.get(analysis_id)
        self._assert_ready_for_pipeline(analysis)

        analysis.pipeline = PipelineStatus(
            state="processing",
            current_stage=PipelineStage.WORKBOOK_UPLOADED,
            progress_pct=5,
            started_at=utc_now_iso(),
        )
        analysis.status = "processing"
        analysis.decision_log = []
        self.analysis_service.save(analysis)

        try:
            workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
            custom_run_path = self.file_service.get_custom_run_filter_path(analysis)

            # Stage 1 — Workbook uploaded (files already stored on disk)
            self._complete_stage(
                analysis,
                PipelineStage.WORKBOOK_UPLOADED,
                DecisionLogEntry(
                    agent="Document Collection Agent",
                    action="workbook_uploaded",
                    detail=(
                        f"Stored prefilled workbook "
                        f"'{analysis.files.prefilled_workbook.filename}'."  # type: ignore[union-attr]
                    ),
                    confidence=1.0,
                ),
            )

            # Stage 2 — Workbook parsed
            analysis.pipeline.current_stage = PipelineStage.WORKBOOK_PARSED
            analysis.pipeline.progress_pct = 30
            self.analysis_service.save(analysis)
            structure, structure_path, log = self.parse_workbook_stage.run(
                analysis, workbook_path
            )
            self._complete_stage(
                analysis,
                PipelineStage.WORKBOOK_PARSED,
                log,
                workbook_structure=structure_path,
            )

            # Stage 3 — custom_run_filter uploaded
            self._complete_stage(
                analysis,
                PipelineStage.CUSTOM_RUN_FILTER_UPLOADED,
                DecisionLogEntry(
                    agent="Document Collection Agent",
                    action="custom_run_filter_uploaded",
                    detail=(
                        f"Stored custom_run_filter "
                        f"'{analysis.files.custom_run_filter.filename}'."  # type: ignore[union-attr]
                    ),
                    confidence=1.0,
                ),
            )

            # Stage 4 — custom_run_filter validated
            analysis.pipeline.current_stage = PipelineStage.CUSTOM_RUN_FILTER_VALIDATED
            analysis.pipeline.progress_pct = 70
            self.analysis_service.save(analysis)
            _, mapping_path, log = self.validate_custom_run_stage.run(
                analysis,
                custom_run_path,
                structure,
            )
            self._complete_stage(
                analysis,
                PipelineStage.CUSTOM_RUN_FILTER_VALIDATED,
                log,
                custom_run_mapping=mapping_path,
            )

            # Stage 5 — Waiting for filing collection (stop here; no SEC yet)
            analysis.pipeline.state = "waiting"
            analysis.pipeline.current_stage = PipelineStage.WAITING_FOR_FILING_COLLECTION
            analysis.pipeline.progress_pct = self.STAGE_PROGRESS[
                PipelineStage.WAITING_FOR_FILING_COLLECTION
            ]
            analysis.pipeline.stages_completed.append(
                PipelineStage.WAITING_FOR_FILING_COLLECTION
            )
            analysis.pipeline.completed_at = utc_now_iso()
            analysis.status = "waiting_for_filing_collection"
            analysis.updated_at = utc_now_iso()
            analysis.decision_log.append(
                DecisionLogEntry(
                    agent="Pipeline Orchestrator",
                    action="waiting_for_filing_collection",
                    detail=(
                        "Infrastructure pipeline complete. "
                        "SEC filing collection is not implemented yet."
                    ),
                    confidence=1.0,
                )
            )
            self.analysis_service.save(analysis)
            return analysis
        except (CustomRunParseError, WorkbookParseError, PipelineError, OSError, ValueError) as exc:
            return self._fail(analysis, str(exc))

    def _complete_stage(
        self,
        analysis: Analysis,
        stage: PipelineStage,
        log_entry: DecisionLogEntry,
        **output_fields: str,
    ) -> None:
        analysis.pipeline.stages_completed.append(stage)
        analysis.pipeline.current_stage = stage
        analysis.pipeline.progress_pct = self.STAGE_PROGRESS[stage]
        for field_name, value in output_fields.items():
            setattr(analysis.pipeline.outputs, field_name, value)
        analysis.decision_log.append(log_entry)
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)

    def _fail(self, analysis: Analysis, message: str) -> Analysis:
        analysis.pipeline.state = "failed"
        analysis.pipeline.current_stage = PipelineStage.FAILED
        analysis.pipeline.error = message
        analysis.pipeline.completed_at = utc_now_iso()
        analysis.status = "failed"
        analysis.updated_at = utc_now_iso()
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Pipeline Orchestrator",
                action="pipeline_failed",
                detail=message,
                confidence=0.0,
            )
        )
        self.analysis_service.save(analysis)
        return analysis

    def assert_ready_for_pipeline(self, analysis: Analysis) -> None:
        """Validate that an analysis has the uploads required to start the pipeline."""
        self._assert_ready_for_pipeline(analysis)

    @staticmethod
    def _assert_ready_for_pipeline(analysis: Analysis) -> None:
        if analysis.files.prefilled_workbook is None:
            raise PipelineError("prefilled_workbook must be uploaded before running the pipeline.")
        if analysis.files.custom_run_filter is None:
            raise PipelineError("custom_run_filter is required before running the pipeline.")
        if analysis.pipeline.state == "processing":
            raise PipelineError("Pipeline is already running for this analysis.")

    @staticmethod
    def stage_label(stage: PipelineStage | None) -> str:
        if stage is None:
            return "Not started"
        return PIPELINE_STAGE_LABELS.get(stage, stage.value)
