"""Assemble the canonical CompanyFinancialModel from ingestion inputs."""

from __future__ import annotations

from typing import Any

from ingestion.models.company_financial_model import CompanyFinancialModel, SecStatementValue
from ingestion.models.custom_run_data import CustomRunData, MetricSeries
from services.sec_service import CONCEPT_TO_XBRL, SecService


class CompanyFinancialModelBuilder:
    """
    Merge SEC statement facts, CustomRunData, and market data into one model.

    SEC remains authoritative for financial statement line items.
  Custom_Run provides proprietary analytics and historical metrics.
    """

    def __init__(self, sec_service: SecService | None = None) -> None:
        self.sec_service = sec_service or SecService()

    def build(
        self,
        *,
        analysis_id: str,
        ticker: str,
        custom_run: CustomRunData,
        company_facts: dict[str, Any],
        filings_manifest: dict[str, Any],
        cik: str | None = None,
    ) -> CompanyFinancialModel:
        sec_values = self._extract_sec_statement_values(custom_run, company_facts)

        return CompanyFinancialModel(
            analysis_id=analysis_id,
            ticker=ticker.upper(),
            company_name=custom_run.company_name or ticker.upper(),
            cik=cik or filings_manifest.get("cik"),
            custom_run=custom_run,
            sec_filings_manifest=filings_manifest,
            sec_statement_values=sec_values,
            market_data=dict(custom_run.market_data),
            historical_metrics=self._series_to_dict(custom_run.historical_metrics),
            proprietary_metrics=self._series_to_dict(custom_run.proprietary_metrics),
            valuation_metrics=self._series_to_dict(custom_run.valuation_metrics),
            quality_metrics={
                series.metric: series.values.get("current")
                for series in custom_run.quality_metrics
            },
            assumptions=dict(custom_run.assumptions),
        )

    def _extract_sec_statement_values(
        self,
        custom_run: CustomRunData,
        company_facts: dict[str, Any],
    ) -> list[SecStatementValue]:
        """Source SEC facts for concepts referenced in historical metrics."""
        values: list[SecStatementValue] = []
        seen: set[tuple[str, str]] = set()

        for series in custom_run.historical_metrics:
            concept_key = series.metric.strip().lower()
            if concept_key not in CONCEPT_TO_XBRL and not series.metric:
                continue
            for period, _ in series.values.items():
                if period == "current" or (period, series.metric) in seen:
                    continue
                fact = self.sec_service.find_fact(company_facts, series.metric, period)
                if fact is None:
                    continue
                seen.add((period, series.metric))
                values.append(
                    SecStatementValue(
                        concept=series.metric,
                        period=period,
                        value=fact.value,
                        xbrl_tag=f"{fact.taxonomy}:{fact.tag}",
                        taxonomy=fact.taxonomy,
                        form=fact.form,
                        filed=fact.filed,
                        accession_number=fact.accession_number,
                        unit=fact.unit,
                    )
                )
        return values

    @staticmethod
    def _series_to_dict(
        series_list: list[MetricSeries],
    ) -> dict[str, dict[str, float | str | None]]:
        return {series.metric: dict(series.values) for series in series_list}
