"""Batch validation runner — create → stage uploads → run → collect outputs."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models.analysis import AnalysisFiles, CreateAnalysisRequest, UploadedFileMetadata
from models.api_responses import load_engine_result_dict
from models.common import utc_now_iso
from pipeline.orchestrator import PipelineOrchestrator
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService
from validation import ENGINE_VERSION
from validation.discovery import ValidationCase, discover_cases
from validation.extract import extract_analytical_fields, module_coverage

logger = logging.getLogger(__name__)


@dataclass
class ValidationRow:
    """One row destined for validation_results.csv."""

    company: str
    ticker: str
    engine_version: str = ENGINE_VERSION
    business_quality_score: float | None = None
    business_quality_rating: str | None = None
    investment_attractiveness_score: float | None = None
    investment_attractiveness_rating: str | None = None
    recommendation: str | None = None
    fair_value: float | None = None
    current_price: float | None = None
    margin_of_safety: float | None = None
    expected_return: float | None = None
    analysis_duration_sec: float | None = None
    status: str = "failed"
    failure_reason: str = ""
    analysis_id: str | None = None
    missing_data: bool = False
    incomplete_module_coverage: bool = False
    incomplete_modules: list[str] = field(default_factory=list)


@dataclass
class ValidationBatchResult:
    """Full batch outputs for reporting."""

    rows: list[ValidationRow]
    input_dir: Path
    output_dir: Path


def run_validation(
    input_dir: Path,
    output_dir: Path,
    *,
    analysis_type: str = "Validation",
    analysis_service: AnalysisService | None = None,
    file_service: FileService | None = None,
    output_service: OutputService | None = None,
    orchestrator: PipelineOrchestrator | None = None,
) -> ValidationBatchResult:
    """
    Run the pipeline for every discovered company package.

    Continues after individual failures. Writes failure details to the logger
    and to ``validation_failures.log`` under ``output_dir``.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    failure_log_path = output_dir / "validation_failures.log"
    file_handler = logging.FileHandler(failure_log_path, encoding="utf-8")
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s"),
    )
    logger.addHandler(file_handler)

    analysis_service = analysis_service or AnalysisService()
    file_service = file_service or FileService()
    output_service = output_service or OutputService()
    orchestrator = orchestrator or PipelineOrchestrator(
        analysis_service=analysis_service,
        file_service=file_service,
        output_service=output_service,
    )

    cases = discover_cases(input_dir)
    rows: list[ValidationRow] = []

    try:
        if not cases:
            logger.warning("No validation cases discovered in %s", input_dir)

        for index, case in enumerate(cases, start=1):
            logger.info(
                "[%s/%s] Starting validation for %s (%s)",
                index,
                len(cases),
                case.company,
                case.ticker,
            )
            row = _run_one_case(
                case,
                analysis_type=analysis_type,
                analysis_service=analysis_service,
                file_service=file_service,
                output_service=output_service,
                orchestrator=orchestrator,
            )
            rows.append(row)
            if row.status != "success":
                logger.error(
                    "Validation failed for %s (%s): %s",
                    case.company,
                    case.ticker,
                    row.failure_reason or "unknown",
                )
            else:
                logger.info(
                    "Validation succeeded for %s (%s) in %.1fs",
                    case.company,
                    case.ticker,
                    row.analysis_duration_sec or 0.0,
                )
    finally:
        logger.removeHandler(file_handler)
        file_handler.close()

    return ValidationBatchResult(rows=rows, input_dir=Path(input_dir), output_dir=output_dir)


def _run_one_case(
    case: ValidationCase,
    *,
    analysis_type: str,
    analysis_service: AnalysisService,
    file_service: FileService,
    output_service: OutputService,
    orchestrator: PipelineOrchestrator,
) -> ValidationRow:
    row = ValidationRow(company=case.company, ticker=case.ticker)
    started = time.perf_counter()
    try:
        analysis = analysis_service.create(
            CreateAnalysisRequest(
                company=case.company,
                ticker=case.ticker,
                analysis_type=analysis_type,
            )
        )
        row.analysis_id = analysis.analysis_id
        _stage_uploads(analysis, case, analysis_service, file_service)

        result = orchestrator.run(analysis.analysis_id)
        row.analysis_duration_sec = round(time.perf_counter() - started, 3)

        if result.pipeline.state == "failed" or result.status == "failed":
            row.status = "failed"
            row.failure_reason = result.pipeline.error or "Pipeline failed without error detail."
            return row

        if not result.is_pipeline_complete:
            row.status = "failed"
            row.failure_reason = (
                result.pipeline.error
                or f"Pipeline finished with state={result.pipeline.state!r} but outputs incomplete."
            )
            return row

        engine_result = load_engine_result_dict(output_service, result)
        _populate_success_fields(row, engine_result)
        row.status = "success"
        return row
    except Exception as exc:  # noqa: BLE001 - batch must continue
        row.analysis_duration_sec = round(time.perf_counter() - started, 3)
        row.status = "failed"
        row.failure_reason = str(exc)
        logger.exception(
            "Unhandled exception validating %s (%s)",
            case.company,
            case.ticker,
        )
        return row


def _stage_uploads(
    analysis: Any,
    case: ValidationCase,
    analysis_service: AnalysisService,
    file_service: FileService,
) -> None:
    """Copy local workbook + filter into upload storage (same layout as API upload)."""
    upload_dir = file_service.analysis_upload_dir(analysis.analysis_id)
    workbook_dest = upload_dir / "prefilled_workbook.xlsx"
    filter_suffix = case.custom_run_path.suffix.lower() or ".csv"
    filter_dest_name = f"custom_run_filter{filter_suffix}"
    filter_dest = upload_dir / filter_dest_name

    shutil.copy2(case.workbook_path, workbook_dest)
    shutil.copy2(case.custom_run_path, filter_dest)

    analysis.files = AnalysisFiles(
        prefilled_workbook=UploadedFileMetadata(
            filename=case.workbook_path.name,
            stored_filename=workbook_dest.name,
            size_bytes=workbook_dest.stat().st_size,
            uploaded_at=utc_now_iso(),
        ),
        custom_run_filter=UploadedFileMetadata(
            filename=case.custom_run_path.name,
            stored_filename=filter_dest.name,
            size_bytes=filter_dest.stat().st_size,
            uploaded_at=utc_now_iso(),
        ),
    )
    analysis.status = "uploaded"
    analysis.updated_at = utc_now_iso()
    analysis_service.save(analysis)


def _populate_success_fields(row: ValidationRow, engine_result: dict[str, Any] | None) -> None:
    fields = extract_analytical_fields(engine_result)
    row.business_quality_score = fields["business_quality_score"]
    row.business_quality_rating = fields["business_quality_rating"]
    row.investment_attractiveness_score = fields["investment_attractiveness_score"]
    row.investment_attractiveness_rating = fields["investment_attractiveness_rating"]
    row.recommendation = fields["recommendation"]
    row.fair_value = fields["fair_value"]
    row.current_price = fields["current_price"]
    row.margin_of_safety = fields["margin_of_safety"]
    row.expected_return = fields["expected_return"]

    _, skipped, errors, incomplete = module_coverage(engine_result)
    row.incomplete_modules = incomplete
    row.incomplete_module_coverage = bool(incomplete) or skipped > 0 or errors > 0

    recommendation = (row.recommendation or "").upper()
    row.missing_data = (
        row.business_quality_score is None
        or row.investment_attractiveness_score is None
        or row.recommendation is None
        or "INSUFFICIENT" in recommendation
        or row.fair_value is None
        or row.current_price is None
    )
