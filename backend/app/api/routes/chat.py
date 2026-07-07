from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis import ChatMessage, ChatMessageCreate
from app.services.analysis_service import AnalysisService

router = APIRouter()


def get_analysis_service(db: Session = Depends(get_db)) -> AnalysisService:
    return AnalysisService(db)


@router.get("/{analysis_id}/chat", response_model=list[ChatMessage])
def get_chat_history(
    analysis_id: str,
    service: AnalysisService = Depends(get_analysis_service),
) -> list[ChatMessage]:
    messages = service.get_chat(analysis_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return messages


@router.post("/{analysis_id}/chat", response_model=list[ChatMessage])
def send_chat_message(
    analysis_id: str,
    message: ChatMessageCreate,
    service: AnalysisService = Depends(get_analysis_service),
) -> list[ChatMessage]:
    messages = service.add_chat_message(analysis_id, message)
    if messages is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return messages
