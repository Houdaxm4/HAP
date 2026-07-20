"""Rule definition primitives for the HAP Rule Library."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from analysis_engine.schemas import Evidence, Finding, FindingDirection, FindingSeverity

RuleSeverity = Literal["INFO", "POSITIVE", "WARNING", "CRITICAL"]


_SEVERITY_MAP: dict[RuleSeverity, FindingSeverity] = {
    "INFO": "info",
    "POSITIVE": "positive",
    "WARNING": "warning",
    "CRITICAL": "critical",
}

_DIRECTION_MAP: dict[RuleSeverity, FindingDirection] = {
    "INFO": "neutral",
    "POSITIVE": "positive",
    "WARNING": "negative",
    "CRITICAL": "negative",
}


class RuleDefinition(BaseModel):
    """Deterministic rule metadata (docs/RULE_LIBRARY.md)."""

    rule_id: str
    category: str
    severity: RuleSeverity
    finding: str
    explanation: str
    suggested_analyst_action: str | None = None


class RuleHit(BaseModel):
    """A triggered rule with evidence — never a recommendation."""

    rule: RuleDefinition
    trigger_metrics: dict[str, float | None] = Field(default_factory=dict)
    periods: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)

    def to_finding(self) -> Finding:
        return Finding(
            finding_id=f"rule:{self.rule.rule_id}",
            code=self.rule.finding.upper().replace(" ", "_"),
            rule_id=self.rule.rule_id,
            severity=_SEVERITY_MAP[self.rule.severity],
            direction=_DIRECTION_MAP[self.rule.severity],
            category=self.rule.category,
            summary=self.rule.finding,
            periods=self.periods,
            metrics=self.trigger_metrics,
            evidence=self.evidence,
            confidence=self.confidence,
            suggested_analyst_action=self.rule.suggested_analyst_action,
        )


def evidence_from_metric(
    *,
    metric: str,
    value: float | None,
    period: str | None,
    source: str | None = None,
    confidence: float | None = None,
    details: dict[str, Any] | None = None,
) -> Evidence:
    return Evidence(
        kind="rule_trigger",
        label=f"{metric} trigger",
        metric=metric,
        concept=metric,
        period=period,
        value=value,
        source=source,
        confidence=confidence,
        details=details or {},
    )
