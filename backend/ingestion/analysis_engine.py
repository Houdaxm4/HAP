"""Analysis engine entry point — ingestion hands off here."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ingestion.models.company_financial_model import CompanyFinancialModel
from models.common import utc_now_iso


class AnalysisEngineResult(BaseModel):
    """Result of invoking AnalysisEngine.run()."""

    status: str
    message: str
    ticker: str
    analysis_id: str
    started_at: str = Field(default_factory=utc_now_iso)
    sec_fact_count: int = 0
    proprietary_metric_count: int = 0
    historical_metric_count: int = 0


class AnalysisEngine:
    """
    HAP analysis engine entry point.

    Sprint 5 only wires ingestion → AnalysisEngine.run().
    Investment methodology, scoring, and recommendation logic are unchanged
    and will be implemented in subsequent sprints.
    """

    def run(self, model: CompanyFinancialModel) -> AnalysisEngineResult:
        return AnalysisEngineResult(
            status="accepted",
            message=(
                "Ingestion complete. CompanyFinancialModel accepted by AnalysisEngine. "
                "Investment analysis stages are not yet implemented."
            ),
            ticker=model.ticker,
            analysis_id=model.analysis_id,
            sec_fact_count=len(model.sec_statement_values),
            proprietary_metric_count=len(model.proprietary_metrics),
            historical_metric_count=len(model.historical_metrics),
        )
