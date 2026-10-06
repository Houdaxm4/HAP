"""Reads the analyst's daily Google Sheet download ("Summary&sector tables.xlsx") for the email draft.

The analyst downloads the sheet each morning into the HAP work folder. For a ticker this returns the four email fields:
  Classified as      -> "Interest" column (Q, K, B, N or U)
  Status with PE10   -> "Current Filter Status w/o PE10 Percentile" column (Buy / Out); it matches the status used in the analyst's emails
  Current TBV/P      -> "TBV/Price" column
  Market Cap         -> not in the sheet: left empty so the email uses the workbook value
The S&P tab is searched first, then the other tabs that carry the same header row (for example FTSE).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.email_draft_service import SheetFields, pct

SHEET_HINT = "summary"
TAB_ORDER = ("S&P", "FTSE")


def find_latest_sheet(folder: Path) -> Path | None:
    """The newest .xlsx in the folder that looks like the summary sheet (has an S&P tab)."""
    candidates = sorted((p for p in Path(folder).glob("*.xlsx") if not p.name.startswith("~$")), key=lambda p: p.stat().st_mtime, reverse=True)
    named = [p for p in candidates if SHEET_HINT in p.name.lower()]
    for path in named + [p for p in candidates if p not in named]:
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception:  # noqa: BLE001 - not a readable workbook
            continue
        try:
            if "S&P" in wb.sheetnames:
                return path
        finally:
            wb.close()
    return None


def _header_map(ws) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in range(1, (ws.max_column or 1) + 1):
        h = ws.cell(1, c).value
        if h:
            out[" ".join(str(h).lower().split())] = c
    return out


def _col(headers: dict[str, int], *needles: str) -> int | None:
    for key, c in headers.items():
        if all(n in key for n in needles):
            return c
    return None


class DailySheet:
    """Rows of the daily sheet by ticker."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._rows: dict[str, dict[str, Any]] = {}
        wb = load_workbook(self.path, data_only=True)
        try:
            for tab in [t for t in TAB_ORDER if t in wb.sheetnames] + [t for t in wb.sheetnames if t not in TAB_ORDER]:
                self._load_tab(wb[tab], tab)
        finally:
            wb.close()

    def _load_tab(self, ws, tab: str) -> None:
        headers = _header_map(ws)
        c_tick = _col(headers, "ticker")
        c_int = _col(headers, "interest")
        c_stat = _col(headers, "current filter status")
        c_tbv = _col(headers, "tbv/price")
        if not (c_tick and c_int):
            return
        for r in range(2, (ws.max_row or 1) + 1):
            t = str(ws.cell(r, c_tick).value or "").strip().upper()
            if not t or t in self._rows:
                continue          # first tab wins (S&P before the others)
            self._rows[t] = {
                "tab": tab,
                "company": ws.cell(r, 1).value,
                "interest": ws.cell(r, c_int).value,
                "status": ws.cell(r, c_stat).value if c_stat else None,
                "tbv_price": ws.cell(r, c_tbv).value if c_tbv else None,
            }

    def has(self, ticker: str) -> bool:
        return ticker.strip().upper() in self._rows

    def row(self, ticker: str) -> dict[str, Any] | None:
        return self._rows.get(ticker.strip().upper())

    def fields(self, ticker: str) -> SheetFields:
        """The email fields for the ticker; anything not in the sheet stays None so the email falls back to the workbook."""
        row = self.row(ticker)
        if row is None:
            return SheetFields()
        status = str(row["status"]).strip() if row.get("status") not in (None, "", "N/A") else None
        tbv = row.get("tbv_price")
        return SheetFields(
            classified_as=str(row["interest"]).strip() if row.get("interest") not in (None, "") else None,
            pe10_status=status,
            tbv_p_text=pct(float(tbv)) if isinstance(tbv, (int, float)) and not isinstance(tbv, bool) else None,
        )

    def company_name(self, ticker: str) -> str:
        row = self.row(ticker)
        name = str(row["company"]).strip() if row and row.get("company") else ""
        return re.sub(r"\s*Common Stock\s*$", "", name, flags=re.I).strip()      # the sheet writes 'Woodward, Inc.Common Stock'
