"""Stand-in Custom_Run_Filter built from the analyst's multi-company "Current Filter Summary Sheet".

The Summary tab of a real custom run filter is one row with the same columns as the rows of the filter summary sheet, and the scalar
block of the ticker tab repeats those values by label. When an analyst has no per-company filter, this builds one from the sheet's row
for the ticker. It carries today's market data only: no quarterly history and no PE10 history, so the valuation fields that depend on a
period's own market data are not those of an older period. Callers must say so wherever the result is shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

SKELETON = Path(__file__).resolve().parents[1] / "resources" / "crf_skeleton.xlsx"
_KEY_HEADERS = ("ticker", "current price (live price)", "max current price to buy")
STANDIN_MARK = "STAND-IN: built by HAP from the current filter summary sheet (today's market data, no PE10 history)"


class StandInError(Exception):
    pass


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def find_filter_summary(folder: Path) -> Path | None:
    """Newest .xlsx in the folder with a 'Summary' tab whose header row holds Ticker, price and Max Current Price to Buy."""
    candidates = sorted(
        (p for p in Path(folder).glob("*.xlsx") if not p.name.startswith("~$") and not p.name.lower().startswith("custom")),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    named = [p for p in candidates if "filter summary" in p.name.lower()] + [p for p in candidates if "filter summary" not in p.name.lower()]
    for path in named:
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception:  # noqa: BLE001 - not a readable workbook
            continue
        try:
            for name in wb.sheetnames:
                if _norm(name) != "summary":
                    continue
                header = next(wb[name].iter_rows(min_row=1, max_row=1, values_only=True), ())
                have = {_norm(h) for h in header}
                if all(k in have for k in _KEY_HEADERS):
                    return path
        finally:
            wb.close()
    return None


def read_summary_row(summary_path: Path, ticker: str) -> dict[str, Any]:
    wb = load_workbook(summary_path, read_only=True, data_only=True)
    try:
        ws = wb["Summary"] if "Summary" in wb.sheetnames else wb[next(n for n in wb.sheetnames if _norm(n) == "summary")]
        rows = ws.iter_rows(values_only=True)
        header = list(next(rows))
        tcol = next(i for i, h in enumerate(header) if _norm(h) == "ticker")
        for row in rows:
            if str(row[tcol] or "").strip().upper() == ticker.upper():
                return {h: v for h, v in zip(header, row) if h is not None}
    finally:
        wb.close()
    raise StandInError(f"{ticker} is not in the filter summary sheet {summary_path.name}")


def build_standin(ticker: str, summary_path: Path, out_path: Path) -> dict[str, Any]:
    """Write a stand-in custom run filter for the ticker; returns what was filled and what the sheet did not have."""
    data = read_summary_row(summary_path, ticker)
    price, cap = data.get("Current Price (Live Price)"), data.get("Current Market Capitalization")
    if not isinstance(price, (int, float)) or not price:
        raise StandInError(f"{ticker} has no current price in {summary_path.name}")
    wb = load_workbook(SKELETON)
    ws = wb[wb.sheetnames[0]]
    ws.title = ticker.upper()
    ws["B1"] = f"{ticker.upper()} US Equity"
    ws["A13"] = STANDIN_MARK
    filled, missing = 0, []
    for r in range(2, 13):
        label = ws.cell(r, 1).value
        if label in data and data[label] is not None:
            ws.cell(r, 2).value = data[label]
    for r in range(150, 300):
        label = ws.cell(r, 1).value
        if label is None:
            continue
        if label in data and data[label] is not None:
            ws.cell(r, 2).value = data[label]
            filled += 1
        else:
            missing.append(str(label))
    summary = wb["Summary"]
    for c, header in enumerate(data, 1):
        summary.cell(1, c).value = header
        summary.cell(2, c).value = data[header]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return {"ticker": ticker.upper(), "source": summary_path.name, "path": str(out_path), "filled": filled,
            "missing_fields": missing, "price": price, "market_cap": cap}
