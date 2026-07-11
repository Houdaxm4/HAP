"""HAP backend v0.6 — FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from models.common import utc_now_iso
from models.custom_run import CustomRunValidationReport
from models.filings import CollectFilingsRequest, FilingCollectionResult
from models.pipeline import PIPELINE_STAGE_LABELS, DecisionLogEntry, PipelineStage
from models.statements import ExtractStatementsRequest, FinancialStatementsResult
from models.workbook_schema import WorkbookStructure, WorkbookSummary
from pipeline.orchestrator import PipelineError, PipelineOrchestrator
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.custom_run_service import CustomRunParseError, CustomRunService
from services.file_service import FileService, FileUploadError
from services.filing_collector import FilingCollector, FilingCollectorError
from services.output_service import OutputService
from services.statement_extractor import FinancialStatementExtractor, StatementExtractorError
from services.workbook_service import WorkbookParseError, WorkbookService

app = FastAPI(
    title="HAP Backend",
    description="Houda's Analyst Platform API",
    version="0.6.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

analysis_service = AnalysisService()
file_service = FileService()
workbook_service = WorkbookService()
custom_run_service = CustomRunService()
output_service = OutputService()
filing_collector = FilingCollector()
statement_extractor = FinancialStatementExtractor()
pipeline_orchestrator = PipelineOrchestrator(
    analysis_service=analysis_service,
    file_service=file_service,
    output_service=output_service,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for the API service."""
    return {"status": "ok", "service": "HAP backend", "version": "0.6.0"}


@app.get("/analysis")
def list_analyses() -> list[dict]:
    """Return all analyses with UI-facing display status."""
    results: list[dict] = []
    for analysis in analysis_service.list_all():
        payload = analysis.to_dict()
        payload["display_status"] = _display_status(analysis)
        results.append(payload)
    return results


@app.post("/analysis/create", response_model=CreateAnalysisResponse)
def create_analysis(request: CreateAnalysisRequest) -> CreateAnalysisResponse:
    """Create a new analysis and persist its metadata."""
    analysis = analysis_service.create(request)
    return CreateAnalysisResponse(analysis_id=analysis.analysis_id, status="created")


@app.post("/analysis/{analysis_id}/upload")
async def upload_analysis_files(
    analysis_id: str,
    background_tasks: BackgroundTasks,
    prefilled_workbook: UploadFile = File(...),
    custom_run_filter: UploadFile = File(...),
    previous_workbook: UploadFile | None = File(None),
    start_pipeline: bool = True,
) -> dict:
    """
    Upload and validate workbook files for an existing analysis.

    Both ``prefilled_workbook`` and ``custom_run_filter`` are required.
    When ``start_pipeline`` is true (default), the infrastructure pipeline
    starts in the background after a successful upload.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        updated = await file_service.handle_uploads(
            analysis,
            prefilled_workbook=prefilled_workbook,
            previous_workbook=previous_workbook,
            custom_run_filter=custom_run_filter,
        )
        analysis_service.save(updated)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pipeline_started = False
    if start_pipeline:
        try:
            pipeline_orchestrator.assert_ready_for_pipeline(updated)
        except PipelineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        background_tasks.add_task(pipeline_orchestrator.run, analysis_id)
        pipeline_started = True

    # Re-load so the response reflects pipeline progress when background
    # tasks run inline (e.g. TestClient) or still show uploaded otherwise.
    refreshed = analysis_service.get(analysis_id)
    payload = refreshed.to_dict()
    payload["display_status"] = _display_status(refreshed)
    payload["pipeline_started"] = pipeline_started
    return payload


@app.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    """Return full metadata for an analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = analysis.to_dict()
    payload["display_status"] = _display_status(analysis)
    return payload


