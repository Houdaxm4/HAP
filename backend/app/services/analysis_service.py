import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.seed import SEED_ANALYSES
from app.models.analysis import AnalysisRecord
from app.schemas.analysis import (
    Analysis,
    AnalysisCreateResponse,
    AnalysisListItem,
    AnalysisStatus,
    AnalysisStatusUpdate,
    ChatMessage,
    ChatMessageCreate,
    NewAnalysisForm,
)


ANALYSIS_TYPE_LABELS = {
    "new_company": "New Company",
    "annual_update": "Annual Update",
    "quarterly_update": "Quarterly Update",
}


class AnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def seed_if_empty(self) -> None:
        if self.db.query(AnalysisRecord).count() > 0:
            return

        for analysis in SEED_ANALYSES:
            record = self._analysis_to_record(analysis)
            self.db.add(record)
        self.db.commit()

    def list_analyses(self) -> list[AnalysisListItem]:
        records = self.db.query(AnalysisRecord).order_by(AnalysisRecord.updated_at.desc()).all()
        return [self._record_to_list_item(record) for record in records]

    def get_analysis(self, analysis_id: str) -> Analysis | None:
        record = self.db.get(AnalysisRecord, analysis_id.lower())
        if not record:
            return None
        return self._record_to_analysis(record)

    def create_analysis(
        self,
        form: NewAnalysisForm,
        prefilled: UploadFile | None = None,
        previous: UploadFile | None = None,
        custom_run_filter: UploadFile | None = None,
        upload_dir: Path | None = None,
    ) -> AnalysisCreateResponse:
        analysis_id = form.ticker.lower()
        now = datetime.utcnow()
        type_label = ANALYSIS_TYPE_LABELS[form.analysis_type]

        files: list[dict[str, str]] = []
        target_dir = upload_dir or self.settings.upload_dir / analysis_id
        target_dir.mkdir(parents=True, exist_ok=True)

        for upload, label in [
            (prefilled, "prefilled"),
            (previous, "previous"),
            (custom_run_filter, "custom_run_filter"),
        ]:
            if upload and upload.filename:
                saved = self._save_upload(upload, target_dir, label)
                files.append(saved)

        analysis = Analysis.model_validate(
            {
                "id": analysis_id,
                "company": form.company_name,
                "ticker": form.ticker.upper(),
                "type": type_label,
                "status": AnalysisStatus.QUEUED.value,
                "progress": 5,
                "startedAt": now.isoformat() + "Z",
                "updatedAt": now.isoformat() + "Z",
                "analyst": "HAP Analyst",
                "sector": "Pending classification",
                "marketCap": "—",
                "currentPrice": "—",
                "targetPrice": "—",
                "recommendation": "—",
                "overview": {
                    "thesis": form.notes or "Analysis initiated. Awaiting data ingestion.",
                    "keyMetrics": [],
                    "timeline": [
                        {"time": now.strftime("%H:%M"), "event": "Analysis queued", "status": "Complete"}
                    ],
                    "files": files,
                },
                "workbook": {"sheets": [], "preview": []},
                "verification": [],
                "decisionLog": [
                    {
                        "id": f"d-{uuid.uuid4().hex[:8]}",
                        "timestamp": now.strftime("%H:%M"),
                        "type": "data",
                        "title": "Run initiated",
                        "reasoning": f"{type_label} for {form.ticker.upper()}",
                        "confidence": 1.0,
                    }
                ],
                "summary": {
                    "rating": "Pending",
                    "targetPrice": "—",
                    "upside": "—",
                    "sections": [],
                    "risks": [],
                    "catalysts": [],
                },
                "chat": [
                    {
                        "role": "assistant",
                        "content": (
                            f"Starting {type_label} for {form.company_name} "
                            f"({form.ticker.upper()}). I'll notify you when data ingestion completes."
                        ),
                        "timestamp": now.strftime("%H:%M"),
                    }
                ],
            }
        )

        existing = self.db.get(AnalysisRecord, analysis_id)
        record = self._analysis_to_record(analysis)
        if existing:
            for column in AnalysisRecord.__table__.columns:
                setattr(existing, column.name, getattr(record, column.name))
        else:
            self.db.add(record)
        self.db.commit()

        return AnalysisCreateResponse(id=analysis_id, message="Analysis queued successfully")

    def update_analysis(self, analysis_id: str, update: AnalysisStatusUpdate) -> Analysis | None:
        record = self.db.get(AnalysisRecord, analysis_id.lower())
        if not record:
            return None

        if update.status is not None:
            record.status = update.status.value
        if update.progress is not None:
            record.progress = update.progress
        record.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return self._record_to_analysis(record)

    def get_chat(self, analysis_id: str) -> list[ChatMessage] | None:
        analysis = self.get_analysis(analysis_id)
        return analysis.chat if analysis else None

    def add_chat_message(self, analysis_id: str, message: ChatMessageCreate) -> list[ChatMessage] | None:
        record = self.db.get(AnalysisRecord, analysis_id.lower())
        if not record:
            return None

        analysis = self._record_to_analysis(record)
        now = datetime.utcnow().strftime("%H:%M")

        analysis.chat.append(ChatMessage(role="user", content=message.content, timestamp=now))
        analysis.chat.append(
            ChatMessage(
                role="assistant",
                content=(
                    f"Received your message for {analysis.ticker}. "
                    "The analysis pipeline will incorporate this context."
                ),
                timestamp=now,
            )
        )

        record.payload_json = analysis.model_dump_json(by_alias=True)
        record.updated_at = datetime.utcnow()
        self.db.commit()
        return analysis.chat

    def _save_upload(self, upload: UploadFile, target_dir: Path, prefix: str) -> dict[str, str]:
        filename = upload.filename or f"{prefix}_upload"
        safe_name = f"{prefix}_{filename}"
        destination = target_dir / safe_name
        content = upload.file.read()
        destination.write_bytes(content)

        size_kb = len(content) / 1024
        if size_kb >= 1024:
            size_label = f"{size_kb / 1024:.1f} MB"
        else:
            size_label = f"{int(size_kb)} KB"

        return {
            "name": safe_name,
            "size": size_label,
            "uploadedAt": datetime.utcnow().strftime("%H:%M"),
        }

    def _analysis_to_record(self, analysis: Analysis) -> AnalysisRecord:
        return AnalysisRecord(
            id=analysis.id,
            company=analysis.company,
            ticker=analysis.ticker,
            type=analysis.type,
            status=analysis.status.value,
            progress=analysis.progress,
            started_at=datetime.fromisoformat(analysis.started_at.replace("Z", "")),
            updated_at=datetime.fromisoformat(analysis.updated_at.replace("Z", "")),
            analyst=analysis.analyst,
            sector=analysis.sector,
            market_cap=analysis.market_cap,
            current_price=analysis.current_price,
            target_price=analysis.target_price,
            recommendation=analysis.recommendation,
            payload_json=analysis.model_dump_json(by_alias=True),
        )

    def _record_to_analysis(self, record: AnalysisRecord) -> Analysis:
        if record.payload_json:
            return Analysis.model_validate_json(record.payload_json)
        return Analysis.model_validate(
            {
                "id": record.id,
                "company": record.company,
                "ticker": record.ticker,
                "type": record.type,
                "status": record.status,
                "progress": record.progress,
                "startedAt": record.started_at.isoformat() + "Z",
                "updatedAt": record.updated_at.isoformat() + "Z",
                "analyst": record.analyst,
                "sector": record.sector,
                "marketCap": record.market_cap,
                "currentPrice": record.current_price,
                "targetPrice": record.target_price,
                "recommendation": record.recommendation,
                "overview": {"thesis": "", "keyMetrics": [], "timeline": [], "files": []},
                "workbook": {"sheets": [], "preview": []},
                "summary": {"rating": "—", "targetPrice": "—", "upside": "—"},
            }
        )

    def _record_to_list_item(self, record: AnalysisRecord) -> AnalysisListItem:
        return AnalysisListItem(
            id=record.id,
            company=record.company,
            ticker=record.ticker,
            type=record.type,
            status=AnalysisStatus(record.status),
            progress=record.progress,
            startedAt=record.started_at.isoformat() + "Z",
            updatedAt=record.updated_at.isoformat() + "Z",
        )