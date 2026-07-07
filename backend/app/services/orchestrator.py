import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.schemas.analysis import AnalysisStatus, AnalysisStatusUpdate
from app.services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, AnalysisStatus], None]


class AnalysisOrchestrator:
    """Simulates the analysis pipeline until real agents are wired in."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self, analysis_id: str, on_progress: ProgressCallback | None = None) -> None:
        if analysis_id in self._tasks and not self._tasks[analysis_id].done():
            return

        self._tasks[analysis_id] = asyncio.create_task(
            self._run_pipeline(analysis_id, on_progress),
            name=f"analysis-{analysis_id}",
        )

    async def _run_pipeline(self, analysis_id: str, on_progress: ProgressCallback | None) -> None:
        stages = [
            (20, AnalysisStatus.QUEUED, "Workbook ingestion"),
            (45, AnalysisStatus.RUNNING, "Data agent processing"),
            (70, AnalysisStatus.RUNNING, "Model agent building"),
            (90, AnalysisStatus.RUNNING, "Verification agent checks"),
            (95, AnalysisStatus.REVIEW, "Summary generation"),
            (100, AnalysisStatus.COMPLETE, "Analysis complete"),
        ]

        for progress, status, label in stages:
            await asyncio.sleep(4)
            self._update_db(analysis_id, progress, status)
            logger.info("Analysis %s: %s (%s%%)", analysis_id, label, progress)
            if on_progress:
                on_progress(analysis_id, progress, status)

    def _update_db(self, analysis_id: str, progress: int, status: AnalysisStatus) -> None:
        db = SessionLocal()
        try:
            service = AnalysisService(db)
            service.update_analysis(
                analysis_id,
                AnalysisStatusUpdate(status=status, progress=progress),
            )
        finally:
            db.close()

    def stop(self, analysis_id: str) -> None:
        task = self._tasks.get(analysis_id)
        if task and not task.done():
            task.cancel()
