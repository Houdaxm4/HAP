"""Stage: build canonical CompanyFinancialModel from ingestion inputs."""

from __future__ import annotations

from typing import Any

from ingestion.company_financial_model_builder import CompanyFinancialModelBuilder
from ingestion.models.company_financial_model import CompanyFinancialModel
from ingestion.models.custom_run_data import CustomRunData
from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from services.output_service import OutputService


class BuildFinancialModelStage:
    """Merge SEC facts, CustomRunData, and market data into CompanyFinancialModel."""

    def __init__(
        self,
        builder: CompanyFinancialModelBuilder | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.builder = builder or CompanyFinancialModelBuilder()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_data: CustomRunData,
        company_facts: dict[str, Any],
        filings_manifest: dict[str, Any],
    ) -> tuple[CompanyFinancialModel, str, DecisionLogEntry]:
        model = self.builder.build(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            custom_run=custom_run_data,
            company_facts=company_facts,
            filings_manifest=filings_manifest,
            cik=analysis.cik,
        )
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "company_financial_model.json",
            model,
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="build_financial_model",
            detail=(
                f"Built CompanyFinancialModel for {model.ticker}: "
                f"{len(model.sec_statement_values)} SEC facts, "
                f"{len(model.proprietary_metrics)} proprietary metrics."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return model, artifact_path, log_entry
