"""Shared wording for Word deliverables: the headline recommendation and small text helpers.

Policy: the final (workbook-based) report is the headline; the engine's view is shown beside it when they
differ. Reads only artifacts already saved for the analysis; it never recomputes anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.recommendation_conflict import recommendation_conflict


def _read(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / name
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def headline_lines(output_dir: Path) -> list[str]:
    """Plain-English lines for the top of the document. Empty when no recommendation exists yet."""
    final = _read(output_dir, "final_recommendation_report.json")
    engine = _read(output_dir, "analysis_engine_result.json")
    info = recommendation_conflict(final, engine)
    if not info["headline"]:
        return []
    label = str(info["headline"]).replace("_", " ")
    lines = [f"Recommendation: {label}."]
    if final:
        parts = []
        if final.get("business_quality_classification"):
            parts.append(f"business quality {str(final['business_quality_classification']).replace('_', ' ').lower()}")
        if final.get("investment_attractiveness_classification"):
            parts.append(f"investment attractiveness {str(final['investment_attractiveness_classification']).replace('_', ' ').lower()}")
        if final.get("valuation_status"):
            parts.append(f"valuation {str(final['valuation_status']).replace('_', ' ').lower()}")
        if parts:
            lines.append("Basis: " + "; ".join(parts) + ".")
    if info["conflict"]:
        lines.append(
            f"Note: HAP's separate SEC-based analysis engine reads this as {str(info['engine_recommendation']).replace('_', ' ')}. "
            "The recommendation above is the headline; the difference is flagged for analyst review."
        )
    return lines


def dedupe(items: list[str]) -> list[str]:
    """Drop repeated entries, keep first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = " ".join(str(item).split())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def pct_text(value: float) -> str:
    """Format a rate that may be stored as a fraction (0.0247) or as percent points (2.47)."""
    x = float(value)
    if abs(x) <= 1.5:
        x *= 100.0
    return f"{x:.2f}%"
