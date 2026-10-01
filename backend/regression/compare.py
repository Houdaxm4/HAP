"""Deep comparison with a numeric tolerance. Returns human-readable differences."""

from __future__ import annotations

from typing import Any

TOLERANCE = 1e-6


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def diff(expected: Any, actual: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                out.append(f"{path}/{key}: missing now (was {str(expected[key])[:60]})")
            elif key not in expected:
                out.append(f"{path}/{key}: new (now {str(actual[key])[:60]})")
            else:
                out += diff(expected[key], actual[key], f"{path}/{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            removed = [x for x in expected if x not in actual]
            added = [x for x in actual if x not in expected]
            if removed or added or len(expected) != len(actual):
                out.append(f"{path}: list changed; removed {removed[:5]}, added {added[:5]}")
    elif _is_number(expected) and _is_number(actual):
        if abs(expected - actual) > TOLERANCE:
            out.append(f"{path}: {expected} -> {actual}")
    elif expected != actual:
        out.append(f"{path}: {str(expected)[:60]} -> {str(actual)[:60]}")
    return out
