"""Point-in-time custom run filter: the filter as it stood at the end of an earlier quarter.

A Custom_Run_Filter export lists quarterly history in columns (one column per fiscal quarter, labelled "2025 Q1") and, below it, a
scalar block of "current" values at the export date. To back-test an older period this builds a filter whose scalars are taken from the
history column of that quarter, and whose history stops at that quarter (nothing later is carried), so every downstream number is what
the analyst would have seen then.

Mapping (checked against the analyst's own AMAT FY2024 run: E10, growth rates and TBV matched, the max entry price within about 3%):
  Current Price               <- "Closing Stock Price (Q. Average)" of the quarter (quarter average, not a close)
  Current E10 / PE10          <- E10 / PE10 of the quarter
  Current Max PE10 to Enter   <- "Lowest of 20th Percentile PE10 or 7PE10" of the quarter
  Max Current Price to Buy    <- that multiple x E10
  1st Exit Price              <- "Lowest of 45th Percentile PE10 or 7PE10" x E10
  EV / market cap / TBV/P / growth rates / margins / ROCE ... <- the same-named history row of the quarter
  PE10 percentile             <- share of the quarterly PE10 history up to the quarter at or below the quarter's PE10 (approximation:
                                 a real export uses daily PE10s, which are not kept per quarter)
Scalars with no history row (Graham, expected return, residual earnings, ...) are left empty so nothing from a later date leaks in;
the workbook computes its own versions.

Share basis: a back-test workbook is pulled today and is adjusted for every split since the period (TPL: two 3-for-1 splits, so its 2019
share count is 9 times the one reported then), while the filter export holds per-share figures as they stood on its own date. The factor
is read from the two share counts (workbook diluted shares of the period vs the filter's shares of that quarter) and every per-share
series is converted to the workbook's basis, so price, E10, entry/exit prices and dividends agree with the workbook's EPS and book value.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

MARK = "POINT-IN-TIME: scalars taken from the history column of {q}; history after that quarter removed"
_SCALAR_ANCHOR = "Current E10"
_PE10_TABLE_LABEL = "PE10"


class PointInTimeError(Exception):
    pass


# per-share series of the filter (value / factor) and share-count series (value x factor); ratios such as "per Share/Price" are untouched
_PER_SHARE = ("Closing Stock Price", "Dividends per Share", "Earnings per Share", "Tangible Book Value per Share",
              "Dividend Rate", "Owners Earnings per Share", "Funds from Operations per Share", "Book Value Per Share",
              "BV per Share", "High Price", "Low Price")
_SHARE_COUNT = ("Shares Outstanding",)
_NOT_PER_SHARE = ("/", "Percentile", "Yield", "Change", "Growth", "Direction", "Payout", "Satisfied", "Number of")
_SHARES_LABEL = "Shares Outstanding Diluted Average (MM)"


def _scale_kind(label: str) -> str | None:
    if not isinstance(label, str) or any(x in label for x in _NOT_PER_SHARE):
        return None
    if label == "E10" or any(label.startswith(x) for x in _PER_SHARE):
        return "per_share"
    if any(label.startswith(x) for x in _SHARE_COUNT):
        return "shares"
    return None


def _clean_factor(raw: float) -> float:
    """Round a share-count ratio to a plausible split factor (whole numbers and halves, within 3%); otherwise 1.0 (no conversion)."""
    if raw < 1.45:
        return 1.0
    for candidate in (round(raw * 2) / 2, round(raw)):
        if candidate >= 1.5 and abs(raw - candidate) / candidate <= 0.03:
            return float(candidate)
    return 1.0


def infer_share_factor(workbook_path: Path, crf_path: Path, quarter: str) -> float:
    """Workbook shares / filter shares for the quarter, as a clean split factor (1.0 when the two agree or cannot be compared)."""
    try:
        wb = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            ws = wb["Last Quarter IS Standardized"]
            wb_shares = None
            for row in ws.iter_rows(min_row=1, max_row=120, max_col=3, values_only=True):
                if row and row[1] == "IS_SH_FOR_DILUTED_EPS":
                    wb_shares = _num(row[2])
                    break
        finally:
            wb.close()
        cwb = load_workbook(crf_path, read_only=True, data_only=True)
        try:
            ws = cwb[cwb.sheetnames[0]]
            rows = list(ws.iter_rows(min_row=1, max_row=200, values_only=True))
        finally:
            cwb.close()
        fq = next(r for r in rows if r and r[0] == "Fiscal Quarter")
        col = next(i for i, v in enumerate(fq) if v == quarter)
        sh = next(r for r in rows if r and r[0] == _SHARES_LABEL)
        crf_shares = _num(sh[col])
        if not wb_shares or not crf_shares:
            return 1.0
        return _clean_factor(wb_shares / crf_shares)
    except Exception:  # noqa: BLE001 - not comparable: leave the filter as it is
        return 1.0


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def available_quarters(crf_path: Path) -> list[str]:
    wb = load_workbook(crf_path, read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        row = next(ws.iter_rows(min_row=16, max_row=16, values_only=True))
        return [str(v) for v in row[1:] if v]
    finally:
        wb.close()


def quarter_key(label: str) -> tuple[int, int]:
    y, q = label.split()
    return int(y), int(q[1:])


def build_point_in_time(crf_path: Path, quarter: str, out_path: Path, share_factor: float = 1.0) -> dict[str, Any]:
    wb = load_workbook(crf_path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    labels = {}
    for r in range(1, (ws.max_row or 1) + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, str) and v not in labels:
            labels[v] = r
    for need in ("date", "Fiscal Quarter", _SCALAR_ANCHOR, "E10", "PE10", "Closing Stock Price (Q. Average)"):
        if need not in labels:
            raise PointInTimeError(f"{crf_path.name}: row '{need}' not found; not a recognised custom run filter layout")
    date_row, fq_row, scalar_start = labels["date"], labels["Fiscal Quarter"], labels[_SCALAR_ANCHOR]
    max_col = ws.max_column or 1
    col = next((c for c in range(2, max_col + 1) if ws.cell(fq_row, c).value == quarter), None)
    if col is None:
        raise PointInTimeError(f"{crf_path.name} has no history column for {quarter}")

    series_rows = {lab: r for lab, r in labels.items() if r < scalar_start and r > fq_row}
    if share_factor and abs(share_factor - 1.0) > 1e-9:
        for lab, r in series_rows.items():
            kind = _scale_kind(lab)
            if kind is None:
                continue
            for c in range(2, max_col + 1):
                v = _num(ws.cell(r, c).value)
                if v is not None:
                    ws.cell(r, c).value = v / share_factor if kind == "per_share" else v * share_factor
    def sv(label: str):
        r = series_rows.get(label)
        return ws.cell(r, col).value if r else None

    price, e10 = _num(sv("Closing Stock Price (Q. Average)")), _num(sv("E10"))
    if not price or not e10:
        raise PointInTimeError(f"{crf_path.name}: price or E10 missing for {quarter}")
    q_date = ws.cell(date_row, col).value
    max_pe = _num(sv("Lowest of 20th Percentile PE10 or 7PE10"))
    exit_pe = _num(sv("Lowest of 45th Percentile PE10 or 7PE10"))
    pe10_hist = sorted(
        v for c in range(2, col + 1) if (v := _num(ws.cell(series_rows["PE10"], c).value)) is not None
    )
    pe10 = _num(sv("PE10")) or price / e10
    percentile = (sum(1 for v in pe10_hist if v <= pe10) / len(pe10_hist)) if pe10_hist else None

    # latest annual earnings date: most recent Q4 column up to the quarter
    annual_date = None
    ea_row = series_rows.get("Earnings Announcement Date")
    for c in range(col, 1, -1):
        if str(ws.cell(fq_row, c).value).endswith("Q4") and ea_row:
            v = ws.cell(ea_row, c).value
            annual_date = v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else v
            break
    wacc = _num(sv("Weighted Average Cost of Capital"))

    override: dict[str, Any] = {
        "Current Price (Live Price)": price,
        "Current E10": e10,
        "Current PE10": pe10,
        "Current Max PE10 to Enter (Lowest PE10 or 7PE10)": max_pe,
        "Max Current Price to Buy": max_pe * e10 if max_pe else None,
        "1st Exit Price": exit_pe * e10 if exit_pe else None,
        "2nd Exit Price": None,
        "Latest Quarter Assets/ Liabilities": sv("Assets/Liabilities"),
        "Current 3 year EPS 10 years Av Growth": sv("3 years Av EPS Growth (10 Years) TTM"),
        "Current 3 year EPS 10 years Av Growth Direction": sv("3 years Av EPS Growth (10 Years) TTM Direction"),
        "Current 3 year Revenue 10 years Av Growth": sv("3 years Av Revenue Growth (10 Years) TTM"),
        "Current TBV/Price": sv("Tangible Book Value per Share/Price"),
        "Current Enterprise Value (not-diluted)": sv("Enterprise Value (not-diluted)"),
        "Current Market Capitalization": sv("Market Value of Common"),
        "Current Dividend Yield (TTM)": sv("Dividend Yield TTM"),
        "Current Dividend Yield": sv("Dividend Yield TTM"),
        "Current PE10 (PFFO10 for REITS) Percentile": percentile,
        "Current Dividend Rate": sv("Dividend Rate (TTM)"),
        "WACC": wacc / 100 if wacc is not None and wacc > 1 else wacc,
        "Current Status with PE10 Percentile": "Buy" if sv("PE10 Quantile Satisfied (Interpolation)") == "Yes" else "Out",
        "Current Status without PE10 Percentile": None,
        "Dividend Policy Satisfied": sv("Dividend Policy Satisfied"),
        "Latest Fiscal Quarter": f"{q_date:%m/%y} Q{quarter_key(quarter)[1]}" if hasattr(q_date, "strftime") else None,
        "Latest Annual Earnings Date": annual_date,
        "Expected Next Earnings Report Datetime": None,
        "Current Graham Instrinsic Value": None,
        "Graham Instrinsic Value in 7 Years": None,
        "Graham Expected Annualized Return": None,
        "Expected Return @ Current Price": None,
        "Expected Return Price Plus Dividends - Given Current Price": None,
        "Expected Return Price Plus Dividends - Given Max Entry Price": None,
        "Approximate Residual Earnings Value": None,
        "Extrapolated Price Plus Dividends": None,
        "Six Month Price Change": None,
        "Dividends Since": ws.cell(labels["Dividends Since"], 2).value if "Dividends Since" in labels else None,
    }

    # history stops at the quarter
    for r in range(date_row, scalar_start):
        for c in range(col + 1, max_col + 1):
            ws.cell(r, c).value = None

    # scalar block: override, else the same-named history row of the quarter, else empty
    table_start = None
    for r in range(scalar_start, (ws.max_row or 1) + 1):
        lab = ws.cell(r, 1).value
        if lab == _PE10_TABLE_LABEL or (lab is None and ws.cell(r, 2).value == _PE10_TABLE_LABEL):
            table_start = r
        if table_start and r >= table_start:
            break
        if not isinstance(lab, str):
            continue
        if lab in override:
            ws.cell(r, 2).value = override[lab]
        elif lab in series_rows and sv(lab) is not None:
            ws.cell(r, 2).value = sv(lab)
        else:
            ws.cell(r, 2).value = None
    # the sorted PE10 distribution (quarterly points up to the quarter)
    hdr = next((r for r in range(scalar_start, (ws.max_row or 1) + 1) if ws.cell(r, 2).value == _PE10_TABLE_LABEL), None)
    if hdr:
        for r in range(hdr + 1, (ws.max_row or 1) + 1):
            ws.cell(r, 1).value = ws.cell(r, 2).value = None
        for i, v in enumerate(pe10_hist):
            ws.cell(hdr + 1 + i, 1).value = i
            ws.cell(hdr + 1 + i, 2).value = v

    # metadata rows
    meta = {"Current Price (Live Price)", "Current Enterprise Value (not-diluted)", "Current Market Capitalization",
            "Expected Next Earnings Report Datetime", "Latest Fiscal Quarter", "Latest Annual Earnings Date"}
    for lab in meta:
        r = labels.get(lab)
        if r and r < date_row:
            ws.cell(r, 2).value = override.get(lab)
    ws.cell(13, 1).value = MARK.format(q=quarter)

    sm = wb["Summary"] if "Summary" in wb.sheetnames else None
    if sm is not None:
        for c in range(1, (sm.max_column or 1) + 1):
            h = sm.cell(1, c).value
            if h in override:
                sm.cell(2, c).value = override[h]
            elif isinstance(h, str) and h in series_rows and h not in ("Company", "Ticker"):
                sm.cell(2, c).value = sv(h)
            elif h not in ("Company", "Ticker", "Industry Sector", "Industry Subgroup", "Fiscal Year Closing"):
                sm.cell(2, c).value = None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return {
        "source": crf_path.name, "quarter": quarter, "quarter_end": str(q_date)[:10], "path": str(out_path),
        "price_quarter_average": price, "e10": e10, "pe10": pe10, "max_pe10_to_enter": max_pe,
        "max_price_to_buy": override["Max Current Price to Buy"], "first_exit_price": override["1st Exit Price"],
        "pe10_percentile_approx": percentile, "share_factor": share_factor,
    }
