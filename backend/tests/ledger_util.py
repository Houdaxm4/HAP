"""Test helper: read the HAP Adjustments tab (every flag and change HAP makes is listed there; cells carry no comment boxes)."""

from __future__ import annotations

COLUMNS = ("id", "year", "tab", "cell", "category", "what", "original", "new", "amount", "reason", "source", "method", "confidence", "status")


def ledger(wb) -> list[dict]:
    if "HAP Adjustments" not in wb.sheetnames:
        return []
    ws = wb["HAP Adjustments"]
    rows = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row and row[0]:
            rows.append(dict(zip(COLUMNS, row)))
    return rows


def entry(wb, tab: str, cell: str, category: str | None = None) -> dict | None:
    for item in ledger(wb):
        if item["tab"] == tab and item["cell"] == cell and (category is None or item["category"] == category):
            return item
    return None


def notes_text(ws) -> str:
    """All text in the tab's single Notes block."""
    from services.tab_notes import read_notes

    return " ".join(read_notes(ws))
