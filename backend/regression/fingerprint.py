"""Compact, stable summaries of analysis results used for regression comparison."""

from __future__ import annotations

from typing import Any

FLOAT_DIGITS = 6


def _round(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def _pick(source: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    source = source or {}
    return {k: source.get(k) for k in keys}


def engine_fingerprint(engine: dict[str, Any]) -> dict[str, Any]:
    modules = {}
    for module in engine.get("modules", []):
        modules[module.get("module_name", "?")] = _pick(module, ("status", "score", "confidence"))
    findings = sorted(
        f"{f.get('code')}|{f.get('severity')}|{f.get('direction')}" for f in engine.get("findings", [])
    )
    return _round(
        {
            "recommendation": _pick(
                engine.get("recommendation"),
                (
                    "recommendation", "recommendation_label", "confidence", "business_quality_score",
                    "investment_attractiveness_score", "business_quality_classification",
                    "investment_attractiveness_classification",
                ),
            ),
            "confidence": engine.get("confidence"),
            "summary_metrics": engine.get("summary_metrics"),
            "modules": modules,
            "findings": findings,
            "risks": sorted(str(r.get("code")) for r in engine.get("risks", [])),
            "opportunities": sorted(str(o.get("code")) for o in engine.get("opportunities", [])),
            "metric_count": len(engine.get("metrics", [])),
        }
    )


FINAL_KEYS = (
    "final_recommendation", "recommendation_label", "confidence", "business_quality_score",
    "business_quality_classification", "investment_attractiveness_score", "investment_attractiveness_classification",
    "valuation_status", "expected_return_status", "roic_wacc_assessment", "current_price", "intrinsic_value",
    "margin_of_safety", "entry_price", "reasons_for", "reasons_against", "key_risks",
)


def final_fingerprint(final: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if final is None else _round(_pick(final, FINAL_KEYS))


def full_fingerprint(engine: dict[str, Any], final: dict[str, Any] | None) -> dict[str, Any]:
    return {"engine": engine_fingerprint(engine), "final_recommendation": final_fingerprint(final)}
