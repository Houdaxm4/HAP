"""Workbook Metric vs HAP Metric comparison utilities."""

from __future__ import annotations

from typing import Any

from analysis_engine.schemas import (
    ComparisonRecommendedAction,
    ComparisonStatus,
    HAPMetric,
    MetricComparison,
    MetricResult,
    ModuleMetricComparisons,
    ToleranceMode,
)
from canonical_model.workbook_metrics import WorkbookMetric, WorkbookMetricCatalog

DEFAULT_RATIO_TOLERANCE = 0.005
DEFAULT_SCORE_TOLERANCE = 0.02
DEFAULT_COUNT_TOLERANCE = 0.0

DEFAULT_HAP_TO_WORKBOOK_CODE: dict[str, str] = {
    "ROIC": "ROIC",
    "ROE": "ROE",
    "ROA": "ROA",
    "GROSS_MARGIN": "GROSS_MARGIN",
    "OPERATING_MARGIN": "OPERATING_MARGIN",
    "EBIT_MARGIN": "OPERATING_MARGIN",
    "NET_MARGIN": "NET_MARGIN",
    "REV_CAGR": "REV_CAGR",
    "EPS_CAGR": "EPS_CAGR",
    "FCF_CAGR": "FCF_CAGR",
    "OI_CAGR": "OI_CAGR",
    "BV_CAGR": "BV_CAGR",
    "REV_YOY": "REV_YOY",
    "GROWTH_STABILITY": "GROWTH_STABILITY",
    "ORGANIC_REV_CAGR": "ORGANIC_REV_CAGR",
    "FCF_MARGIN": "FCF_MARGIN",
    "CASH_CONVERSION": "CASH_CONVERSION",
    "OWNER_EARNINGS": "OWNER_EARNINGS",
    "CURRENT_RATIO": "CURRENT_RATIO",
    "QUICK_RATIO": "QUICK_RATIO",
    "DEBT_TO_EQUITY": "DEBT_TO_EQUITY",
    "DEBT_TO_EBITDA": "DEBT_TO_EBITDA",
    "INTEREST_COVERAGE": "INTEREST_COVERAGE",
    "INTRINSIC_VALUE": "INTRINSIC_VALUE",
    "MARGIN_OF_SAFETY": "MARGIN_OF_SAFETY",
    "EXPECTED_IRR": "EXPECTED_IRR",
    "EXPECTED_CAGR": "EXPECTED_CAGR",
}


class MetricComparisonCapable:
    """
    Optional interface for modules that compare Workbook vs HAP metrics.

    Future modules (Cash Flow, Balance Sheet, Capital Allocation, Valuation,
    Expected Return) should implement ``build_metric_comparisons``.
    """

    def build_metric_comparisons(
        self,
        model: Any,
        hap_metrics: list[MetricResult],
        *,
        period: str | None = None,
        code_map: dict[str, str] | None = None,
    ) -> ModuleMetricComparisons:
        module_name = getattr(self, "module_id", self.__class__.__name__)
        return build_module_metric_comparisons(
            model=model,
            module_name=module_name,
            hap_metrics=hap_metrics,
            period=period,
            code_map=code_map,
        )


def default_tolerance(*, unit: str | None) -> tuple[float, ToleranceMode]:
    if unit in {"score", "direction", "flag"}:
        return DEFAULT_SCORE_TOLERANCE, "absolute"
    if unit in {"count"}:
        return DEFAULT_COUNT_TOLERANCE, "absolute"
    return DEFAULT_RATIO_TOLERANCE, "absolute"


