"""Recast a workbook cost-of-revenue row to ONE definition using the company's own 10-K income statements.

Why: data providers sometimes switch which operating-expense line they call "cost of revenue" when the company
changes its presentation. SEC XBRL often has no tag for that line, so the figures are read from the filing's income
statement. The latest definition is identified by matching the latest year's workbook value to a statement row.
Read-only: nothing is written to the workbook.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TOLERANCE = 0.005  # 0.5% when matching a workbook value to a statement row
_NUM = r"(?:\(\s*[\d,]+\s*\)|[\d,]+|-)"
_ROW_RE = re.compile(rf"([A-Za-z][A-Za-z ,&/\-]*?)\s+\$?\s*({_NUM})\s+\$?\s*({_NUM})(?:\s+\$?\s*({_NUM}))?(?=\s|$)")
_SECTION_START = re.compile(r"OPERATING EXPENSES:?|COSTS AND EXPENSES:?", re.I)
_SECTION_END = re.compile(r"Total\s+operating\s+expenses|Total\s+costs\s+and\s+expenses", re.I)


def _to_float(token: str | None) -> float | None:
    if token is None:
        return None
    token = token.strip()
    if token == "-":
        return 0.0
    negative = token.startswith("(")
    digits = re.sub(r"[^\d]", "", token)
    if not digits:
        return None
    value = float(digits)
    return -value if negative else value


def parse_expense_rows(statement_text: str) -> dict[str, list[float | None]]:
    """Operating-expense rows of one income statement: label -> values [latest, prior, prior-1] in the filing's units."""
    start = _SECTION_START.search(statement_text)
    end = _SECTION_END.search(statement_text, start.end() if start else 0)
    if not start or not end:
        return {}
    block = re.sub(r"\s+", " ", statement_text[start.end():end.start()])
    rows: dict[str, list[float | None]] = {}
    for match in _ROW_RE.finditer(block):
        label = match.group(1).strip(" ,")
        if label and label.lower() not in rows:
            rows[label.lower()] = [_to_float(match.group(i)) for i in (2, 3, 4)]
    return rows


def _find_statement(text: str) -> str:
    for m in re.finditer(r"CONSOLIDATED STATEMENTS? OF (?:INCOME|OPERATIONS)", text, re.I):
        block = text[m.start(): m.start() + 3000]
        if _SECTION_START.search(block) and _SECTION_END.search(block):
            return block
    return ""


def parse_total_expenses(statement_text: str) -> list[float | None]:
    """The 'Total operating expenses' row of one income statement: [latest, prior, prior-1]."""
    end = _SECTION_END.search(statement_text)
    if not end:
        return []
    tail = re.sub(r"\s+", " ", statement_text[end.end(): end.end() + 160])
    m = re.match(rf"\s*\$?\s*({_NUM})\s+\$?\s*({_NUM})(?:\s+\$?\s*({_NUM}))?", tail)
    return [_to_float(m.group(i)) for i in (1, 2, 3)] if m else []


def statement_total_for_year(filings: dict[int, str], fiscal_year: int) -> list[float | None]:
    text = filings.get(fiscal_year)
    return parse_total_expenses(_find_statement(text)) if text else []


def statement_rows_for_year(filings: dict[int, str], fiscal_year: int) -> dict[str, list[float | None]]:
    text = filings.get(fiscal_year)
    return parse_expense_rows(_find_statement(text)) if text else {}


def recast_cost(
    workbook_cost: dict[int, float | None],
    filings: dict[int, str],
    *,
    unit_divisor: float = 1000.0,
) -> dict[str, Any]:
    """workbook_cost: fiscal year -> workbook cost of revenue ($M). filings: fiscal year -> 10-K text (thousands).

    Returns {label, years: {fy: {"value", "status", "source_filing_year"}}}. Status is one of
    'matches' (workbook already on this definition), 'recast' (replaced from a filing) or 'not_recastable'.
    """
    if not workbook_cost:
        return {"label": None, "years": {}}
    # Anchor on the latest year that has both a workbook value and a parsable filing statement.
    anchors = [fy for fy in sorted(workbook_cost, reverse=True) if workbook_cost[fy] and statement_rows_for_year(filings, fy)]
    if not anchors:
        return {"label": None, "years": {}}
    latest = anchors[0]
    anchor_value = workbook_cost[latest]
    rows = statement_rows_for_year(filings, latest)
    label = next(
        (name for name, values in rows.items()
         if values[0] is not None and abs(values[0] / unit_divisor - anchor_value) <= TOLERANCE * abs(anchor_value)),
        None,
    )
    if label is None:
        return {"label": None, "years": {}}

    years: dict[int, dict[str, Any]] = {}
    for fy in sorted(workbook_cost):
        found = None
        # Earliest filing that presents this year under the same label (as first reported on this definition).
        for filing_year in sorted(filings):
            offset = filing_year - fy
            if offset < 0 or offset > 2:
                continue
            values = statement_rows_for_year(filings, filing_year).get(label)
            if values and values[offset] is not None:
                found = (values[offset] / unit_divisor, filing_year)
                break
        book = workbook_cost.get(fy)
        if found is None:
            years[fy] = {"value": book, "status": "not_recastable", "source_filing_year": None}
        elif book and abs(book - found[0]) <= TOLERANCE * abs(found[0]):
            years[fy] = {"value": book, "status": "matches", "source_filing_year": found[1]}
        else:
            years[fy] = {"value": found[0], "status": "recast", "source_filing_year": found[1]}
    return {"label": label, "years": years}


def load_filings(filings_dir: Path) -> dict[int, str]:
    """Cached 10-K files named like '10k_buybacks_2022.htm' (fiscal year) -> plain text."""
    from services.new_company_buyback_service import html_to_text

    out: dict[int, str] = {}
    for path in sorted(filings_dir.glob("10k_*_*.htm")):
        match = re.search(r"_(\d{4})\.htm$", path.name)
        if not match:
            continue
        try:
            out[int(match.group(1))] = html_to_text(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return out
