"""Workbook Metrics — analyst-calculated ratios and formulas from the workbook.

Workbook Metrics are read-only inputs to HAP. They are never overwritten by
analysis modules and are kept separate from statement facts and HAP Metrics.
"""

from __future__ import annotations

from typing import Iterator

from pydantic import BaseModel, Field

from canonical_model.primitives import LineItemProvenance


class WorkbookMetric(BaseModel):
    """
  Analyst-owned value from the workbook (typically a formula cell).

  HAP ingests these for comparison only. Modules must not mutate or replace them.
  """

    code: str
    name: str
    value: float
    period: str | None = None
    unit: str | None = "ratio"
    is_formula: bool = True
    cell_ref: str | None = None
    formula: str | None = None
    source: str | None = "workbook"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    module_hint: str | None = None
    provenance: LineItemProvenance | None = None


class WorkbookMetricCatalog(BaseModel):
    """Indexed collection of workbook metrics attached to a CompanyFinancialModel."""

    metrics: list[WorkbookMetric] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.metrics)

    def __iter__(self) -> Iterator[WorkbookMetric]:
        return iter(self.metrics)

    @property
    def is_empty(self) -> bool:
        return not self.metrics

    def add(self, metric: WorkbookMetric) -> None:
        """Insert or replace a metric for the same code + period."""
        for index, existing in enumerate(self.metrics):
            if (
                existing.code == metric.code
                and existing.period == metric.period
            ):
                self.metrics[index] = metric
                return
        self.metrics.append(metric)

    def get(self, code: str, *, period: str | None = None) -> WorkbookMetric | None:
        code_key = code.upper()
        matches = [item for item in self.metrics if item.code.upper() == code_key]
        if not matches:
            return None
        if period is None:
            with_period = [item for item in matches if item.period]
            if with_period:
                return sorted(with_period, key=lambda item: item.period or "")[-1]
            return matches[0]
        for item in matches:
            if item.period == period:
                return item
        return None

    def for_code(self, code: str) -> list[WorkbookMetric]:
        code_key = code.upper()
        return sorted(
            [item for item in self.metrics if item.code.upper() == code_key],
            key=lambda item: item.period or "",
        )

    def codes(self) -> list[str]:
        return sorted({item.code.upper() for item in self.metrics})