def compare_workbook_to_hap(
    *,
    comparison_id: str,
    metric_code: str,
    metric_name: str,
    module_name: str,
    workbook: WorkbookMetric | None,
    hap: HAPMetric | MetricResult | None,
    period: str | None = None,
    unit: str | None = None,
    tolerance: float | None = None,
    tolerance_mode: ToleranceMode | None = None,
) -> MetricComparison:
    """Compare one workbook metric to one HAP metric and classify the result."""
    workbook_value = workbook.value if workbook is not None else None
    hap_value: float | None = None
    hap_evidence: list = []
    hap_confidence = 0.85

    if isinstance(hap, MetricResult):
        hap_value = hap.value
        hap_evidence = list(hap.evidence)
        hap_confidence = hap.confidence
        unit = unit or hap.unit
        period = period or hap.period
        metric_name = metric_name or hap.name
    elif isinstance(hap, HAPMetric):
        hap_value = hap.value
        hap_evidence = list(hap.evidence)
        hap_confidence = hap.confidence
        unit = unit or hap.unit
        period = period or hap.period

    if workbook is not None:
        unit = unit or workbook.unit
        period = period or workbook.period

    tol, mode = default_tolerance(unit=unit)
    if tolerance is not None:
        tol = tolerance
    if tolerance_mode is not None:
        mode = tolerance_mode

    difference: float | None = None
    relative_difference: float | None = None
    status: ComparisonStatus
    recommended_action: ComparisonRecommendedAction

    if workbook_value is None and hap_value is None:
        status = "not_comparable"
        recommended_action = "not_applicable"
    elif workbook_value is None:
        status = "hap_only"
        recommended_action = "no_action"
    elif hap_value is None:
        status = "workbook_only"
        recommended_action = "accept_workbook_value"
    else:
        difference = hap_value - workbook_value
        if workbook_value != 0:
            relative_difference = difference / abs(workbook_value)
        if _values_match(workbook_value, hap_value, tolerance=tol, mode=mode):
            status = "match" if difference == 0 else "within_tolerance"
            recommended_action = "no_action"
        else:
            status = "divergent"
            if workbook is not None and workbook.is_formula:
                recommended_action = "investigate_workbook_formula"
            elif relative_difference is not None and abs(relative_difference) > 0.10:
                recommended_action = "request_analyst_review"
            else:
                recommended_action = "reconcile_inputs"

    hap_metric = None
    if hap_value is not None:
        hap_metric = HAPMetric(
            code=metric_code,
            name=metric_name,
            value=hap_value,
            unit=unit,
            period=period,
            module_name=module_name,
            confidence=hap_confidence,
            evidence=hap_evidence,
        )

    return MetricComparison(
        comparison_id=comparison_id,
        metric_code=metric_code,
        metric_name=metric_name,
        module_name=module_name,
        period=period,
        unit=unit,
        workbook_value=workbook_value,
        hap_value=hap_value,
        difference=difference,
        relative_difference=relative_difference,
        tolerance=tol,
        tolerance_mode=mode,
        status=status,
        recommended_action=recommended_action,
        workbook_metric=workbook.model_dump() if workbook is not None else None,
        hap_metric=hap_metric,
    )


def build_module_metric_comparisons(
    *,
    model: Any,
    module_name: str,
    hap_metrics: list[MetricResult],
    period: str | None = None,
    code_map: dict[str, str] | None = None,
    tolerance_overrides: dict[str, float] | None = None,
) -> ModuleMetricComparisons:
    """Compare a module's HAP metrics against workbook equivalents when present."""
    catalog: WorkbookMetricCatalog = getattr(
        model, "workbook_metrics", WorkbookMetricCatalog()
    )
    mapping = {**DEFAULT_HAP_TO_WORKBOOK_CODE, **(code_map or {})}
    comparisons: list[MetricComparison] = []

    for hap_metric in hap_metrics:
        workbook_code = mapping.get(hap_metric.code.upper(), hap_metric.code.upper())
        target_period = period or hap_metric.period
        workbook_metric = catalog.get(workbook_code, period=target_period)
        tolerance = (tolerance_overrides or {}).get(hap_metric.code.upper())
        comparisons.append(
            compare_workbook_to_hap(
                comparison_id=f"{module_name}:cmp:{hap_metric.code}:{target_period or 'latest'}",
                metric_code=hap_metric.code,
                metric_name=hap_metric.name,
                module_name=module_name,
                workbook=workbook_metric,
                hap=hap_metric,
                period=target_period,
                tolerance=tolerance,
            )
        )

    divergent = sum(1 for item in comparisons if item.status == "divergent")
    return ModuleMetricComparisons(
        comparisons=comparisons,
        workbook_metric_count=sum(
            1 for item in comparisons if item.workbook_value is not None
        ),
        hap_metric_count=sum(1 for item in comparisons if item.hap_value is not None),
        divergent_count=divergent,
    )


def attach_metric_comparisons(
    coverage: dict[str, Any],
    comparison_bundle: ModuleMetricComparisons,
) -> dict[str, Any]:
    """Attach comparisons to module ``coverage`` without changing core result fields."""
    updated = dict(coverage)
    updated["metric_comparisons"] = comparison_bundle.model_dump()
    return updated


def extract_metric_comparisons(coverage: dict[str, Any]) -> list[MetricComparison]:
    """Read comparisons from a module result's ``coverage`` extension."""
    raw = coverage.get("metric_comparisons")
    if raw is None:
        return []
    if isinstance(raw, ModuleMetricComparisons):
        return list(raw.comparisons)
    if isinstance(raw, dict):
        bundle = ModuleMetricComparisons.model_validate(raw)
        return list(bundle.comparisons)
    return []


def _values_match(
    workbook_value: float,
    hap_value: float,
    *,
    tolerance: float,
    mode: ToleranceMode,
) -> bool:
    difference = abs(hap_value - workbook_value)
    if mode == "relative":
        if workbook_value == 0:
            return difference <= tolerance
        return difference / abs(workbook_value) <= tolerance
    return difference <= tolerance
