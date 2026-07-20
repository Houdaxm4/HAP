"""Run registered financial analysis modules and aggregate results."""

from __future__ import annotations

from analysis_engine.base import AnalysisModule
from analysis_engine.business_quality_aggregator import aggregate_business_quality
from analysis_engine.investment_attractiveness_aggregator import aggregate_investment_attractiveness
from analysis_engine.metric_comparison import extract_metric_comparisons
from analysis_engine.modules import DEFAULT_MODULES
from analysis_engine.modules.expected_return import ExpectedReturnModule
from analysis_engine.modules.recommendation import RecommendationModule, wrap_recommendation
from analysis_engine.modules.valuation import ValuationModule
from analysis_engine.recommendation_engine import generate_recommendation
from analysis_engine.schemas import AnalysisEngineResult, AnalysisModuleResult, MetricComparison
from analysis_engine.utils import clamp_confidence, mean
from analysis_engine.valuation_engine import ValuationComputeResult, compute_valuation
from canonical_model import CompanyFinancialModel


class AnalysisEngine:
    """Execute analysis modules against a CompanyFinancialModel only."""

    def __init__(self, modules: list[AnalysisModule] | None = None) -> None:
        if modules is None:
            self.modules = [module_cls() for module_cls in DEFAULT_MODULES]
        else:
            self.modules = list(modules)

    def run(self, model: CompanyFinancialModel) -> AnalysisEngineResult:
        module_results: list[AnalysisModuleResult] = []
        valuation_compute: ValuationComputeResult | None = None

        for module in self.modules:
            if isinstance(module, RecommendationModule):
                continue
            try:
                if isinstance(module, ValuationModule):
                    valuation_compute = compute_valuation(model)
                    result = module.analyze(model, valuation_compute=valuation_compute)
                elif isinstance(module, ExpectedReturnModule):
                    result = module.analyze(model, valuation_compute=valuation_compute)
                else:
                    result = module.analyze(model)
            except Exception as exc:  # noqa: BLE001 - isolate module failures
                result = AnalysisModuleResult(
                    module_name=getattr(module, "module_id", module.__class__.__name__),
                    module_version=getattr(module, "module_version", "1.0.0"),
                    status="error",
                    confidence=0.0,
                    error=str(exc),
                )
            module_results.append(result)

        business_quality = aggregate_business_quality(module_results)
        investment_attractiveness = aggregate_investment_attractiveness(module_results)
        recommendation = generate_recommendation(
            business_quality,
            investment_attractiveness,
            module_results,
        )
        module_results.append(
            wrap_recommendation(recommendation, business_quality, investment_attractiveness)
        )

        findings = [item for result in module_results for item in result.findings]
        metrics = [item for result in module_results for item in result.metrics]
        risks = [item for result in module_results for item in result.risks]
        opportunities = [item for result in module_results for item in result.opportunities]
        adjustments = [item for result in module_results for item in result.analyst_adjustments]
        ok_scores = [result.confidence for result in module_results if result.status == "ok"]
        metric_comparisons: list[MetricComparison] = [
            comparison
            for result in module_results
            for comparison in extract_metric_comparisons(result.coverage)
        ]

        return AnalysisEngineResult(
            analysis_id=model.analysis_id,
            ticker=model.ticker,
            modules=module_results,
            findings=findings,
            metrics=metrics,
            metric_comparisons=metric_comparisons,
            risks=risks,
            opportunities=opportunities,
            analyst_adjustments=adjustments,
            confidence=clamp_confidence(mean(ok_scores) or 0.0),
            business_quality=business_quality,
            investment_attractiveness=investment_attractiveness,
            recommendation=recommendation,
            summary_metrics={
                "module_count": len(module_results),
                "ok_count": sum(1 for result in module_results if result.status == "ok"),
                "skipped_count": sum(
                    1 for result in module_results if result.status == "skipped"
                ),
                "error_count": sum(1 for result in module_results if result.status == "error"),
                "finding_count": len(findings),
                "metric_count": len(metrics),
                "metric_comparison_count": len(metric_comparisons),
                "divergent_metric_count": sum(
                    1 for item in metric_comparisons if item.status == "divergent"
                ),
                "scored_module_count": sum(
                    1 for result in module_results if result.score is not None
                ),
                "business_quality_score": business_quality.score,
                "investment_attractiveness_score": investment_attractiveness.score,
                "recommendation": recommendation.recommendation,
            },
        )
