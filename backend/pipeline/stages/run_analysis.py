"""Stage: invoke AnalysisEngine after ingestion completes."""

from __future__ import annotations

from ingestion.analysis_engine import AnalysisEngine, AnalysisEngineResult
from ingestion.models.company_financial_model import CompanyFinancialModel
from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from services.output_service import OutputService


class RunAnalysisStage:
    """Hand off the assembled CompanyFinancialModel to AnalysisEngine.run()."""

    def __init__(
        self,
        engine: AnalysisEngine | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.engine = engine or AnalysisEngine()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        financial_model: CompanyFinancialModel,
    ) -> tuple[AnalysisEngineResult, str, DecisionLogEntry]:
        result = self.engine.run(financial_model)
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "analysis_engine_result.json",
            result,
        )
        log_entry = DecisionLogEntry(
            agent="Pipeline Orchestrator",
            action="run_analysis",
            detail=result.message,
            confidence=1.0,
            citations=[artifact_path],
        )
        return result, artifact_path, log_entry