@app.post("/analysis/{analysis_id}/run")
def run_analysis_pipeline(analysis_id: str, background_tasks: BackgroundTasks) -> dict:
    """Start the HAP infrastructure pipeline for an uploaded analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        pipeline_orchestrator.assert_ready_for_pipeline(analysis)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(pipeline_orchestrator.run, analysis_id)
    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "message": "Pipeline started. Poll GET /analysis/{id} for progress.",
        "stages": [PIPELINE_STAGE_LABELS[stage] for stage in PipelineStage if stage != PipelineStage.FAILED],
    }


@app.post("/analysis/{analysis_id}/continue-trusted-model")
def continue_trusted_model(analysis_id: str, background_tasks: BackgroundTasks) -> dict:
    """
    Continue into the trusted financial model milestone:

    fetch filings → fill workbook with provenance → validate → write reports.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        pipeline_orchestrator.assert_ready_for_trusted_model(analysis)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background_tasks.add_task(pipeline_orchestrator.continue_trusted_model, analysis_id)
    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "message": (
            "Trusted-model pipeline started. Poll GET /analysis/{id} for progress, "
            "validation status, and artifact availability."
        ),
        "stages": [
            PIPELINE_STAGE_LABELS[stage]
            for stage in (
                PipelineStage.FILINGS_FETCHED,
                PipelineStage.PROVENANCE_RECORDED,
                PipelineStage.WORKBOOK_VALIDATED,
                PipelineStage.VALIDATION_REPORT_GENERATED,
                PipelineStage.PROVENANCE_REPORT_GENERATED,
                PipelineStage.COMPLETE,
            )
        ],
    }


@app.get("/analysis/{analysis_id}/validation-report")
def get_validation_report(analysis_id: str) -> dict:
    """Return the trusted-model validation report artifact."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = output_service.artifact_path(analysis_id, "validation_report.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Validation report not available yet.")
    return output_service.read_json(analysis_id, "validation_report.json")


@app.get("/analysis/{analysis_id}/provenance-report")
def get_provenance_report(analysis_id: str) -> dict:
    """Return the full provenance report artifact."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = output_service.artifact_path(analysis_id, "provenance_report.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Provenance report not available yet.")
    return output_service.read_json(analysis_id, "provenance_report.json")


@app.post("/analysis/{analysis_id}/read-workbook", response_model=WorkbookSummary)
def read_workbook(analysis_id: str) -> WorkbookSummary:
    """Inspect the prefilled workbook without modifying it (summary view)."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        workbook_path = file_service.get_prefilled_workbook_path(analysis)
        original_filename = analysis.files.prefilled_workbook.filename  # type: ignore[union-attr]
        return workbook_service.read_summary(workbook_path, original_filename)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/workbook-structure", response_model=WorkbookStructure)
def get_workbook_structure(analysis_id: str) -> WorkbookStructure:
    """
    Return the full JSON representation of the uploaded workbook.

    Prefers the pipeline artifact when available; otherwise parses the uploaded
    file on demand. The source workbook is never modified.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    artifact = output_service.artifact_path(analysis_id, "workbook_structure.json")
    if artifact.exists():
        return WorkbookStructure.model_validate(output_service.read_json(analysis_id, "workbook_structure.json"))

    try:
        workbook_path = file_service.get_prefilled_workbook_path(analysis)
        original_filename = analysis.files.prefilled_workbook.filename  # type: ignore[union-attr]
        return workbook_service.parse_structure(workbook_path, original_filename)
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkbookParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/analysis/{analysis_id}/custom-run-validation",
    response_model=CustomRunValidationReport,
)
def get_custom_run_validation(analysis_id: str) -> CustomRunValidationReport:
    """
    Return the custom_run_filter validation report.

    Prefers the pipeline artifact when available; otherwise validates on demand.
    Never populates the workbook template.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    artifact = output_service.artifact_path(analysis_id, "custom_run_validation_report.json")
    if artifact.exists():
        return CustomRunValidationReport.model_validate(
            output_service.read_json(analysis_id, "custom_run_validation_report.json")
        )

    try:
        custom_run_path = file_service.get_custom_run_filter_path(analysis)
        original_filename = analysis.files.custom_run_filter.filename  # type: ignore[union-attr]
        mapping = custom_run_service.parse(custom_run_path, original_filename)

        structure = None
        workbook_artifact = output_service.artifact_path(analysis_id, "workbook_structure.json")
        if workbook_artifact.exists():
            structure = WorkbookStructure.model_validate(
                output_service.read_json(analysis_id, "workbook_structure.json")
            )
        elif analysis.files.prefilled_workbook is not None:
            workbook_path = file_service.get_prefilled_workbook_path(analysis)
            structure = workbook_service.parse_structure(
                workbook_path,
                analysis.files.prefilled_workbook.filename,
            )

        return custom_run_service.validate(
            mapping,
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            structure=structure,
        )
    except FileUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CustomRunParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/outputs/{artifact_name}")
def download_output_artifact(analysis_id: str, artifact_name: str) -> FileResponse:
    """Download a pipeline output artifact."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = output_service.artifact_path(analysis_id, artifact_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_name}' not found.")

    return FileResponse(
        path=path,
        filename=artifact_name,
        media_type=_media_type_for(path),
    )


