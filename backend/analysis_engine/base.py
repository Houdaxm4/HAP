"""Base interface for HAP financial analysis modules."""

from __future__ import annotations

from abc import ABC, abstractmethod

from analysis_engine.metric_comparison import ModuleMetricComparisons, build_module_metric_comparisons
from analysis_engine.schemas import AnalysisModuleResult, MetricResult
from canonical_model import CompanyFinancialModel


class AnalysisModule(ABC):
    """
    One financial analysis concern only.

    Implementations must accept a ``CompanyFinancialModel`` and return structured
    Pydantic results. They must not load Excel files, read workbook cells, or
    write narrative reports.

    Modules compute **HAP Metrics** independently from statement facts. When
    equivalent **Workbook Metrics** exist on the model, attach comparisons under
    ``coverage[\"metric_comparisons\"]`` — never overwrite workbook formulas.
    """

    module_id: str
    module_version: str = "1.0.0"

    @abstractmethod
    def analyze(self, model: CompanyFinancialModel) -> AnalysisModuleResult:
        """Run this module against the canonical company financial model."""

    def build_metric_comparisons(
        self,
        model: CompanyFinancialModel,
        hap_metrics: list[MetricResult],
        *,
        period: str | None = None,
        code_map: dict[str, str] | None = None,
    ) -> ModuleMetricComparisons:
        """Compare HAP metrics to workbook equivalents when present."""
        return build_module_metric_comparisons(
            model=model,
            module_name=self.module_id,
            hap_metrics=hap_metrics,
            period=period,
            code_map=code_map,
        )
