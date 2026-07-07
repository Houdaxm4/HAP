import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.schemas.analysis import AnalysisStatus
from app.services.analysis_service import AnalysisService

router = APIRouter()


@router.websocket("/ws/analyses/{analysis_id}")
async def analysis_progress_ws(websocket: WebSocket, analysis_id: str) -> None:
    await websocket.accept()

    try:
        while True:
            db = SessionLocal()
            try:
                service = AnalysisService(db)
                analysis = service.get_analysis(analysis_id)
            finally:
                db.close()

            if not analysis:
                await websocket.send_json({"error": "Analysis not found"})
                await websocket.close(code=1008)
                return

            await websocket.send_text(
                json.dumps(
                    {
                        "analysisId": analysis.id,
                        "status": analysis.status.value,
                        "progress": analysis.progress,
                    }
                )
            )

            if analysis.status == AnalysisStatus.COMPLETE:
                break

            await websocket.receive_text()
    except WebSocketDisconnect:
        return
