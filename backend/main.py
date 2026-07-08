"""HAP backend v0.4 — FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from models.pipeline import PipelineState, PipelineStepResponse
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.file_service import FileService, FileUploadError
from services.pipeline_service import PipelineService
from services.workbook_service import WorkbookService, WorkbookSummary

logger = logging.getLogger(__name__)

app = FastAPI(
    title="HAP Backend",
    description="Houda's Analyst Platform API",
    version="0.4.0",
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
pipeline_service = PipelineService()


def _run_phase_one_background(analysis_id: str) -> None:
    try:
        analysis = analysis_service.get(analysis_id)
        pipeline_service.run_phase_one(analysis)
        analysis_service.save(analysis)
    except Exception:  # noqa: BLE001
        logger.exception("Phase 1 pipeline failed for analysis %s", analysis_id)
        try:
            analysis = analysis_service.get(analysis_id)
            analysis_service.save(analysis)
        except AnalysisNotFoundError:
            return


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "HAP backend"}


@app.post("/analysis/create", response_model=CreateAnalysisResponse)
def create_analysis(request: CreateAnalysisRequest) -> CreateAnalysisResponse:
    analysis = analysis_service.create(request)
    return CreateAnalysisResponse(analysis_id=analysis.analysis_id, status="created")


@app.post("/analysis/{analysis_id}/upload")
async def upload_analysis_files(
    analysis_id: str,
    prefilled_workbook: UploadFile = File(...),
    previous_workbook: UploadFile | None = File(None),
    custom_run_filter: UploadFile = File(...),
) -> dict:
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


@app.post("/analysis/{analysis_id}/pipeline/start", response_model=PipelineState)
def start_pipeline(
    analysis_id: str,
    background_tasks: BackgroundTasks,
) -> PipelineState:
    try:
        analysis = analysis_service.get(analysis_id)
        state = pipeline_service.start(analysis)
        analysis_service.save(analysis)
        background_tasks.add_task(_run_phase_one_background, analysis_id)
        return state
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/pipeline", response_model=PipelineState)
def get_pipeline(analysis_id: str) -> PipelineState:
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return pipeline_service.get_state(analysis)


@app.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analysis.to_dict()


@app.get("/analysis/{analysis_id}/outputs")
def get_outputs(analysis_id: str) -> dict:
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "analysis_id": analysis.analysis_id,
        "ticker": analysis.ticker,
        "pipeline_stage": analysis.pipeline.current_stage,
        "outputs": analysis.pipeline.outputs.model_dump(),
        "phase1": analysis.phase1.model_dump() if analysis.phase1 else None,
        "message": analysis.pipeline.message,
    }


@app.get("/analysis/{analysis_id}/outputs/workbook")
def download_completed_workbook(analysis_id: str) -> FileResponse:
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if analysis.phase1 is None or not analysis.phase1.completed_workbook_path:
        raise HTTPException(status_code=404, detail="Completed workbook is not available yet.")

    path = Path(analysis.phase1.completed_workbook_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Completed workbook file is missing on disk.")

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{analysis.ticker}_Completed_Workbook.xlsx",
    )


@app.post("/analysis/{analysis_id}/read-workbook", response_model=WorkbookSummary)
def read_workbook(analysis_id: str) -> WorkbookSummary:
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
