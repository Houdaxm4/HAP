from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalysisRecord(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    company: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="Queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    analyst: Mapped[str] = mapped_column(String(128), default="HAP Analyst")
    sector: Mapped[str] = mapped_column(String(255), default="")
    market_cap: Mapped[str] = mapped_column(String(64), default="—")
    current_price: Mapped[str] = mapped_column(String(64), default="—")
    target_price: Mapped[str] = mapped_column(String(64), default="—")
    recommendation: Mapped[str] = mapped_column(String(16), default="—")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
