"""HAP backend v0.3 — FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.analysis import CreateAnalysisRequest, CreateAnalysisResponse
from models.pipeline import PipelineState, PipelineStepResponse
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.file_service import FileService, FileUploadError
from services.pipeline_service import PipelineService
from services.workbook_service import WorkbookService, WorkbookSummary

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
pipeline_service = PipelineService()


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
    custom_run_filter: UploadFile = File(...),
) -> dict:
    """Upload the prefilled template and required custom_run filter."""
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
def start_pipeline(analysis_id: str) -> PipelineState:
    """Start the analysis pipeline after required uploads are present."""
    try:
        analysis = analysis_service.get(analysis_id)
        state = pipeline_service.start(analysis)
        analysis_service.save(analysis)
        return state
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analysis/{analysis_id}/pipeline", response_model=PipelineState)
def get_pipeline(analysis_id: str) -> PipelineState:
    """Return the current pipeline state for an analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return pipeline_service.get_state(analysis)


@app.post(
    "/analysis/{analysis_id}/pipeline/collect-filings",
    response_model=PipelineStepResponse,
)
def collect_filings(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: collect SEC filings and market materials."""
    return _run_pipeline_step(analysis_id, pipeline_service.collect_filings)


@app.post(
    "/analysis/{analysis_id}/pipeline/parse-filings",
    response_model=PipelineStepResponse,
)
def parse_filings(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: parse collected SEC filings."""
    return _run_pipeline_step(analysis_id, pipeline_service.parse_filings)


@app.post(
    "/analysis/{analysis_id}/pipeline/fill-workbook",
    response_model=PipelineStepResponse,
)
def fill_workbook(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: complete blanks in the uploaded workbook template."""
    return _run_pipeline_step(analysis_id, pipeline_service.fill_workbook)


@app.post(
    "/analysis/{analysis_id}/pipeline/validate-workbook",
    response_model=PipelineStepResponse,
)
def validate_workbook(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: validate completed workbook against sources."""
    return _run_pipeline_step(analysis_id, pipeline_service.validate_workbook)


@app.post(
    "/analysis/{analysis_id}/pipeline/fundamental-analysis",
    response_model=PipelineStepResponse,
)
def fundamental_analysis(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: run fundamental analysis."""
    return _run_pipeline_step(analysis_id, pipeline_service.run_fundamental_analysis)


@app.post(
    "/analysis/{analysis_id}/pipeline/market-valuation-analysis",
    response_model=PipelineStepResponse,
)
def market_valuation_analysis(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: run market and valuation analysis."""
    return _run_pipeline_step(analysis_id, pipeline_service.run_market_valuation_analysis)


@app.post(
    "/analysis/{analysis_id}/pipeline/generate-memo",
    response_model=PipelineStepResponse,
)
def generate_memo(analysis_id: str) -> PipelineStepResponse:
    """Placeholder: generate investment memo and final outputs."""
    return _run_pipeline_step(analysis_id, pipeline_service.generate_investment_memo)


@app.get("/analysis/{analysis_id}/outputs")
def get_outputs(analysis_id: str) -> dict:
    """Return pipeline output availability for an analysis."""
    try:
        analysis = analysis_service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "analysis_id": analysis.analysis_id,
        "ticker": analysis.ticker,
        "pipeline_stage": analysis.pipeline.current_stage,
        "outputs": analysis.pipeline.outputs.model_dump(),
        "message": (
            "Analysis pipeline outputs are pending real backend implementation."
            if analysis.pipeline.current_stage != "outputs_ready"
            else "Outputs are ready."
        ),
    }


def _run_pipeline_step(analysis_id: str, runner) -> PipelineStepResponse:
    try:
        analysis = analysis_service.get(analysis_id)
        response = runner(analysis)
        analysis_service.save(analysis)
        return response
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
