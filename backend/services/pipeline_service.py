"""Phase 1 pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis, utc_now_iso
from models.phase1 import Phase1Result
from models.pipeline import PipelineStage, PipelineState, pipeline_message_for_stage
from services.custom_run_filter_service import CustomRunFilterService
from services.file_service import FileService
from services.sec_edgar_service import SecEdgarService
from services.workbook_fill_service import WorkbookFillError, WorkbookFillService


class PipelineService:
    """Run the HAP analysis pipeline."""

    def __init__(
        self,
        file_service: FileService | None = None,
        filter_service: CustomRunFilterService | None = None,
        workbook_fill_service: WorkbookFillService | None = None,
        sec_service: SecEdgarService | None = None,
    ) -> None:
        self.file_service = file_service or FileService()
        self.filter_service = filter_service or CustomRunFilterService()
        self.sec_service = sec_service or SecEdgarService()
        self.workbook_fill_service = WorkbookFillService(self.sec_service)
        self.outputs_dir = Path(__file__).resolve().parent.parent / "storage" / "outputs"

    def get_state(self, analysis: Analysis) -> PipelineState:
        return analysis.pipeline

    def start(self, analysis: Analysis) -> PipelineState:
        if analysis.files.prefilled_workbook is None:
            raise ValueError("prefilled_workbook must be uploaded before starting the pipeline.")
        if analysis.files.custom_run_filter is None:
            raise ValueError("custom_run_filter must be uploaded before starting the pipeline.")

        analysis.pipeline.current_stage = PipelineStage.TEMPLATE_UPLOADED
        analysis.pipeline.stage_status = "in_progress"
        analysis.pipeline.message = "Phase 1 queued: parsing uploads and collecting SEC filings."
        analysis.status = "processing"
        analysis.updated_at = utc_now_iso()
        analysis.pipeline.updated_at = utc_now_iso()
        return analysis.pipeline

    def run_phase_one(self, analysis: Analysis) -> Phase1Result:
        try:
            return self._execute_phase_one(analysis)
        except Exception as exc:  # noqa: BLE001 - pipeline must capture and persist failures
            analysis.pipeline.current_stage = PipelineStage.FAILED
            analysis.pipeline.stage_status = "failed"
            analysis.pipeline.message = f"Phase 1 failed: {exc}"
            analysis.status = "failed"
            analysis.updated_at = utc_now_iso()
            analysis.pipeline.updated_at = utc_now_iso()
            raise

    def _execute_phase_one(self, analysis: Analysis) -> Phase1Result:
        self._set_stage(
            analysis,
            PipelineStage.FILING_COLLECTION,
            "Parsing workbook and custom_run filter; resolving ticker; downloading SEC filings.",
        )

        workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
        filter_path = self.file_service.get_custom_run_filter_path(analysis)
        workbook_parse = self.workbook_fill_service.parse_workbook(
            workbook_path,
            analysis.files.prefilled_workbook.filename,  # type: ignore[union-attr]
        )
        filter_parse = self.filter_service.parse(
            filter_path,
            analysis.files.custom_run_filter.filename,  # type: ignore[union-attr]
        )

        ticker = self._resolve_ticker(analysis, workbook_parse, filter_parse)
        profile = self.sec_service.resolve_company(ticker)
        analysis.ticker = profile.ticker
        analysis.company = filter_parse.company_override or profile.company_name

        filing_bundle = self.sec_service.collect_filings(profile, analysis.analysis_id)
        filings = filing_bundle.ten_k_filings + (
            [filing_bundle.latest_ten_q] if filing_bundle.latest_ten_q else []
        )

        self._set_stage(
            analysis,
            PipelineStage.WORKBOOK_COMPLETION,
            f"Filing collection complete for {profile.ticker}. Filling workbook from SEC facts.",
        )

        output_path = self.outputs_dir / analysis.analysis_id / "completed_workbook.xlsx"
        fills = self.workbook_fill_service.fill_workbook(
            workbook_path,
            filter_parse,
            profile,
            output_path,
        )

        self._set_stage(
            analysis,
            PipelineStage.WORKBOOK_VALIDATION,
            "Validating SEC-backed workbook fills.",
        )
        validation_passed, validation_message = self.workbook_fill_service.validate_fills(
            filter_parse.mappings,
            fills,
        )

        result = Phase1Result(
            resolved_ticker=profile.ticker,
            company_profile=profile,
            workbook_parse=workbook_parse,
            filter_parse=filter_parse,
            filings=filings,
            fills_applied=fills,
            completed_workbook_path=str(output_path),
            validation_passed=validation_passed,
            validation_message=validation_message,
        )

        analysis.phase1 = result
        analysis.pipeline.outputs.workbook = "ready" if fills else "pending"
        analysis.pipeline.current_stage = PipelineStage.FUNDAMENTAL_ANALYSIS
        analysis.pipeline.stage_status = "pending"
        analysis.pipeline.message = (
            "Phase 1 complete. Workbook filled from SEC filings and ready for fundamental analysis."
            if validation_passed
            else f"Phase 1 finished with validation warnings. {validation_message}"
        )
        analysis.status = "running"
        analysis.updated_at = utc_now_iso()
        analysis.pipeline.updated_at = utc_now_iso()
        return result

    def _resolve_ticker(self, analysis, workbook_parse, filter_parse) -> str:
        candidates = [
            filter_parse.ticker_override,
            workbook_parse.detected_ticker,
            analysis.ticker,
        ]
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip().upper()
        raise WorkbookFillError(
            "Unable to determine company ticker from workbook, custom_run filter, or analysis metadata."
        )

    def _set_stage(self, analysis: Analysis, stage: PipelineStage, message: str) -> None:
        analysis.pipeline.current_stage = stage
        analysis.pipeline.stage_status = "in_progress"
        analysis.pipeline.message = message
        analysis.status = "processing"
        analysis.updated_at = utc_now_iso()
        analysis.pipeline.updated_at = utc_now_iso()
