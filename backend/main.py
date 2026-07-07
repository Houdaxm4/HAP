"""HAP backend v0.2 — FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.file_service import FileService, FileUploadError
from services.workbook_service import WorkbookService, WorkbookSummary

app = FastAPI(
    title="HAP Backend",
    description="Houda's Analyst Platform API",
    version="0.2.0",
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


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for the API service."""
    return {"status": "ok", "service": "HAP backend"}


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


@app.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    """Return full metadata for an analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis.to_dict()


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
