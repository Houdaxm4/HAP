"""Profitability rules PR001–PR010 from docs/RULE_LIBRARY.md."""

from __future__ import annotations

from analysis_engine.schemas import Evidence
from canonical_model import FinancialSeries
from rule_library.base import RuleDefinition, RuleHit, evidence_from_metric

NET_MARGIN_VOLATILITY_THRESHOLD = 0.35  # CV threshold for PR008


PROFITABILITY_RULES: dict[str, RuleDefinition] = {
    "PR001": RuleDefinition(
        rule_id="PR001",
        category="profitability",
        severity="POSITIVE",
        finding="Exceptional Capital Efficiency",
        explanation=(
            "The company generates returns on invested capital significantly "
            "above typical corporate cost of capital."
        ),
        suggested_analyst_action="None.",
    ),
    "PR002": RuleDefinition(
        rule_id="PR002",
        category="profitability",
        severity="POSITIVE",
        finding="Excellent Capital Efficiency",
        explanation="ROIC between 15% and 20%.",
        suggested_analyst_action="None.",
    ),
    "PR003": RuleDefinition(
        rule_id="PR003",
        category="profitability",
        severity="INFO",
        finding="Healthy Returns",
        explanation="ROIC between 10% and 15%.",
        suggested_analyst_action="None.",
    ),
    "PR004": RuleDefinition(
        rule_id="PR004",
        category="profitability",
        severity="CRITICAL",
        finding="Economic Value Destruction",
        explanation="ROIC below WACC.",
        suggested_analyst_action="Investigate competitive position and capital allocation.",
    ),
    "PR005": RuleDefinition(
        rule_id="PR005",
        category="profitability",
        severity="WARNING",
        finding="Deteriorating Capital Efficiency",
        explanation="ROIC declining for five consecutive years.",
        suggested_analyst_action="Review competitive position and reinvestment returns.",
    ),
    "PR006": RuleDefinition(
        rule_id="PR006",
        category="profitability",
        severity="POSITIVE",
        finding="Improving Operating Efficiency",
        explanation="Operating Margin increasing five years.",
        suggested_analyst_action="None.",
    ),
    "PR007": RuleDefinition(
        rule_id="PR007",
        category="profitability",
        severity="WARNING",
        finding="Margin Compression",
        explanation="Operating Margin declining five years.",
        suggested_analyst_action="Investigate cost structure and pricing power.",
    ),
    "PR008": RuleDefinition(
        rule_id="PR008",
        category="profitability",
        severity="WARNING",
        finding="Unstable Profitability",
        explanation="Net Margin volatility exceeds threshold.",
        suggested_analyst_action="Normalize one-time items and review earnings quality.",
    ),
    "PR009": RuleDefinition(
        rule_id="PR009",
        category="profitability",
        severity="POSITIVE",
        finding="Excellent Shareholder Returns",
        explanation="ROE > 20%.",
        suggested_analyst_action="None.",
    ),
    "PR010": RuleDefinition(
        rule_id="PR010",
        category="profitability",
        severity="POSITIVE",
        finding="Improving Asset Utilization",
        explanation="ROA consistently increasing.",
        suggested_analyst_action="None.",
    ),
}


