"""Stage: build CompanyFinancialModel and run the AnalysisEngine."""

from __future__ import annotations

from typing import Any

from analysis_engine.runner import AnalysisEngine
from analysis_engine.schemas import AnalysisEngineResult
from canonical_model import CompanyFinancialModel, build_company_financial_model
from models.analysis import Analysis
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.provenance import ProvenanceReport
from models.validation import DiscrepancyReport
from services.hap_workbook_service import HapWorkbookService
from services.output_service import OutputService

ENGINE_VERSION = "0.3.0"


class RunAnalysisStage:
    """
    Build the canonical financial model from SEC + CustomRunData and run
    the AnalysisEngine. Does not modify analytical methodology.
    """

    def __init__(
        self,
        output_service: OutputService | None = None,
        analysis_engine: AnalysisEngine | None = None,
        hap_workbook_service: HapWorkbookService | None = None,
    ) -> None:
        self.output_service = output_service or OutputService()
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.hap_workbook_service = hap_workbook_service or HapWorkbookService()

    def run(
        self,
        analysis: Analysis,
        provenance_report: ProvenanceReport,
        discrepancy_report: DiscrepancyReport,
        custom_run: CustomRunData,
        company_facts: dict[str, Any],
    ) -> tuple[CompanyFinancialModel, AnalysisEngineResult, str, str, str, DecisionLogEntry]:
        model = build_company_financial_model(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            company=analysis.company or custom_run.company,
            analysis_type=analysis.analysis_type,
            provenance_report=provenance_report,
            discrepancy_report=discrepancy_report,
            company_facts=company_facts,
            custom_run=custom_run,
            metadata={
                "ingestion": "hap_v1_sec_plus_custom_run",
                "custom_run_source": custom_run.source_filename,
            },
        )

        # Default terminal growth when DCF would otherwise skip (assumption registry).
        if model.valuation_inputs.terminal_growth_rate is None and model.valuation_inputs.wacc:
            model.valuation_inputs.terminal_growth_rate = 0.03
            model.metadata["terminal_growth_defaulted"] = True

        engine_result = self.analysis_engine.run(model)

        model_path = self.output_service.write_json(
            analysis.analysis_id,
            "company_financial_model.json",
            model,
        )
        result_path = self.output_service.write_json(
            analysis.analysis_id,
            "analysis_engine_result.json",
            engine_result,
        )

        hap_workbook_path = self.output_service.artifact_path(
            analysis.analysis_id,
            "hap_workbook.xlsx",
        )
        self.hap_workbook_service.write(
            hap_workbook_path,
            analysis=analysis,
            model=model,
            engine_result=engine_result,
            custom_run=custom_run,
            validation_report=discrepancy_report,
            provenance_report=provenance_report,
            engine_version=ENGINE_VERSION,
        )
        hap_workbook_rel = self.output_service.relative_path(
            analysis.analysis_id,
            "hap_workbook.xlsx",
        )

        recommendation = (
            engine_result.recommendation.recommendation
            if engine_result.recommendation is not None
            else "INSUFFICIENT_DATA"
        )
        bq_score = (
            engine_result.business_quality.score
            if engine_result.business_quality is not None
            else None
        )
        ia_score = (
            engine_result.investment_attractiveness.score
            if engine_result.investment_attractiveness is not None
            else None
        )

        log_entry = DecisionLogEntry(
            agent="Analysis Engine",
            action="run_analysis",
            detail=(
                f"AnalysisEngine completed for {analysis.ticker}: "
                f"BQ={bq_score}, IA={ia_score}, recommendation={recommendation}. "
                f"HAP workbook written."
            ),
            confidence=engine_result.confidence,
            citations=[model_path, result_path, hap_workbook_rel],
        )
        return model, engine_result, model_path, result_path, hap_workbook_rel, log_entry
