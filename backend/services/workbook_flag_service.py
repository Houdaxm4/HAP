"""Analyst-review flags: Excel comments + fills. Never changes values."""

from __future__ import annotations

from typing import Any

from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.worksheet.worksheet import Worksheet

RED_FILL = PatternFill("solid", fgColor="FF6B6B")
HAP_FILL = PatternFill("solid", fgColor="F4E4C1")
STRUCTURAL_FILL = PatternFill("solid", fgColor="F5A623")

STRUCTURAL_COMMENT = "STRUCTURAL ERROR — MANUAL REVIEW REQUIRED."
SUGGESTION_COMMENT = "SUGGESTION ONLY — VALUE NOT AUTOMATICALLY CHANGED."
HAP_ANALYSIS_LABEL = "HAP ANALYSIS — not original analyst data."


def _author() -> str:
    return "HAP"


def set_comment(cell, text: str) -> None:
    existing = cell.comment.text.strip() if cell.comment and cell.comment.text else ""
    if existing and text in existing:
        return
    body = f"{existing}\n{text}".strip() if existing else text
    cell.comment = Comment(body, _author())


def flag_discrepancy(
    ws: Worksheet,
    addr: str,
    *,
    workbook_value: Any,
    source_value: Any,
    provenance: str,
    issue: str,
) -> None:
    cell = ws[addr]
    cell.fill = RED_FILL
    set_comment(
        cell,
        (
            f"FINANCIAL-STATEMENT DISCREPANCY\n"
            f"Workbook value: {workbook_value}\n"
            f"Source value: {source_value}\n"
            f"Provenance: {provenance}\n"
            f"Issue: {issue}\n"
            "Value was NOT automatically changed."
        ),
    )


def flag_structural(ws: Worksheet, addr: str, *, cycle: list[str] | None = None) -> None:
    cell = ws[addr]
    cell.fill = STRUCTURAL_FILL
    extra = f"\nCircular dependency: {' -> '.join(cycle)}" if cycle else ""
    set_comment(cell, STRUCTURAL_COMMENT + extra)


def flag_suggestion(ws: Worksheet, addr: str, *, suggestion: Any, reason: str) -> None:
    cell = ws[addr]
    cell.fill = RED_FILL
    set_comment(
        cell,
        f"{SUGGESTION_COMMENT}\nSuggested adjustment: {suggestion}\nReason: {reason}",
    )


def style_hap_analysis_cell(cell) -> None:
    cell.fill = HAP_FILL
    set_comment(cell, HAP_ANALYSIS_LABEL)


def flag_filled(ws: Worksheet, addr: str, *, value: Any, source: str, reason: str) -> None:
    """Mark a cell HAP filled because the supplied workbook left it blank and a filing has the figure."""
    cell = ws[addr]
    cell.fill = HAP_FILL
    set_comment(
        cell,
        (
            "HAP FILLED - blank in the supplied workbook.\n"
            f"Value: {value}\n"
            f"Source: {source}\n"
            f"Reason: {reason}"
        ),
    )


def flag_missing_data(ws: Worksheet, addr: str, *, concept: str, reason: str) -> None:
    """Mark a blank cell that a reported metric needs and that no allowed online source could provide."""
    cell = ws[addr]
    cell.fill = RED_FILL
    set_comment(
        cell,
        (
            "DATA MISSING - needed by a reported metric.\n"
            f"Concept: {concept}\n"
            f"Reason: {reason}\n"
            "Not available from SEC EDGAR or Yahoo Finance; metrics that depend on this cell are incomplete."
        ),
    )


def flag_recast(ws: Worksheet, addr: str, *, old_value: Any, new_value: Any, source: str, issue: str) -> None:
    """Mark a cell HAP changed on purpose, keeping the original value in the comment (reversible by hand)."""
    cell = ws[addr]
    cell.fill = HAP_FILL
    set_comment(
        cell,
        (
            "HAP RECAST - value changed from SEC evidence.\n"
            f"Original (data provider): {old_value}\n"
            f"New: {new_value}\n"
            f"Source: {source}\n"
            f"Reason: {issue}"
        ),
    )
