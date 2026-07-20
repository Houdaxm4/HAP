"""Legacy validation helpers retained for workbook-side checks only.

Custom_Run_Filter product validation lives in ``custom_run_validation.py``.
"""

from __future__ import annotations

from typing import Any


def values_match(expected: Any, actual: Any) -> bool:
    """Compare numeric/string cell values with a small relative tolerance."""
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    try:
        return abs(float(expected) - float(actual)) <= max(1.0, abs(float(expected)) * 0.0001)
    except (TypeError, ValueError):
        return str(expected).strip() == str(actual).strip()


def is_impossible_value(concept: str, value: Any) -> bool:
    """Plausibility guard for signed statement concepts."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    lowered = concept.lower()
    if "shares" in lowered or "eps" in lowered or "per share" in lowered:
        return numeric < 0
    if numeric < 0 and any(token in lowered for token in ("revenue", "assets", "cash flow")):
        return True
    return False
