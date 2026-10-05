"""Analyst-review flags: shaded cells, a line in the HAP Adjustments tab, and one plain-language note on the tab.

There are no comment boxes on cells. Notes live in one place per tab (the Notes block, see tab_notes) and the detail of every flag
(cell, original or workbook value, filing value, reason, source) is a row in the HAP Adjustments tab. Never changes values, except flag_recast
and flag_adjustment, whose callers change the value and need the original kept.
"""

from __future__ import annotations

from typing import Any

from openpyxl.styles import PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from services.tab_notes import add_notes, note

RED_FILL = PatternFill("solid", fgColor="FF6B6B")
HAP_FILL = PatternFill("solid", fgColor="F4E4C1")
STRUCTURAL_FILL = PatternFill("solid", fgColor="F5A623")

STRUCTURAL_COMMENT = "STRUCTURAL ERROR — MANUAL REVIEW REQUIRED."
SUGGESTION_COMMENT = "SUGGESTION ONLY — VALUE NOT AUTOMATICALLY CHANGED."
HAP_ANALYSIS_LABEL = "HAP ANALYSIS — not original analyst data."

FILINGS = "the company's SEC filings"


def set_comment(cell, text: str) -> None:
    """Kept so older callers keep working. Cells no longer get comment boxes; see the module note."""
    return None


def _source_label(source: str | None) -> str:
    return "Yahoo Finance (unofficial, indicative)" if source and "yahoo" in str(source).lower() else FILINGS


def _record(ws: Worksheet, addr: str, *, category: str, what: str, original: Any, new: Any, reason: str, source: str,
            method: str, status: str, notes: list[str]) -> None:
    from services.adjustment_ledger_service import AdjustmentLedger

    wb = ws.parent
    if wb is not None:
        AdjustmentLedger(wb).record(
            sheet=ws.title, cell=addr, fiscal_year=None, category=category, what=what, original=original, new=new, amount=None,
            reason=reason, source=source, method=method, confidence="medium", mark_cell=False, status=status,
        )
    add_notes(ws, notes)


def flag_discrepancy(
    ws: Worksheet,
    addr: str,
    *,
    workbook_value: Any,
    source_value: Any,
    provenance: str,
    issue: str,
) -> None:
    ws[addr].fill = RED_FILL
    _record(
        ws, addr, category="Differs from filing", what="Figure differs from the filing", original=workbook_value, new=source_value,
        reason=f"{issue} The supplied value was not changed.", source=str(provenance), method="flag_only", status="Flagged only",
        notes=[note("Red cells hold a figure that differs from the filing and were left as supplied", "figures are not overwritten without your approval",
                    _source_label(provenance))],
    )


def flag_structural(ws: Worksheet, addr: str, *, cycle: list[str] | None = None) -> None:
    ws[addr].fill = STRUCTURAL_FILL
    _record(
        ws, addr, category="Formula problem", what="Circular reference", original="formula", new="unchanged",
        reason="A circular dependency was found" + (f": {' -> '.join(cycle)}" if cycle else "") + ". Manual review required.",
        source="the workbook formulas", method="flag_only", status="Flagged only",
        notes=[note("Orange cells have a circular reference that needs a manual review", "the formulas depend on each other", "the workbook formulas")],
    )


def flag_suggestion(ws: Worksheet, addr: str, *, suggestion: Any, reason: str) -> None:
    ws[addr].fill = RED_FILL
    _record(
        ws, addr, category="Suggestion", what="Suggested alternative value", original=ws[addr].value, new=suggestion,
        reason=f"{reason} The value was not changed.", source="the company's history in this workbook", method="flag_only", status="Flagged only",
        notes=[note("Red cells have a suggested alternative value; the cell itself was not changed", "the current value looks unrealistic",
                    "the company's history in this workbook")],
    )


def style_hap_analysis_cell(cell) -> None:
    """Shade a cell that belongs to HAP's own analysis (not original analyst data). No comment box."""
    cell.fill = HAP_FILL


def flag_filled(ws: Worksheet, addr: str, *, value: Any, source: str, reason: str) -> None:
    """Mark a cell HAP filled because the supplied workbook left it blank and a filing has the figure."""
    ws[addr].fill = HAP_FILL
    label = _source_label(source)
    _record(
        ws, addr, category="Filled from filing", what="Blank cell filled", original="blank", new=value, reason=reason, source=str(source),
        method="yahoo_quarterly_sum" if "Yahoo" in label else "sec_10q", status="Applied",
        notes=[note("Beige cells were filled from a filing", "the supplied workbook left them blank", label)],
    )


def flag_missing_data(ws: Worksheet, addr: str, *, concept: str, reason: str) -> None:
    """Mark a blank cell that a reported metric needs and that no allowed online source could provide."""
    ws[addr].fill = RED_FILL
    _record(
        ws, addr, category="Missing figure", what=f"Missing: {concept}", original="blank", new="still blank", reason=reason,
        source="SEC EDGAR and Yahoo Finance", method="flag_only", status="Flagged only",
        notes=[note("Red cells are missing a figure", "no allowed source could provide it, so metrics that need it are incomplete",
                    "SEC EDGAR and Yahoo Finance")],
    )


def flag_recast(ws: Worksheet, addr: str, *, old_value: Any, new_value: Any, source: str, issue: str) -> None:
    """Mark a cell HAP changed on purpose; the original value is kept in the HAP Adjustments tab (reversible by hand)."""
    ws[addr].fill = HAP_FILL
    _record(
        ws, addr, category="Recast to latest definition", what="Figure changed to the latest definition", original=old_value, new=new_value,
        reason=issue, source=str(source), method="sec_override", status="Applied",
        notes=[note("Beige cells were changed to the company's latest definition", "the supplied figure used an older definition", FILINGS)],
    )


def flag_adjustment(ws: Worksheet, addr: str, *, original: Any, new: Any, reason: str, source: str) -> None:
    """Mark a cell HAP adjusted on purpose; the original is kept in the HAP Adjustments tab."""
    ws[addr].fill = HAP_FILL
    _record(
        ws, addr, category="Adjustment", what="Value adjusted", original=original, new=new, reason=reason, source=str(source),
        method="one_time_item", status="Applied",
        notes=[note("Beige cells were adjusted", reason, str(source))],
    )
