"""Extract validation CSV fields from persisted pipeline / engine artifacts."""

from __future__ import annotations

from typing import Any


def metric_value(engine_result: dict[str, Any] | None, code: str) -> float | None:
    """Return the first metric value matching ``code`` from the engine result."""
    if not engine_result:
        return None
    for metric in engine_result.get("metrics") or []:
        if metric.get("code") == code:
            value = metric.get("value")
            if isinstance(value, (int, float)):
                return float(value)
    for module in engine_result.get("modules") or []:
        for metric in module.get("metrics") or []:
            if metric.get("code") == code:
                value = metric.get("value")
                if isinstance(value, (int, float)):
                    return float(value)
    return None


def module_coverage(engine_result: dict[str, Any] | None) -> tuple[int, int, int, list[str]]:
    """
    Return (ok_count, skipped_count, error_count, incomplete_module_names).

    Incomplete = skipped or error (excluding recommendation when skipped for insufficient data
    is still counted as incomplete coverage).
    """
    if not engine_result:
        return 0, 0, 0, []
    ok = 0
    skipped = 0
    errors = 0
    incomplete: list[str] = []
    for module in engine_result.get("modules") or []:
        name = str(module.get("module_name") or "unknown")
        status = str(module.get("status") or "")
        if status == "ok":
            ok += 1
        elif status == "error":
            errors += 1
            incomplete.append(name)
        else:
            skipped += 1
            incomplete.append(name)
    return ok, skipped, errors, incomplete


def extract_analytical_fields(engine_result: dict[str, Any] | None) -> dict[str, Any]:
    """Project engine analytical fields used by the validation CSV."""
    empty = {
        "business_quality_score": None,
        "business_quality_rating": None,
        "investment_attractiveness_score": None,
        "investment_attractiveness_rating": None,
        "recommendation": None,
        "fair_value": None,
        "current_price": None,
        "margin_of_safety": None,
        "expected_return": None,
    }
    if not engine_result:
        return empty

    bq = engine_result.get("business_quality") or {}
    ia = engine_result.get("investment_attractiveness") or {}
    rec = engine_result.get("recommendation") or {}

    fair_value = metric_value(engine_result, "FAIR_VALUE_BASE")
    current_price = metric_value(engine_result, "SHARE_PRICE")
    margin_of_safety = metric_value(engine_result, "MARGIN_OF_SAFETY")
    expected_return = metric_value(engine_result, "EXPECTED_CAGR")
    if expected_return is None:
        expected_return = metric_value(engine_result, "EXPECTED_IRR")

    return {
        "business_quality_score": bq.get("score"),
        "business_quality_rating": bq.get("classification_label") or bq.get("classification"),
        "investment_attractiveness_score": ia.get("score"),
        "investment_attractiveness_rating": ia.get("classification_label") or ia.get("classification"),
        "recommendation": rec.get("recommendation_label") or rec.get("recommendation"),
        "fair_value": fair_value,
        "current_price": current_price,
        "margin_of_safety": margin_of_safety,
        "expected_return": expected_return,
    }
