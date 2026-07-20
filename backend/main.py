"""HAP backend v0.3 — FastAPI application entry point."""

from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from models.api_responses import (
    AnalysisDetailResponse,
    AnalysisSummaryResponse,
    build_detail_response,
    build_summary_response,
    load_engine_result_dict,
)
from models.workbook_schema import WorkbookSummary
from pipeline.orchestrator import PipelineError, PipelineOrchestrator
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.file_service import FileService, FileUploadError
from services.output_service import OutputService
from services.workbook_service import WorkbookService

app = FastAPI(
    title="HAP Backend",
    description="Houda's Analyst Platform API",
    version="0.3.0",
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
output_service = OutputService()
pipeline_orchestrator = PipelineOrchestrator(
    analysis_service=analysis_service,
    file_service=file_service,
    output_service=output_service,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for the API service."""
    return {"status": "ok", "service": "HAP backend", "version": "0.3.0"}


@app.post("/analysis/create", response_model=CreateAnalysisResponse)
def create_analysis(request: CreateAnalysisRequest) -> CreateAnalysisResponse:
    """Create a new analysis and persist its metadata."""
    analysis = analysis_service.create(request)
    return CreateAnalysisResponse(analysis_id=analysis.analysis_id, status="created")


@app.post("/analysis/{analysis_id}/upload")
async def upload_analysis_files(
    analysis_id: str,
    prefilled_workbook: UploadFile = File(...),
    previous_workbook: UploadFile | None = File(None),
    custom_run_filter: UploadFile | None = File(None),
) -> dict:
    """Upload workbook files for an existing analysis."""
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

    return updated.to_dict()


@app.get("/analyses", response_model=list[AnalysisSummaryResponse])
def list_analyses() -> list[AnalysisSummaryResponse]:
    """Return summary DTOs for all analyses (no full engine artifacts)."""
    items: list[AnalysisSummaryResponse] = []
    for analysis in analysis_service.list_all():
        engine_result = load_engine_result_dict(output_service, analysis)
        items.append(build_summary_response(analysis, engine_result))
    return items


@app.get("/analysis/{analysis_id}", response_model=AnalysisDetailResponse)
def get_analysis(analysis_id: str) -> AnalysisDetailResponse:
    """Return detail metadata DTO. Engine JSON is available via outputs API."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    engine_result = load_engine_result_dict(output_service, analysis)
    return build_detail_response(analysis, engine_result)


@app.post("/analysis/{analysis_id}/run")
def run_analysis_pipeline(analysis_id: str, background_tasks: BackgroundTasks) -> dict:
    """Start the HAP backend pipeline for an uploaded analysis."""
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
    }


@app.post("/analysis/{analysis_id}/read-workbook", response_model=WorkbookSummary)
def read_workbook(analysis_id: str) -> WorkbookSummary:
    """Inspect the prefilled workbook without modifying it."""
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


@app.get("/analysis/{analysis_id}/outputs")
def list_output_artifacts(analysis_id: str) -> dict:
    """List downloadable pipeline output artifacts for an analysis."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "analysis_id": analysis_id,
        "artifacts": output_service.list_artifacts(analysis_id),
    }


@app.get("/analysis/{analysis_id}/outputs/{artifact_name}")
def download_output_artifact(analysis_id: str, artifact_name: str) -> FileResponse:
    """Download a pipeline output artifact."""
    try:
        analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Prevent path traversal into sec_cache or parent directories.
    if "/" in artifact_name or "\\" in artifact_name or artifact_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid artifact name.")

    path = output_service.artifact_path(analysis_id, artifact_name)
    if not path.exists() or not path.is_file():
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


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"
