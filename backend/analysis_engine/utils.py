"""Numeric helpers shared by analysis modules."""

from __future__ import annotations

from analysis_engine.schemas import Evidence
from canonical_model import FinancialPoint, FinancialSeries


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def latest_point(series: FinancialSeries | list[FinancialPoint]) -> FinancialPoint | None:
    if isinstance(series, FinancialSeries):
        return series.latest()
    if not series:
        return None
    return sorted(series, key=lambda item: item.period)[-1]


# Backward-compatible alias.
latest_amount = latest_point


def point_evidence(point: FinancialPoint, *, label: str | None = None) -> Evidence:
    provenance = point.provenance
    return Evidence(
        kind="financial_fact",
        label=label or f"{point.concept or 'amount'} ({point.period})",
        metric=point.concept,
        concept=point.concept,
        period=point.period,
        value=point.value,
        unit=point.currency,
        source=point.source,
        cell_ref=provenance.cell_ref if provenance else None,
        source_document=point.source or (provenance.source_document if provenance else None),
        confidence=point.confidence,
        provenance={
            "xbrl_tag": provenance.xbrl_tag if provenance else None,
            "audited": point.audited,
            "cell_ref": provenance.cell_ref if provenance else None,
        },
        details={
            "xbrl_tag": provenance.xbrl_tag if provenance else None,
            "audited": point.audited,
            "currency": point.currency,
        },
    )


# Backward-compatible alias.
amount_evidence = point_evidence


def paired_periods(*series_list: FinancialSeries | list[FinancialPoint]) -> list[str]:
    if not series_list:
        return []
    period_sets: list[set[str]] = []
    for series in series_list:
        if isinstance(series, FinancialSeries):
            period_sets.append(set(series.periods()))
        else:
            period_sets.append({item.period for item in series if item.period})
    if not period_sets:
        return []
    return sorted(set.intersection(*period_sets))


def yoy_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior)


def ratio_series(
    *,
    name: str,
    numerator: FinancialSeries,
    denominator: FinancialSeries,
    currency: str = "ratio",
) -> FinancialSeries:
    """Build a derived ratio series over intersecting periods."""
    series = FinancialSeries(name=name, currency=currency)
    for period in paired_periods(numerator, denominator):
        num = numerator.point_for(period)
        den = denominator.point_for(period)
        if num is None or den is None or den.value == 0:
            continue
        confidence_values = [c for c in (num.confidence, den.confidence) if c is not None]
        series.upsert(
            FinancialPoint(
                period=period,
                value=num.value / den.value,
                currency=currency,
                source="derived",
                confidence=mean(confidence_values),
                audited=bool(num.audited and den.audited),
                provenance=num.provenance,
            )
        )
    return series
