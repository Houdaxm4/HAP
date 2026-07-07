from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    RUNNING = "Running"
    QUEUED = "Queued"
    REVIEW = "Review"
    COMPLETE = "Complete"


class AnalysisType(str, Enum):
    NEW_COMPANY = "New Company"
    ANNUAL_UPDATE = "Annual Update"
    QUARTERLY_UPDATE = "Quarterly Update"
    DCF_VALUATION = "DCF Valuation"
    COMPETITIVE_MOAT = "Competitive Moat"
    EARNINGS_PREVIEW = "Earnings Preview"


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    PENDING = "pending"


class DecisionType(str, Enum):
    DATA = "data"
    MODEL = "model"
    ASSUMPTION = "assumption"
    OVERRIDE = "override"


class KeyMetric(BaseModel):
    label: str
    value: str
    change: str | None = None


class TimelineEvent(BaseModel):
    time: str
    event: str
    status: AnalysisStatus | Literal["Complete"]


class UploadedFileInfo(BaseModel):
    name: str
    size: str
    uploaded_at: str = Field(alias="uploadedAt")

    model_config = {"populate_by_name": True}


class OverviewData(BaseModel):
    thesis: str
    key_metrics: list[KeyMetric] = Field(default_factory=list, alias="keyMetrics")
    timeline: list[TimelineEvent] = Field(default_factory=list)
    files: list[UploadedFileInfo] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class WorkbookSheet(BaseModel):
    name: str
    rows: int
    cols: int = 0


class WorkbookPreviewCell(BaseModel):
    cell: str
    value: str
    formula: str | None = None


class WorkbookData(BaseModel):
    sheets: list[WorkbookSheet] = Field(default_factory=list)
    preview: list[WorkbookPreviewCell] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    item: str
    status: VerificationStatus
    detail: str
    checked_at: str | None = Field(default=None, alias="checkedAt")

    model_config = {"populate_by_name": True}


class DecisionLogEntry(BaseModel):
    id: str
    timestamp: str
    type: DecisionType
    title: str
    reasoning: str
    confidence: float


class SummarySection(BaseModel):
    heading: str
    content: str


class SummaryData(BaseModel):
    rating: str
    target_price: str = Field(alias="targetPrice")
    upside: str
    sections: list[SummarySection] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ChatMessage(BaseModel):
    role: Literal["assistant", "user"]
    content: str
    timestamp: str


class Analysis(BaseModel):
    id: str
    company: str
    ticker: str
    type: str
    status: AnalysisStatus
    progress: int
    started_at: str = Field(alias="startedAt")
    updated_at: str = Field(alias="updatedAt")
    analyst: str
    sector: str
    market_cap: str = Field(alias="marketCap")
    current_price: str = Field(alias="currentPrice")
    target_price: str = Field(alias="targetPrice")
    recommendation: Literal["Buy", "Hold", "Sell", "—"]
    overview: OverviewData
    workbook: WorkbookData
    verification: list[VerificationCheck] = Field(default_factory=list)
    decision_log: list[DecisionLogEntry] = Field(default_factory=list, alias="decisionLog")
    summary: SummaryData
    chat: list[ChatMessage] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class AnalysisListItem(BaseModel):
    id: str
    company: str
    ticker: str
    type: str
    status: AnalysisStatus
    progress: int
    started_at: str = Field(alias="startedAt")
    updated_at: str = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


class AnalysisStatusUpdate(BaseModel):
    status: AnalysisStatus | None = None
    progress: int | None = Field(default=None, ge=0, le=100)


class NewAnalysisForm(BaseModel):
    company_name: str
    ticker: str
    analysis_type: Literal["new_company", "annual_update", "quarterly_update"]
    notes: str = ""


class AnalysisCreateResponse(BaseModel):
    id: str
    message: str


class ChatMessageCreate(BaseModel):
    content: str
