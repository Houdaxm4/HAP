from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis import (
    Analysis,
    AnalysisCreateResponse,
    AnalysisListItem,
    AnalysisStatusUpdate,
    NewAnalysisForm,
)
from app.services.analysis_service import AnalysisService
from app.services.file_storage import FileStorageService
from app.services.orchestrator import AnalysisOrchestrator

router = APIRouter()
orchestrator = AnalysisOrchestrator()
file_storage = FileStorageService()


def get_analysis_service(db: Session = Depends(get_db)) -> AnalysisService:
    return AnalysisService(db)


@router.get("", response_model=list[AnalysisListItem])
def list_analyses(service: AnalysisService = Depends(get_analysis_service)) -> list[AnalysisListItem]:
    return service.list_analyses()


@router.get("/{analysis_id}", response_model=Analysis)
def get_analysis(
    analysis_id: str,
    service: AnalysisService = Depends(get_analysis_service),
) -> Analysis:
    analysis = service.get_analysis(analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.post("", response_model=AnalysisCreateResponse, status_code=201)
async def create_analysis(
    company_name: str = Form(...),
    ticker: str = Form(...),
    analysis_type: str = Form(...),
    notes: str = Form(""),
    prefilled_workbook: UploadFile | None = File(None),
    previous_workbook: UploadFile | None = File(None),
    custom_run_filter: UploadFile | None = File(None),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisCreateResponse:
    if analysis_type not in {"new_company", "annual_update", "quarterly_update"}:
        raise HTTPException(status_code=400, detail="Invalid analysis_type")

    form = NewAnalysisForm(
        company_name=company_name,
        ticker=ticker,
        analysis_type=analysis_type,  # type: ignore[arg-type]
        notes=notes,
    )

    response = service.create_analysis(
        form,
        prefilled=prefilled_workbook,
        previous=previous_workbook,
        custom_run_filter=custom_run_filter,
        upload_dir=file_storage.analysis_dir(form.ticker.lower()),
    )

    await orchestrator.start(response.id)
    return response


@router.patch("/{analysis_id}", response_model=Analysis)
def update_analysis(
    analysis_id: str,
    update: AnalysisStatusUpdate,
    service: AnalysisService = Depends(get_analysis_service),
) -> Analysis:
    analysis = service.update_analysis(analysis_id, update)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis
