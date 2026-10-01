"""Detect disagreement between the final (workbook-based) and engine (SEC-based) recommendations.

Policy: the final report is the headline; the engine view is shown beside it. Neither overrides the other.
"""

from __future__ import annotations

from typing import Any


def recommendation_conflict(final: dict[str, Any] | None, engine: dict[str, Any] | None) -> dict[str, Any]:
    rec = (engine or {}).get("recommendation") or {}
    final_label = (final or {}).get("final_recommendation")
    engine_label = rec.get("recommendation")
    available = bool(final_label and engine_label)
    conflict = available and str(final_label).upper() != str(engine_label).upper()
    return {
        "available": available,
        "conflict": conflict,
        "headline": final_label if final_label else engine_label,
        "headline_source": "final_recommendation_report" if final_label else "analysis_engine_result",
        "final_recommendation": final_label,
        "engine_recommendation": engine_label,
        "message": (
            f"Final report says {final_label}; analysis engine says {engine_label}. "
            "The final report is the headline; review the difference."
            if conflict else None
        ),
    }
