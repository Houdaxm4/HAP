"""Canonical financial series primitives.

``FinancialPoint`` / ``FinancialSeries`` are the primary historical structures.
``PeriodAmount`` remains as a compatibility alias for ``FinancialPoint``.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Iterator, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

TrendDirection = Literal["up", "down", "flat", "insufficient"]


class LineItemProvenance(BaseModel):
    """Traceability metadata retained after workbook mapping.

    Analysis modules may cite this for evidence. They must not use it to
    re-query Excel workbooks.
    """

    concept: str | None = None
    cell_ref: str | None = None
    source_document: str | None = None
    xbrl_tag: str | None = None
    worksheet: str | None = None
    filing_type: str | None = None
    accession_number: str | None = None


class FinancialPoint(BaseModel):
    """One observed financial value in a historical series."""

    period: str
    value: float
    currency: str = "USD"
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    audited: bool = False
    provenance: LineItemProvenance | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_unit(cls, data: Any) -> Any:
        """Accept deprecated ``unit`` as an alias for ``currency``."""
        if isinstance(data, dict) and "currency" not in data and data.get("unit") is not None:
            payload = dict(data)
            payload["currency"] = payload.pop("unit")
            return payload
        return data

    @property
    def unit(self) -> str:
        """Backward-compatible alias for ``currency``."""
        return self.currency

    @property
    def concept(self) -> str | None:
        if self.provenance is None:
            return None
        return self.provenance.concept


# Backward-compatible name used by earlier callers / tests.
PeriodAmount = FinancialPoint


class FinancialSeries(BaseModel):
    """Ordered historical series for one financial concept."""

    name: str
    currency: str = "USD"
    points: list[FinancialPoint] = Field(default_factory=list)

    @field_validator("points")
    @classmethod
    def _sort_points(cls, points: list[FinancialPoint]) -> list[FinancialPoint]:
        return sorted(points, key=lambda point: point.period)

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self) -> Iterator[FinancialPoint]:
        return iter(self.sorted_points())

    def __bool__(self) -> bool:
        return bool(self.points)

    @property
    def is_empty(self) -> bool:
        return not self.points

    def sorted_points(self) -> list[FinancialPoint]:
        return sorted(self.points, key=lambda point: point.period)

    def latest(self) -> FinancialPoint | None:
        points = self.sorted_points()
        return points[-1] if points else None

    def value_for(self, period: str) -> float | None:
        for point in self.points:
            if point.period == period:
                return point.value
        return None

    def point_for(self, period: str) -> FinancialPoint | None:
        for point in self.points:
            if point.period == period:
                return point
        return None

    def periods(self) -> list[str]:
        return [point.period for point in self.sorted_points() if point.period]

    def values(self, *, window: int | None = None) -> list[float]:
        return [point.value for point in self.window_points(window)]

    def window_points(self, window: int | None = None) -> list[FinancialPoint]:
        points = self.sorted_points()
        if window is None or window <= 0:
            return points
        return points[-window:]

    def upsert(self, point: FinancialPoint) -> None:
        """Insert or replace the point for ``point.period``."""
        for index, existing in enumerate(self.points):
            if existing.period == point.period:
                self.points[index] = point
                break
        else:
            self.points.append(point)
        self.points = sorted(self.points, key=lambda item: item.period)
        if not self.currency and point.currency:
            self.currency = point.currency

    def average(self, window: int | None = 5) -> float | None:
        values = self.values(window=window)
        if not values:
            return None
        return sum(values) / len(values)

    def cagr(self, window: int | None = 5) -> float | None:
        """Compound annual growth rate across the selected window.

        Requires at least two points and a non-zero, same-sign start value.
        ``window`` counts points; years spanned = len(points) - 1.
        """
        points = self.window_points(window)
        if len(points) < 2:
            return None
        start = points[0].value
        end = points[-1].value
        years = len(points) - 1
        if start == 0 or years <= 0:
            return None
        if start < 0 or end < 0:
            # CAGR is undefined for sign changes / negative bases in this model.
            if start < 0 and end < 0:
                return (abs(end) / abs(start)) ** (1 / years) - 1
            return None
        return (end / start) ** (1 / years) - 1

    def stability(self, window: int | None = 5) -> float | None:
        """
        Stability score in ``[0, 1]`` based on coefficient of variation.

        ``1.0`` = perfectly stable; lower values indicate higher volatility.
        """
        values = self.values(window=window)
        if len(values) < 2:
            return None
        avg = sum(values) / len(values)
        if avg == 0:
            return 0.0
        variance = sum((value - avg) ** 2 for value in values) / len(values)
        cv = sqrt(variance) / abs(avg)
        return max(0.0, min(1.0, 1.0 / (1.0 + cv)))

    def trend_direction(self, window: int | None = 5) -> TrendDirection:
        values = self.values(window=window)
        if len(values) < 2:
            return "insufficient"
        start, end = values[0], values[-1]
        if start == 0:
            if end == 0:
                return "flat"
            return "up" if end > 0 else "down"
        change = (end - start) / abs(start)
        if abs(change) < 0.05:
            return "flat"
        return "up" if change > 0 else "down"

    def with_point(self, point: FinancialPoint) -> Self:
        clone = self.model_copy(deep=True)
        clone.upsert(point)
        return clone
