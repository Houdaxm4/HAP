"""HAP pipeline orchestrator: infrastructure + trusted financial model."""

from __future__ import annotations

import logging
from pathlib import Path

from models.analysis import Analysis
from models.common import utc_now_iso
from models.custom_run import CustomRunMapping, CustomRunValidationReport
from models.pipeline import (
    PIPELINE_STAGE_LABELS,
    DecisionLogEntry,
    PipelineStage,
    PipelineStatus,
)
from models.workbook_schema import WorkbookStructure
from pipeline.stages.fetch_sec_filings import FetchSecFilingsStage
from pipeline.stages.fill_workbook import FillWorkbookStage
from pipeline.stages.parse_workbook import ParseWorkbookStage
from pipeline.stages.validate_custom_run import ValidateCustomRunStage
from pipeline.stages.validate_workbook import ValidateWorkbookStage
from services.analysis_service import AnalysisService
from services.custom_run_service import CustomRunParseError
from services.file_service import FileService
from services.output_service import OutputService
from services.sec_service import SecService, SecServiceError
from services.workbook_service import WorkbookParseError

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""


class PipelineOrchestrator:
    """
    Run HAP workflows:

    Phase 1 (infrastructure):
      Workbook uploaded → parsed → custom_run uploaded → validated →
      Waiting for filing collection

    Phase 2 (trusted financial model):
      Filings fetched → provenance recorded / workbook filled →
      workbook validated → validation report → provenance report → Complete

    Critical validation errors stop the pipeline before investment-analysis stages.
    """

    STAGE_PROGRESS: dict[PipelineStage, int] = {
        PipelineStage.WORKBOOK_UPLOADED: 10,
        PipelineStage.WORKBOOK_PARSED: 20,
        PipelineStage.CUSTOM_RUN_FILTER_UPLOADED: 30,
        PipelineStage.CUSTOM_RUN_FILTER_VALIDATED: 40,
        PipelineStage.WAITING_FOR_FILING_COLLECTION: 50,
        PipelineStage.FILINGS_FETCHED: 65,
        PipelineStage.PROVENANCE_RECORDED: 80,
        PipelineStage.WORKBOOK_VALIDATED: 88,
        PipelineStage.VALIDATION_REPORT_GENERATED: 92,
        PipelineStage.PROVENANCE_REPORT_GENERATED: 96,
        PipelineStage.COMPLETE: 100,
    }

    def __init__(
        self,
        analysis_service: AnalysisService | None = None,
        file_service: FileService | None = None,
        output_service: OutputService | None = None,
        sec_service: SecService | None = None,
        sec_cache_dir: Path | None = None,
    ) -> None:
        self.analysis_service = analysis_service or AnalysisService()
        self.file_service = file_service or FileService()
        self.output_service = output_service or OutputService()
        self.sec_service = sec_service or SecService(cache_dir=sec_cache_dir)
        self.sec_cache_dir = sec_cache_dir
        self.parse_workbook_stage = ParseWorkbookStage(output_service=self.output_service)
        self.validate_custom_run_stage = ValidateCustomRunStage(
            output_service=self.output_service
        )
        self.fetch_sec_stage = FetchSecFilingsStage(
            sec_service=self.sec_service,
            output_service=self.output_service,
        )
        self.fill_workbook_stage = FillWorkbookStage(
            sec_service=self.sec_service,
            output_service=self.output_service,
        )
        self.validate_workbook_stage = ValidateWorkbookStage(
            output_service=self.output_service
        )

    def run(self, analysis_id: str) -> Analysis:
        """Execute infrastructure pipeline stages sequentially (phase 1)."""
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

            analysis.pipeline.current_stage = PipelineStage.WORKBOOK_PARSED
            analysis.pipeline.progress_pct = 15
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

            analysis.pipeline.current_stage = PipelineStage.CUSTOM_RUN_FILTER_VALIDATED
            analysis.pipeline.progress_pct = 35
            self.analysis_service.save(analysis)
            _mapping, _report, mapping_path, report_path, log = self.validate_custom_run_stage.run(
                analysis,
                custom_run_path,
                structure,
            )
            self._complete_stage(
                analysis,
                PipelineStage.CUSTOM_RUN_FILTER_VALIDATED,
                log,
                custom_run_mapping=mapping_path,
                custom_run_validation_report=report_path,
            )

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
                        "Call continue-trusted-model to fetch filings, "
                        "record provenance, and validate the workbook."
                    ),
                    confidence=1.0,
                )
            )
            self.analysis_service.save(analysis)
            return analysis
        except (CustomRunParseError, WorkbookParseError, PipelineError, OSError, ValueError) as exc:
            return self._fail(analysis, str(exc))

    def continue_trusted_model(self, analysis_id: str) -> Analysis:
        """
        Phase 2: fetch SEC facts, fill workbook with provenance, validate.

        Stops before investment analysis when critical validation errors exist.
        Warnings allow completion with passed_with_warnings.
        """
        analysis = self.analysis_service.get(analysis_id)
        if not analysis.is_pipeline_complete and analysis.pipeline.state != "waiting":
            # Allow resume if infra artifacts exist even if state drifted.
            outputs = analysis.pipeline.outputs
            if not (
                outputs.workbook_structure
                and outputs.custom_run_mapping
                and outputs.custom_run_validation_report
            ):
                raise PipelineError(
                    "Infrastructure pipeline must complete before trusted-model continuation."
                )

        if analysis.pipeline.state == "processing":
            raise PipelineError("Pipeline is already running for this analysis.")

        analysis.pipeline.state = "processing"
        analysis.pipeline.error = None
        analysis.pipeline.completed_at = None
        analysis.status = "processing"
        analysis.updated_at = utc_now_iso()
        if analysis.pipeline.started_at is None:
            analysis.pipeline.started_at = utc_now_iso()
        self.analysis_service.save(analysis)

        try:
            workbook_path = self.file_service.get_prefilled_workbook_path(analysis)

            structure = WorkbookStructure.model_validate(
                self.output_service.read_json(analysis.analysis_id, "workbook_structure.json")
            )
            custom_run_mapping = CustomRunMapping.model_validate(
                self.output_service.read_json(analysis.analysis_id, "custom_run_mapping.json")
            )
            custom_run_validation = CustomRunValidationReport.model_validate(
                self.output_service.read_json(
                    analysis.analysis_id, "custom_run_validation_report.json"
                )
            )

            # Stage: filings fetched
            analysis.pipeline.current_stage = PipelineStage.FILINGS_FETCHED
            analysis.pipeline.progress_pct = 55
            self.analysis_service.save(analysis)

            manifest, company_facts, manifest_path, facts_path, log = self.fetch_sec_stage.run(
                analysis,
                cache_dir=self.sec_cache_dir,
            )
            self._complete_stage(
                analysis,
                PipelineStage.FILINGS_FETCHED,
                log,
                sec_filings_manifest=manifest_path,
                company_facts=facts_path,
            )
            if analysis.cik is None:
                analysis.cik = manifest.get("cik")
                self.analysis_service.save(analysis)

            # Stage: provenance recorded (+ workbook filled)
            analysis.pipeline.current_stage = PipelineStage.PROVENANCE_RECORDED
            analysis.pipeline.progress_pct = 70
            self.analysis_service.save(analysis)

            provenance_report, workbook_rel, provenance_path, fill_log = self.fill_workbook_stage.run(
                analysis,
                workbook_path,
                custom_run_mapping,
                structure,
                company_facts,
                manifest,
            )
            self._complete_stage(
                analysis,
                PipelineStage.PROVENANCE_RECORDED,
                fill_log,
                completed_workbook=workbook_rel,
                provenance_report=provenance_path,
            )

            # Optional financial statements artifact for BS/CF checks
            financial_statements = None
            statements_path = self.output_service.artifact_path(
                analysis.analysis_id, "financial_statements.json"
            )
            if statements_path.exists():
                financial_statements = self.output_service.read_json(
                    analysis.analysis_id, "financial_statements.json"
                )
                analysis.pipeline.outputs.financial_statements = (
                    self.output_service.relative_path(
                        analysis.analysis_id, "financial_statements.json"
                    )
                )

            completed_workbook_path = self.output_service.artifact_path(
                analysis.analysis_id, "completed_workbook.xlsx"
            )

            # Stage: workbook validated
            analysis.pipeline.current_stage = PipelineStage.WORKBOOK_VALIDATED
            analysis.pipeline.progress_pct = 85
            self.analysis_service.save(analysis)

            (
                validation_report,
                _discrepancy,
                validation_path,
                discrepancy_path,
                validate_log,
            ) = self.validate_workbook_stage.run(
                analysis,
                custom_run_mapping,
                provenance_report,
                completed_workbook_path,
                source_workbook_path=workbook_path,
                workbook_structure=structure,
                custom_run_validation_report=custom_run_validation,
                financial_statements=financial_statements,
            )
            self._complete_stage(
                analysis,
                PipelineStage.WORKBOOK_VALIDATED,
                validate_log,
                validation_report=validation_path,
                discrepancy_report=discrepancy_path,
            )

            analysis.pipeline.validation_status = validation_report.overall_status
            analysis.pipeline.critical_issue_count = validation_report.critical_count
            analysis.pipeline.warning_issue_count = validation_report.warning_count
            analysis.pipeline.informational_issue_count = validation_report.informational_count
            self.analysis_service.save(analysis)

            # Stage: validation report generated (artifact already written)
            self._complete_stage(
                analysis,
                PipelineStage.VALIDATION_REPORT_GENERATED,
                DecisionLogEntry(
                    agent="Workbook Validation Agent",
                    action="generate_validation_report",
                    detail=f"Wrote validation_report.json ({validation_report.overall_status}).",
                    confidence=1.0,
                    citations=[validation_path],
                ),
            )

            # Stage: provenance report generated (artifact already written during fill)
            self._complete_stage(
                analysis,
                PipelineStage.PROVENANCE_REPORT_GENERATED,
                DecisionLogEntry(
                    agent="Workbook Completion Agent",
                    action="generate_provenance_report",
                    detail=(
                        f"Wrote provenance_report.json with "
                        f"{len(provenance_report.entries)} entries."
                    ),
                    confidence=1.0,
                    citations=[provenance_path],
                ),
            )

            # Critical errors: stop before investment analysis; do not mark Complete.
            if validation_report.blocks_pipeline or validation_report.overall_status == "failed":
                analysis.pipeline.state = "failed"
                analysis.pipeline.current_stage = PipelineStage.FAILED
                analysis.pipeline.error = validation_report.summary
                analysis.pipeline.completed_at = utc_now_iso()
                analysis.status = "validation_failed"
                analysis.updated_at = utc_now_iso()
                analysis.decision_log.append(
                    DecisionLogEntry(
                        agent="Pipeline Orchestrator",
                        action="stopped_on_critical_validation",
                        detail=(
                            "Critical validation errors present. "
                            "Pipeline stopped before investment analysis / writing stages. "
                            + validation_report.summary
                        ),
                        confidence=0.0,
                        citations=[validation_path, provenance_path],
                    )
                )
                self.analysis_service.save(analysis)
                logger.warning(
                    "Trusted model stopped for %s due to critical validation errors",
                    analysis_id,
                )
                return analysis

            # Complete only when all required artifacts exist and no critical errors.
            if not (
                analysis.pipeline.outputs.completed_workbook
                and analysis.pipeline.outputs.provenance_report
                and analysis.pipeline.outputs.validation_report
            ):
                return self._fail(
                    analysis,
                    "Cannot mark complete: required trusted-model artifacts are missing.",
                )

            analysis.pipeline.state = "complete"
            analysis.pipeline.current_stage = PipelineStage.COMPLETE
            analysis.pipeline.progress_pct = 100
            if PipelineStage.COMPLETE not in analysis.pipeline.stages_completed:
                analysis.pipeline.stages_completed.append(PipelineStage.COMPLETE)
            analysis.pipeline.completed_at = utc_now_iso()
            if validation_report.overall_status == "passed_with_warnings":
                analysis.status = "complete_with_warnings"
            else:
                analysis.status = "complete"
            analysis.updated_at = utc_now_iso()
            analysis.decision_log.append(
                DecisionLogEntry(
                    agent="Pipeline Orchestrator",
                    action="trusted_model_complete",
                    detail=(
                        "Trusted financial model complete: workbook, provenance, and "
                        f"validation artifacts ready ({validation_report.overall_status}). "
                        "Investment analysis stages are not started in this milestone."
                    ),
                    confidence=1.0,
                    citations=[
                        analysis.pipeline.outputs.completed_workbook,
                        analysis.pipeline.outputs.provenance_report,
                        analysis.pipeline.outputs.validation_report,
                    ],
                )
            )
            self.analysis_service.save(analysis)
            return analysis
        except (SecServiceError, CustomRunParseError, WorkbookParseError, PipelineError, OSError, ValueError) as exc:
            return self._fail(analysis, str(exc))

    def _complete_stage(
        self,
        analysis: Analysis,
        stage: PipelineStage,
        log_entry: DecisionLogEntry,
        **output_fields: str,
    ) -> None:
        if stage not in analysis.pipeline.stages_completed:
            analysis.pipeline.stages_completed.append(stage)
        analysis.pipeline.current_stage = stage
        analysis.pipeline.progress_pct = self.STAGE_PROGRESS.get(stage, analysis.pipeline.progress_pct)
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

    def assert_ready_for_trusted_model(self, analysis: Analysis) -> None:
        """Validate that phase-1 artifacts exist before continuing."""
        outputs = analysis.pipeline.outputs
        if not (
            outputs.workbook_structure
            and outputs.custom_run_mapping
            and outputs.custom_run_validation_report
        ):
            raise PipelineError(
                "Run the infrastructure pipeline before continuing the trusted model."
            )
        if analysis.pipeline.state == "processing":
            raise PipelineError("Pipeline is already running for this analysis.")

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
