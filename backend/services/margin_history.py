"""Ten-year revenue growth and margin history read from a completed workbook (read-only).

Flags years whose cost of revenue is blank or zero between populated years: the data provider then put all
costs under operating expenses, so that year's gross margin (100%) is not comparable with its neighbours.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

SHEET = "Income - GAAP"
ROW_KEYS = {
    "revenue": ("SALES_REV_TURN",),
    "cost": ("IS_COGS_TO_FE_AND_PP_AND_G",),
    "gross_profit": ("GROSS_PROFIT",),
    "operating_income": ("IS_OPER_INC",),
    "net_income": ("NET_INCOME",),
}


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _find_rows(ws) -> dict[str, int]:
    rows: dict[str, int] = {}
    for r in range(1, min(ws.max_row or 1, 120) + 1):
        key = str(ws.cell(r, 2).value or "").strip()
        for name, keys in ROW_KEYS.items():
            if key in keys and name not in rows:
                rows[name] = r
    return rows


def _ratio(a: float | None, b: float | None) -> float | None:
    return None if a is None or not b else a / b


def read_history(path: Path) -> list[dict[str, Any]]:
    from services.annual_period_service import detect_year_columns

    wb = load_workbook(path, data_only=True)
    try:
        if SHEET not in wb.sheetnames:
            return []
        ws = wb[SHEET]
        rows = _find_rows(ws)
        if "revenue" not in rows:
            return []
        columns = detect_year_columns(ws, wb)
        history: list[dict[str, Any]] = []
        for fy in sorted(columns, key=lambda t: int("".join(ch for ch in t if ch.isdigit()) or 0)):
            col = columns[fy]
            item = {name: _num(ws.cell(row, col).value) for name, row in rows.items()}
            item["fiscal_year"] = fy
            history.append(item)
    finally:
        wb.close()

    for index, item in enumerate(history):
        prior = history[index - 1]["revenue"] if index else None
        item["revenue_growth"] = None if not prior or item["revenue"] is None else item["revenue"] / prior - 1
        item["gross_margin"] = _ratio(item.get("gross_profit"), item["revenue"])
        item["operating_margin"] = _ratio(item.get("operating_income"), item["revenue"])
        item["net_margin"] = _ratio(item.get("net_income"), item["revenue"])
    populated = [h for h in history if (h.get("cost") or 0) > 0]
    for item in history:
        cost = item.get("cost")
        item["gross_margin_comparable"] = True
        if (cost is None or cost == 0) and len(populated) >= 3 and item["revenue"]:
            item["gross_margin_comparable"] = False
    return history


def noncomparable_years(history: list[dict[str, Any]]) -> list[str]:
    return [h["fiscal_year"] for h in history if not h.get("gross_margin_comparable", True)]


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def table_rows(history: list[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for h in history:
        gross = _pct(h["gross_margin"]) if h.get("gross_margin_comparable", True) else "not comparable"
        rows.append([
            h["fiscal_year"],
            "n/a" if h["revenue"] is None else f"{h['revenue']:,.1f}",
            _pct(h["revenue_growth"]), gross, _pct(h["operating_margin"]), _pct(h["net_margin"]),
        ])
    return rows


def note_text(history: list[dict[str, Any]]) -> str | None:
    bad = noncomparable_years(history)
    if not bad:
        return None
    return (
        f"Gross margin for {', '.join(bad)} is not comparable: the data provider left cost of revenue blank and "
        "reported all costs as operating expenses, so gross profit equals revenue. Operating and net margins are "
        "unaffected. Revenue is in millions."
    )
