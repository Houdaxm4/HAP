"""HAP pipeline orchestrator — workbook fill through analytical engine."""

from __future__ import annotations

from models.analysis import Analysis
from models.common import utc_now_iso
from models.pipeline import DecisionLogEntry, PipelineStage, PipelineStatus
from pipeline.stages.fetch_sec_filings import FetchSecFilingsStage
from pipeline.stages.fill_workbook import FillWorkbookStage
from pipeline.stages.parse_custom_run import ParseCustomRunStage
from pipeline.stages.parse_workbook import ParseWorkbookStage
from pipeline.stages.run_analysis import RunAnalysisStage
from pipeline.stages.validate_workbook import ValidateWorkbookStage
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""


class PipelineOrchestrator:
    """
    Run the HAP workflow:

    Upload → Parse workbook → Parse Custom_Run_Filter → SEC filings → Fill → Validate
    → Build CompanyFinancialModel → AnalysisEngine → Persist → Complete
    """

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
        self.parse_custom_run_stage = ParseCustomRunStage(output_service=self.output_service)
        self.fetch_sec_stage = FetchSecFilingsStage(output_service=self.output_service)
        self.fill_workbook_stage = FillWorkbookStage(output_service=self.output_service)
        self.validate_workbook_stage = ValidateWorkbookStage(output_service=self.output_service)
        self.run_analysis_stage = RunAnalysisStage(output_service=self.output_service)

    def run(self, analysis_id: str) -> Analysis:
        """Execute all pipeline stages sequentially."""
        analysis = self.analysis_service.get(analysis_id)
        self._assert_ready_for_pipeline(analysis)

        analysis.pipeline = PipelineStatus(
            state="processing",
            current_stage=PipelineStage.PARSE_WORKBOOK,
            progress_pct=5,
            started_at=utc_now_iso(),
        )
        analysis.status = "processing"
        analysis.decision_log = []
        self.analysis_service.save(analysis)

        try:
            workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
            custom_run_path = self.file_service.get_custom_run_filter_path(analysis)

            structure, structure_path, log = self.parse_workbook_stage.run(analysis, workbook_path)
            self._complete_stage(
                analysis,
                PipelineStage.PARSE_WORKBOOK,
                20,
                log,
                workbook_structure=structure_path,
            )

            custom_run, custom_run_path_rel, log = self.parse_custom_run_stage.run(
                analysis,
                custom_run_path,
            )
            self._complete_stage(
                analysis,
                PipelineStage.PARSE_CUSTOM_RUN,
                35,
                log,
                custom_run_data=custom_run_path_rel,
            )

            cache_dir = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
            manifest, company_facts, manifest_path, _, log = self.fetch_sec_stage.run(
                analysis,
                cache_dir=cache_dir,
            )
            analysis.cik = manifest.get("cik")
            self._complete_stage(
                analysis,
                PipelineStage.FETCH_SEC_FILINGS,
                55,
                log,
                sec_filings_manifest=manifest_path,
            )

            provenance_report, workbook_path_rel, provenance_path, log = self.fill_workbook_stage.run(
                analysis,
                workbook_path,
                custom_run,
                structure,
                company_facts,
                manifest,
            )
            self._complete_stage(
                analysis,
                PipelineStage.FILL_WORKBOOK,
                80,
                log,
                completed_workbook=workbook_path_rel,
                provenance_report=provenance_path,
            )

            completed_workbook_path = self.output_service.artifact_path(
                analysis_id,
                "completed_workbook.xlsx",
            )
            discrepancy_report, validation_path, discrepancy_path, log = (
                self.validate_workbook_stage.run(
                    analysis,
                    custom_run,
                    provenance_report,
                    completed_workbook_path,
                )
            )
            self._complete_stage(
                analysis,
                PipelineStage.VALIDATE_WORKBOOK,
                90,
                log,
                validation_report=validation_path,
                discrepancy_report=discrepancy_path,
            )

            _, _, model_path, result_path, log = self.run_analysis_stage.run(
                analysis,
                provenance_report,
                discrepancy_report,
                custom_run,
                company_facts,
            )
            self._complete_stage(
                analysis,
                PipelineStage.RUN_ANALYSIS,
                98,
                log,
                company_financial_model=model_path,
                analysis_engine_result=result_path,
            )

            analysis.pipeline.state = "complete"
            analysis.pipeline.current_stage = PipelineStage.COMPLETE
            analysis.pipeline.progress_pct = 100
            analysis.pipeline.completed_at = utc_now_iso()
            analysis.status = "complete" if analysis.is_pipeline_complete else "processing"
            analysis.updated_at = utc_now_iso()
            self.analysis_service.save(analysis)
            return analysis
        except Exception as exc:  # noqa: BLE001 - never leave analyses stuck processing
            return self._fail(analysis, str(exc))

    def _complete_stage(
        self,
        analysis: Analysis,
        stage: PipelineStage,
        progress_pct: int,
        log_entry: DecisionLogEntry,
        **output_fields: str,
    ) -> None:
        analysis.pipeline.stages_completed.append(stage)
        next_stage = self._next_stage(stage)
        analysis.pipeline.current_stage = next_stage
        analysis.pipeline.progress_pct = progress_pct
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

    @staticmethod
    def _next_stage(stage: PipelineStage) -> PipelineStage | None:
        order = [
            PipelineStage.PARSE_WORKBOOK,
            PipelineStage.PARSE_CUSTOM_RUN,
            PipelineStage.FETCH_SEC_FILINGS,
            PipelineStage.FILL_WORKBOOK,
            PipelineStage.VALIDATE_WORKBOOK,
            PipelineStage.RUN_ANALYSIS,
            PipelineStage.COMPLETE,
        ]
        try:
            index = order.index(stage)
        except ValueError:
            return None
        return order[index + 1] if index + 1 < len(order) else PipelineStage.COMPLETE

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
