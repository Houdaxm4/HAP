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


def read_history(path: Path, filings_dir: Path | None = None) -> list[dict[str, Any]]:
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
        item["gross_margin_basis"] = "workbook"
        if (cost is None or cost == 0) and len(populated) >= 3 and item["revenue"]:
            item["gross_margin_comparable"] = False
    if filings_dir is not None:
        _apply_recast(history, filings_dir)
    return history


def _fy_int(token: str) -> int | None:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else None


def _apply_recast(history: list[dict[str, Any]], filings_dir: Path) -> None:
    """Re-express cost of revenue on the latest definition using the 10-K income statements (see cost_recast)."""
    try:
        from services.cost_recast import load_filings, recast_cost

        filings = load_filings(filings_dir)
        workbook_cost = {_fy_int(h["fiscal_year"]): h.get("cost") for h in history if _fy_int(h["fiscal_year"])}
        result = recast_cost(workbook_cost, filings)
    except Exception:  # noqa: BLE001 - recast is an enhancement; the plain history still stands
        return
    if not result.get("label"):
        return
    for item in history:
        info = result["years"].get(_fy_int(item["fiscal_year"]))
        if not info or not item["revenue"]:
            continue
        item["recast_label"] = result["label"]
        item["recast_source_filing_year"] = info["source_filing_year"]
        if info["status"] == "recast":
            item["cost_recast"] = info["value"]
            item["gross_margin"] = (item["revenue"] - info["value"]) / item["revenue"]
            item["gross_margin_comparable"] = True
            item["gross_margin_basis"] = "recast"
        elif info["status"] == "matches":
            item["gross_margin_comparable"] = True
            item["gross_margin_basis"] = "latest_definition"
        else:
            item["gross_margin_basis"] = "prior_definition"


JUMP_POINTS = 0.20  # a gross-margin move this large in one year usually means a cost-classification change


def margin_jumps(history: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    """(from_year, to_year, change) for large year-over-year gross-margin moves between comparable years."""
    out = []
    for prev, cur in zip(history, history[1:]):
        if not (prev.get("gross_margin_comparable", True) and cur.get("gross_margin_comparable", True)):
            continue
        if prev.get("gross_margin_basis") != cur.get("gross_margin_basis") and "prior_definition" in (
            prev.get("gross_margin_basis"), cur.get("gross_margin_basis")
        ):
            continue  # a known definition change, explained in the note
        a, b = prev.get("gross_margin"), cur.get("gross_margin")
        if a is not None and b is not None and abs(b - a) >= JUMP_POINTS:
            out.append((prev["fiscal_year"], cur["fiscal_year"], b - a))
    return out


def noncomparable_years(history: list[dict[str, Any]]) -> list[str]:
    return [h["fiscal_year"] for h in history if not h.get("gross_margin_comparable", True)]


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def table_rows(history: list[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for h in history:
        gross = _pct(h["gross_margin"]) if h.get("gross_margin_comparable", True) else "not comparable"
        if h.get("gross_margin_basis") == "prior_definition" and h.get("gross_margin_comparable", True):
            gross += " (prior definition)"
        elif h.get("gross_margin_basis") == "recast":
            gross += " (recast)"
        rows.append([
            h["fiscal_year"],
            "n/a" if h["revenue"] is None else f"{h['revenue']:,.1f}",
            _pct(h["revenue_growth"]), gross, _pct(h["operating_margin"]), _pct(h["net_margin"]),
        ])
    return rows


def note_text(history: list[dict[str, Any]]) -> str | None:
    bad = noncomparable_years(history)
    jumps = margin_jumps(history)
    parts = []
    recast_years = [h["fiscal_year"] for h in history if h.get("gross_margin_basis") == "recast"]
    prior_years = [h["fiscal_year"] for h in history if h.get("gross_margin_basis") == "prior_definition"]
    if recast_years or prior_years:
        label = next((h.get("recast_label") for h in history if h.get("recast_label")), "the latest line")
        parts.append(
            f"Cost of revenue is shown on one definition: the company's '{label}' expense line as presented in its latest "
            "filings."
            + (f" {', '.join(recast_years)} were recast from the 10-K income statements (the data provider used a different line)." if recast_years else "")
            + (f" {', '.join(prior_years)} predate the company's change in presentation and cannot be recast; their gross margin is on the earlier definition and is not comparable with later years." if prior_years else "")
        )
    if bad:
        parts.append(
            f"Gross margin for {', '.join(bad)} is not comparable: the data provider left cost of revenue blank and "
            "reported all costs as operating expenses, so gross profit equals revenue."
        )
    for start, end, change in jumps:
        parts.append(
            f"Gross margin moved {change * 100:+.0f} points between {start} and {end}. That is large enough to suggest a "
            "change in how costs are classified rather than in the business; check the filings before reading it as a trend."
        )
    if not parts:
        return None
    return " ".join(parts) + " Operating and net margins are unaffected. Revenue is in millions."