def evaluate_profitability_rules(
    *,
    roic: float | None,
    roe: float | None,
    roa_series: FinancialSeries | None,
    roic_series: FinancialSeries | None,
    operating_margin_series: FinancialSeries | None,
    net_margin_series: FinancialSeries | None,
    wacc: float | None,
    period: str | None,
    evidence_by_metric: dict[str, list[Evidence]] | None = None,
) -> list[RuleHit]:
    """Evaluate PR001–PR010 against computed profitability metrics."""
    hits: list[RuleHit] = []
    bag = evidence_by_metric or {}

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in bag and bag[metric]:
            return list(bag[metric])
        return [
            evidence_from_metric(
                metric=metric,
                value=value,
                period=period,
                confidence=0.85,
            )
        ]

    if roic is not None:
        if roic > 0.20:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR001"],
                    trigger_metrics={"ROIC": roic},
                    periods=[period] if period else [],
                    evidence=_ev("ROIC", roic),
                )
            )
        elif 0.15 <= roic <= 0.20:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR002"],
                    trigger_metrics={"ROIC": roic},
                    periods=[period] if period else [],
                    evidence=_ev("ROIC", roic),
                )
            )
        elif 0.10 <= roic < 0.15:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR003"],
                    trigger_metrics={"ROIC": roic},
                    periods=[period] if period else [],
                    evidence=_ev("ROIC", roic),
                )
            )
        if wacc is not None and roic < wacc:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR004"],
                    trigger_metrics={"ROIC": roic, "WACC": wacc},
                    periods=[period] if period else [],
                    evidence=_ev("ROIC", roic)
                    + evidence_from_metric(metric="WACC", value=wacc, period=period),
                )
            )

    if roic_series is not None and _strictly_declining(roic_series, years=5):
        hits.append(
            RuleHit(
                rule=PROFITABILITY_RULES["PR005"],
                trigger_metrics={"ROIC_POINTS": float(len(roic_series.window_points(5)))},
                periods=roic_series.periods()[-5:],
                evidence=_ev("ROIC", roic_series.latest().value if roic_series.latest() else None),
            )
        )

    if operating_margin_series is not None:
        if _strictly_increasing(operating_margin_series, years=5):
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR006"],
                    trigger_metrics={
                        "OPERATING_MARGIN": operating_margin_series.latest().value
                        if operating_margin_series.latest()
                        else None
                    },
                    periods=operating_margin_series.periods()[-5:],
                    evidence=_ev(
                        "OPERATING_MARGIN",
                        operating_margin_series.latest().value
                        if operating_margin_series.latest()
                        else None,
                    ),
                )
            )
        if _strictly_declining(operating_margin_series, years=5):
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR007"],
                    trigger_metrics={
                        "OPERATING_MARGIN": operating_margin_series.latest().value
                        if operating_margin_series.latest()
                        else None
                    },
                    periods=operating_margin_series.periods()[-5:],
                    evidence=_ev(
                        "OPERATING_MARGIN",
                        operating_margin_series.latest().value
                        if operating_margin_series.latest()
                        else None,
                    ),
                )
            )

    if net_margin_series is not None and len(net_margin_series) >= 3:
        cv = _coefficient_of_variation(net_margin_series.values(window=5))
        if cv is not None and cv > NET_MARGIN_VOLATILITY_THRESHOLD:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR008"],
                    trigger_metrics={"NET_MARGIN_CV": cv},
                    periods=net_margin_series.periods()[-5:],
                    evidence=_ev("NET_MARGIN_CV", cv),
                )
            )

    if roe is not None and roe > 0.20:
        hits.append(
            RuleHit(
                rule=PROFITABILITY_RULES["PR009"],
                trigger_metrics={"ROE": roe},
                periods=[period] if period else [],
                evidence=_ev("ROE", roe),
            )
        )

    if roa_series is not None and _strictly_increasing(roa_series, years=None):
        # "consistently increasing" — require at least 3 points, all steps up.
        if len(roa_series) >= 3:
            hits.append(
                RuleHit(
                    rule=PROFITABILITY_RULES["PR010"],
                    trigger_metrics={
                        "ROA": roa_series.latest().value if roa_series.latest() else None
                    },
                    periods=roa_series.periods(),
                    evidence=_ev(
                        "ROA",
                        roa_series.latest().value if roa_series.latest() else None,
                    ),
                )
            )

    return hits


def _strictly_declining(series: FinancialSeries, years: int | None) -> bool:
    points = series.window_points(years) if years else series.sorted_points()
    if years is not None and len(points) < years:
        return False
    if len(points) < 2:
        return False
    values = [point.value for point in points]
    return all(values[i] > values[i + 1] for i in range(len(values) - 1))


def _strictly_increasing(series: FinancialSeries, years: int | None) -> bool:
    points = series.window_points(years) if years else series.sorted_points()
    if years is not None and len(points) < years:
        return False
    if len(points) < 2:
        return False
    values = [point.value for point in points]
    return all(values[i] < values[i + 1] for i in range(len(values) - 1))


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    if avg == 0:
        return None
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return (variance**0.5) / abs(avg)