@app.get("/analysis/{analysis_id}/provenance/{cell_ref:path}")
def get_cell_provenance(analysis_id: str, cell_ref: str) -> dict:
    """
    Return explainability metadata for one workbook cell.

    Example: /analysis/{id}/provenance/Income%20Statement!B5
    """
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    provenance_path = output_service.artifact_path(analysis_id, "provenance_report.json")
    if not provenance_path.exists():
        raise HTTPException(status_code=404, detail="Provenance report not available yet.")

    import json

    with provenance_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    normalized_ref = cell_ref.replace("%21", "!")
    for entry in report.get("entries", []):
        if entry.get("cell_ref") == normalized_ref:
            return entry

    raise HTTPException(status_code=404, detail=f"No provenance found for '{normalized_ref}'.")


@app.post("/filings/collect", response_model=FilingCollectionResult)
def collect_filings(request: CollectFilingsRequest) -> FilingCollectionResult:
    """
    Collect latest 10-K, latest 10-Q, and historical 10-Ks for a ticker.

    Uses the SEC EDGAR API, resolves CIK automatically, supports amendments,
    downloads HTML/XBRL into the local cache, and stores metadata in SQLite.
    Does not extract financial values.
    """
    try:
        return filing_collector.collect(request)
    except FilingCollectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/filings/collection/{collection_id}", response_model=FilingCollectionResult)
def get_filing_collection(collection_id: str) -> FilingCollectionResult:
    """Return one filing collection by id."""
    result = filing_collector.get_collection(collection_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Filing collection '{collection_id}' not found.")
    return result


@app.get("/filings/{ticker}", response_model=FilingCollectionResult)
def get_filings_for_ticker(ticker: str) -> FilingCollectionResult:
    """Return the latest stored filing collection for a ticker."""
    result = filing_collector.get_filings_for_ticker(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No filings collected for '{ticker}'.")
    return result


@app.post("/analysis/{analysis_id}/collect-filings", response_model=FilingCollectionResult)
def collect_filings_for_analysis(
    analysis_id: str,
    historical_years: int = 10,
    download_documents: bool = True,
) -> FilingCollectionResult:
    """
    Run the Filing Collector for an analysis ticker and attach the result.

    Intended for analyses waiting on filing collection. No extraction is performed.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = filing_collector.collect(
            CollectFilingsRequest(
                ticker=analysis.ticker,
                historical_years=historical_years,
                download_documents=download_documents,
            )
        )
    except FilingCollectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analysis.cik = result.cik
    analysis.filing_collection_id = result.collection_id
    analysis.status = "filings_collected"
    analysis.updated_at = utc_now_iso()
    analysis.pipeline.outputs.filing_collection = output_service.write_json(
        analysis.analysis_id,
        "filing_collection.json",
        result,
    )
    analysis.decision_log.append(
        DecisionLogEntry(
            agent="Document Collection Agent",
            action="collect_filings",
            detail=(
                f"Collected filings for {result.ticker} (CIK {result.cik}): "
                f"latest 10-K={'yes' if result.latest_10k else 'no'}, "
                f"latest 10-Q={'yes' if result.latest_10q else 'no'}, "
                f"historical 10-Ks={len(result.historical_10ks)}. "
                "No extraction performed."
            ),
            confidence=1.0,
            citations=[analysis.pipeline.outputs.filing_collection],
        )
    )
    analysis_service.save(analysis)
    return result


@app.post("/statements/extract", response_model=FinancialStatementsResult)
def extract_financial_statements(request: ExtractStatementsRequest) -> FinancialStatementsResult:
    """
    Extract Balance Sheet, Income Statement, and Cash Flow for a ticker.

    Uses SEC company facts (XBRL). Does not compute ratios or produce analysis.
    """
    try:
        return statement_extractor.extract(request)
    except StatementExtractorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/analysis/{analysis_id}/extract-statements",
    response_model=FinancialStatementsResult,
)
def extract_statements_for_analysis(
    analysis_id: str,
    max_annual_periods: int = 10,
    max_quarterly_periods: int = 8,
    include_quarters: bool = True,
) -> FinancialStatementsResult:
    """
    Extract the three primary financial statements for an analysis ticker.

    Balance Sheet, Income Statement, and Cash Flow only. No ratios. No analysis.
    """
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = statement_extractor.extract(
            ExtractStatementsRequest(
                ticker=analysis.ticker,
                max_annual_periods=max_annual_periods,
                max_quarterly_periods=max_quarterly_periods,
                include_quarters=include_quarters,
            )
        )
    except StatementExtractorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analysis.cik = result.cik
    analysis.financial_statements_id = result.extraction_id
    analysis.status = "statements_extracted"
    analysis.updated_at = utc_now_iso()
    analysis.pipeline.outputs.financial_statements = output_service.write_json(
        analysis.analysis_id,
        "financial_statements.json",
        result,
    )
    analysis.decision_log.append(
        DecisionLogEntry(
            agent="Financial Statement Extractor",
            action="extract_statements",
            detail=(
                f"Extracted Balance Sheet ({result.balance_sheet.populated_value_count} values), "
                f"Income Statement ({result.income_statement.populated_value_count} values), "
                f"and Cash Flow ({result.cash_flow.populated_value_count} values) for {result.ticker}. "
                "No ratios or analysis performed."
            ),
            confidence=1.0,
            citations=[analysis.pipeline.outputs.financial_statements],
        )
    )
    analysis_service.save(analysis)
    return result


@app.get("/analysis/{analysis_id}/statements", response_model=FinancialStatementsResult)
def get_analysis_statements(analysis_id: str) -> FinancialStatementsResult:
    """Return previously extracted financial statements for an analysis."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = output_service.artifact_path(analysis_id, "financial_statements.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Financial statements not extracted yet.")
    return FinancialStatementsResult.model_validate(
        output_service.read_json(analysis_id, "financial_statements.json")
    )


def _display_status(analysis) -> str:
    """UI-facing status for infrastructure + trusted-model pipeline."""
    if analysis.status == "validation_failed" or (
        analysis.pipeline.state == "failed"
        and analysis.pipeline.validation_status == "failed"
    ):
        return "Validation failed"
    if analysis.pipeline.state == "failed" or analysis.status == "failed":
        return "Failed"
    if analysis.is_trusted_model_complete or analysis.pipeline.state == "complete":
        if analysis.pipeline.validation_status == "passed_with_warnings":
            return "Complete with warnings"
        return "Complete"
    if analysis.financial_statements_id or analysis.status == "statements_extracted":
        return "Statements extracted"
    if analysis.filing_collection_id or analysis.status == "filings_collected":
        return "Filings collected"
    if (
        analysis.pipeline.state == "waiting"
        or analysis.status == "waiting_for_filing_collection"
    ):
        return "Waiting for filing collection"
    if analysis.pipeline.state == "processing" or analysis.status == "processing":
        return "Processing"
    if analysis.status == "uploaded":
        return "Uploaded"
    if analysis.status == "created":
        return "Created"
    return "Processing"


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"
