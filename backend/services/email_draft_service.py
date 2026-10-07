"""Email draft that follows every analysis (quarter update, annual update, new company).

It replaces the old Word report. The draft is plain text that the analyst checks and forwards to the team, so for now it is saved as a
text file and as an .eml file addressed to the analyst (HAP_EMAIL_DRAFT_TO, default houda@vlixes.us). The .eml opens in a mail app as an
unsent draft. Nothing is sent by HAP.

All numbers come from the completed, recalculated workbook (cached values, read by Bloomberg field code and by label so a shifted row
does not break them). Fields that the analyst keeps in the company Google Sheet (market cap, TBV/P, Classified as, Status with PE10) are
passed in as `sheet_fields`; until the sheet is connected the workbook provides the market cap and TBV/P, and the other two are marked.
The narrative paragraphs (what drove the quarter, the moat, the conclusion) are drafted from the numbers with a bracketed line the
analyst completes; a model-written version replaces them when the API key is available.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from services.annual_period_service import detect_year_columns

DEFAULT_TO = "houda@vlixes.us"
MISSING = "n/a"

LQ_BS, LQ_IS, LQ_CF = "Last Quarter BS Standardized", "Last Quarter IS Standardized", "Last Quarter CF Standardized"
FY_BS, FY_IS, FY_CF = "Balance Sheet - Standardized", "Income - GAAP", "Cash Flow - Standardized"

# ---------------------------------------------------------------- formatting


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pct(v: float | None, digits: int = 2, sign: bool = False) -> str:
    if v is None:
        return MISSING
    return f"{v * 100:+.{digits}f}%" if sign else f"{v * 100:.{digits}f}%"


def money_m(v: float | None) -> str:
    """Statement values are in millions."""
    if v is None:
        return MISSING
    return f"-${abs(v):,.1f}M" if v < 0 else f"${v:,.1f}M"


def money_b(v_millions: float | None) -> str:
    return MISSING if v_millions is None else f"~${v_millions / 1000:,.2f}B"


def usd(v: float | None) -> str:
    if v is None:
        return MISSING
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def ratio(v: float | None, suffix: str = "") -> str:
    return MISSING if v is None else f"{v:,.2f}{suffix}"


def change(cur: float | None, prior: float | None) -> float | None:
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / abs(prior)


# ---------------------------------------------------------------- workbook reading


def _find_code_row(ws, code: str) -> int | None:
    for r in range(1, min(ws.max_row or 1, 200) + 1):
        if str(ws.cell(r, 2).value or "").strip() == code:
            return r
    return None


def _find_label_row(ws, label: str, start: int = 1, exact: bool = True) -> int | None:
    want = label.lower().strip()
    for r in range(start, min(ws.max_row or 1, 200) + 1):
        have = " ".join(str(ws.cell(r, 1).value or "").lower().split())
        if (have == want) if exact else (want in have):
            return r
    return None


def _year_columns(ws, header_rows=(1, 2, 3, 4)) -> dict[str, int]:
    """FY label ('FY 2025' or 'FY2025') -> column, from the header rows."""
    import re

    out: dict[str, int] = {}
    for r in header_rows:
        for c in range(2, min(ws.max_column or 2, 60) + 1):
            m = re.fullmatch(r"FY\s*(\d{4})", str(ws.cell(r, c).value or "").strip())
            if m:
                out[f"FY{m.group(1)}"] = c
    return out


def _fy_pair(ws) -> tuple[int | None, int | None, str | None]:
    """(latest FY column, prior FY column, latest FY token) read from the header row."""
    cols = _year_columns(ws)
    if not cols:
        return None, None, None
    ordered = sorted(cols)
    latest = ordered[-1]
    prior = ordered[-2] if len(ordered) > 1 else None
    return cols[latest], (cols[prior] if prior else None), latest


def _value(ws, row: int | None, col: int | None) -> float | None:
    return _num(ws.cell(row, col).value) if row and col else None


@dataclass
class Facts:
    """Everything the three templates need, read once from the workbook."""

    ticker: str = ""
    company: str = ""
    fy: str | None = None                      # latest fiscal year token, e.g. FY2025
    quarter_label: str | None = None           # e.g. "2026 Q3"
    quarter_number: int | None = None
    quarter_year: int | None = None
    price: float | None = None
    market_cap_m: float | None = None
    tbv_p: float | None = None
    pe10_percentile: float | None = None
    max_entry: float | None = None
    ev_mos: float | None = None
    expected_return: float | None = None
    expected_return_adjusted: bool = False
    graham_entry: float | None = None
    fy_metrics: dict[str, Any] = field(default_factory=dict)
    fy_changes: dict[str, Any] = field(default_factory=dict)
    q_yoy: dict[str, Any] = field(default_factory=dict)
    q_qoq: dict[str, Any] = field(default_factory=dict)
    ytd_label: str = ""
    segments: list[tuple[str, float | None]] = field(default_factory=list)
    projection: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    fy_series: dict[str, list[tuple[str, float | None]]] = field(default_factory=dict)


def read_facts(workbook_path: Path, *, ticker: str, company: str = "") -> Facts:
    wb = load_workbook(workbook_path, data_only=True)
    f = Facts(ticker=ticker.upper(), company=company)
    try:
        if "Inputs" in wb.sheetnames:
            inp = wb["Inputs"]
            f.price = _num(inp["B63"].value)
            f.max_entry = _num(inp["B67"].value)
            f.pe10_percentile = _num(inp["B72"].value)
        _read_valuation(wb, f)
        _read_fy(wb, f)
        _read_quarter(wb, f)
        f.expected_return_adjusted = _er_adjusted(wb)
    finally:
        wb.close()
    return f


def _read_valuation(wb, f: Facts) -> None:
    if "Enterprise Value" in wb.sheetnames:
        ev = wb["Enterprise Value"]
        r = _find_label_row(ev, "Market Cap")
        f.market_cap_m = _value(ev, r, 2)
        r = _find_label_row(ev, "Margin of Safety")
        f.ev_mos = _value(ev, r, 2)
        r = _find_label_row(ev, "Entry target price")
        f.graham_entry = _value(ev, r, 2)
    if "Expected Returns & Buybacks" in wb.sheetnames:
        er = wb["Expected Returns & Buybacks"]
        # headers sit in row 13, values in row 14 (Average ROE ... Expected Annual Return)
        # the analyst's Expected Return is the "Expected Return Price + Dividends" column (F14); the plain price-only column (E14) is the fallback
        for wanted in ("expected return price + dividends", "expected annual return"):
            for c in range(1, 8):
                if str(er.cell(13, c).value or "").strip().lower() == wanted and f.expected_return is None:
                    f.expected_return = _num(er.cell(14, c).value)
    if "Final Metrics" in wb.sheetnames and f.price:
        fm = wb["Final Metrics"]
        lat, _prior, _tok = _fy_pair(fm)
        r = _find_label_row(fm, "TBV per Share")
        tbv = _value(fm, r, lat)
        if tbv is not None:
            f.tbv_p = tbv / f.price


def _er_adjusted(wb) -> bool:
    if "HAP Adjustments" not in wb.sheetnames:
        return False
    for row in wb["HAP Adjustments"].iter_rows(values_only=True):
        if row and any(str(x or "") == "Expected return input" for x in row) and any(str(x or "") == "Applied" for x in row):
            return True
    return False


def _read_fy(wb, f: Facts) -> None:
    m: dict[str, Any] = {}
    if "Final Metrics" in wb.sheetnames:
        fm = wb["Final Metrics"]
        lat, prior, token = _fy_pair(fm)
        f.fy = token
        avg_col = 2
        for key, label in (("roce", "ROCE"), ("roic_wacc", "ROIC in - WACC"), ("interest_cov", "Interest Coverage Ratio")):
            r = _find_label_row(fm, label)
            m[key] = (_value(fm, r, lat), _value(fm, r, prior), _value(fm, r, avg_col))
        for key, label in (("gross_margin", "Gross Margin"), ("op_margin", "Operating Margin")):
            r = _find_label_row(fm, label)
            m[key] = (_value(fm, r, lat), _value(fm, r, prior), _value(fm, r, avg_col))
        years = _year_columns(fm)
        for key, label in (("roce", "ROCE"), ("roic_wacc", "ROIC in - WACC")):
            r = _find_label_row(fm, label)
            f.fy_series[key] = [(fy, _value(fm, r, years[fy])) for fy in sorted(years)]
    if "All Ratios" in wb.sheetnames:
        ar = wb["All Ratios"]
        lat, prior, token = _fy_pair(ar)
        f.fy = f.fy or token
        for key, label in (("a_l", "Assets/Liabilities"), ("debt_assets", "Debt/Assets"), ("net_margin", "Net Margin"),
                           ("interest_cov_ar", "Interest Coverage Ratio")):
            r = _find_label_row(ar, label)
            m[key] = (_value(ar, r, lat), _value(ar, r, prior), _value(ar, r, 2))
        for key, label in (("revenue", "Revenue"), ("net_income", "Net Income"), ("eps", "EPS diluted")):
            r = _find_label_row(ar, label)
            m[key] = (_value(ar, r, lat), _value(ar, r, prior), None)
    f.fy_metrics = m

    ch: dict[str, Any] = {}
    for sheet, code, key in ((FY_CF, "CF_CASH_FROM_OPER", "cfo"), (FY_BS, "BS_PURE_RETAINED_EARNINGS", "retained"),
                             (FY_BS, "TOTAL_EQUITY", "equity")):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        cols = {k: v for k, v in detect_year_columns(ws, wb).items() if str(k).startswith("FY")}
        r = _find_code_row(ws, code)
        filled = [_value(ws, r, cols[k]) for k in sorted(cols) if _value(ws, r, cols[k]) is not None]   # skip a blank new-year column
        ch[key] = (filled[-1], filled[-2]) if len(filled) > 1 else (None, None)
    f.fy_changes = ch


def _read_quarter(wb, f: Facts) -> None:
    import re

    if LQ_IS in wb.sheetnames:
        ws = wb[LQ_IS]
        for c in range(2, 10):
            for r in (1, 2, 3, 4, 5, 6, 7, 8, 9):
                text = str(ws.cell(r, c).value or "")
                m = re.search(r"FQ(\d)\s*(\d{4})", text)
                year, quarter = (m.group(2), m.group(1)) if m else (None, None)
                if not m:                                    # quarterly-update workbooks write the header as "2026 Q3"
                    m2 = re.search(r"(\d{4})\s*Q(\d)", text)
                    year, quarter = (m2.group(1), m2.group(2)) if m2 else (None, None)
                if year and f.quarter_label is None:
                    f.quarter_number, f.quarter_year, f.quarter_label = int(quarter), int(year), f"{year} Q{quarter}"
        f.ytd_label = {1: "3M", 2: "6M", 3: "9M", 4: "12M"}.get(f.quarter_number or 0, "YTD")
        y: dict[str, Any] = {}
        for key, code in (("revenue", "SALES_REV_TURN"), ("op_income", "IS_OPER_INC"), ("net_income", "NET_INCOME"),
                          ("net_common", "EARN_FOR_COMMON"), ("eps", "IS_DILUTED_EPS"), ("gross_profit", "GROSS_PROFIT")):
            r = _find_code_row(ws, code)
            if r is None:
                continue
            y[key] = {
                "q": (_value(ws, r, 3), _value(ws, r, 4)),
                "ytd": (_value(ws, r, 7), _value(ws, r, 8)),
            }
        f.q_yoy = y
    if LQ_CF in wb.sheetnames:
        ws = wb[LQ_CF]
        r = _find_code_row(ws, "CF_CASH_FROM_OPER")
        if r:
            f.q_yoy["cfo"] = {"ytd": (_value(ws, r, 3), _value(ws, r, 4))}
    if LQ_BS in wb.sheetnames:
        ws = wb[LQ_BS]
        q: dict[str, Any] = {}
        for key, code in (("assets", "BS_TOT_ASSET"), ("liabilities", "BS_TOT_LIAB2"), ("retained", "BS_PURE_RETAINED_EARNINGS"),
                          ("equity", "TOTAL_EQUITY")):
            r = _find_code_row(ws, code)
            q[key] = (_value(ws, r, 3), _value(ws, r, 4)) if r else (None, None)
        f.q_qoq = q


# ---------------------------------------------------------------- shared blocks


@dataclass
class SheetFields:
    """Values the analyst keeps in the company Google Sheet. Any field left None falls back to the workbook or is marked."""

    market_cap_text: str | None = None
    tbv_p_text: str | None = None
    classified_as: str | None = None
    pe10_status: str | None = None


def pe10_status(f: Facts) -> str:
    """The status comes from the analyst's sheet; it is not derived from the price (the sheet applies more filters than price versus max)."""
    return "[Google Sheet]"


def _header_block(f: Facts, sheet: SheetFields | None) -> list[str]:
    sheet = sheet or SheetFields()
    cap = sheet.market_cap_text or money_b(f.market_cap_m)
    tbv = sheet.tbv_p_text or pct(f.tbv_p)
    return [
        f"Market Cap: {cap}",
        f"Current TBV/P: {tbv}",
        f"Classified as: {sheet.classified_as or '[Google Sheet]'}",
        f"Status with PE10: {sheet.pe10_status or pe10_status(f)}",
    ]


def _price_block(f: Facts) -> list[str]:
    er = pct(f.expected_return)
    if f.expected_return is not None and f.expected_return_adjusted:
        er += " (adjusted)"
    return [
        "Price & MoS",
        f"Current price: {usd(f.price)}. PE10 percentile is at {pct(f.pe10_percentile)}. Max entry price {usd(f.max_entry)}.",
        f"EV MoS: {pct(f.ev_mos, 2, sign=True)}",
        f"Expected Return: {er}",
        f"Graham Entry Price: {usd(f.graham_entry)}",
    ]


def _avg_line(label: str, triple: tuple, fy: str, prior_fy: str, avg: bool = True) -> str:
    cur, prior, average = triple
    parts = [f"{pct(prior)} in {prior_fy}"] if prior is not None else []
    if avg and average is not None:
        parts.append(f"10-year average {pct(average)}")
    tail = f" ({', '.join(parts)})" if parts else ""
    return f"{label}: {pct(cur)}{tail}"


def _fy_names(f: Facts) -> tuple[str, str]:
    fy = f.fy or "FY"
    try:
        prior = f"FY{int(fy[2:]) - 1}"
    except ValueError:
        prior = "the prior year"
    return fy, prior


def _fy_metrics_block(f: Facts, title: str) -> list[str]:
    fy, prior = _fy_names(f)
    m = f.fy_metrics
    lines = [title]
    if "roce" in m:
        lines.append(_avg_line("ROCE", m["roce"], fy, prior))
    if "roic_wacc" in m:
        lines.append(_avg_line("ROIC-WACC", m["roic_wacc"], fy, prior))
    if "a_l" in m:
        lines.append(f"A/L: {ratio(m['a_l'][0])}")
    gm = m.get("gross_margin", (None,))[0]
    om = m.get("op_margin", (None,))[0]
    nm = m.get("net_margin", (None,))[0]
    lines.append(f"Margins: (Gross {pct(gm, 1)} — Op {pct(om)} — Net {pct(nm)})")
    if "debt_assets" in m:
        lines.append(f"Debt/Asset: {pct(m['debt_assets'][0])}")
    cov = (m.get("interest_cov") or m.get("interest_cov_ar") or (None,))[0]
    lines.append(f"Interest Coverage ratio: {ratio(cov, 'x')}")
    return lines


def _fy_vs_block(f: Facts) -> list[str]:
    fy, prior = _fy_names(f)
    m, ch = f.fy_metrics, f.fy_changes
    lines = [f"{fy} vs. {prior}"]
    for label, key in (("Revenue", "revenue"), ("Net Income", "net_income"), ("EPS", "eps")):
        cur, pri, _ = m.get(key, (None, None, None))
        lines.append(f"{label}: {pct(change(cur, pri), 2, sign=True)}")
    cur, pri = ch.get("cfo", (None, None))
    lines.append(f"Cash from Op: {pct(change(cur, pri), 2, sign=True)}")
    a_l = m.get("a_l", (None, None, None))
    lines.append(f"A/L: {ratio(a_l[0])} from {ratio(a_l[1])}")
    for label, key in (("Retained Earnings", "retained"), ("Equity", "equity")):
        cur, pri = ch.get(key, (None, None))
        lines.append(f"{label}: {pct(change(cur, pri), 2, sign=True)}")
    return lines


def _periods(f: Facts) -> tuple[str, str, str]:
    """('Q3 2026', 'Q3 2025', 'Q2 2026'): this quarter, the same quarter last year, the previous quarter."""
    q, y = f.quarter_number or 0, f.quarter_year or 0
    prev = f"Q{q - 1} {y}" if q > 1 else f"Q4 {y - 1}"
    return f"Q{q} {y}", f"Q{q} {y - 1}", prev


def _quarter_vs_block(f: Facts, heading: str, *, with_ytd: bool, margin_digits: int = 2) -> list[str]:
    y = f.q_yoy
    lines = [heading]

    def cmp_line(label: str, pair: tuple, money: bool, per_share: bool = False) -> str:
        cur, pri = pair
        if cur is None and pri is None:
            return ""
        fmt = usd if per_share else money_m
        return f"{label} {pct(change(cur, pri), 2, sign=True)} ({fmt(cur)} vs. {fmt(pri)})"

    basis = "ytd" if with_ytd else "q"
    ni_key, ni_label = "net_income", "Net Income (GAAP)"
    common, plain = y.get("net_common", {}).get(basis), y.get("net_income", {}).get(basis)
    if common and plain and common[0] is not None and plain[0] is not None and abs(common[0] - plain[0]) > 0.05:
        ni_key, ni_label = "net_common", "Net Income available to Common (after preferred dividends)"
    for label, key, per_share in (("Revenue", "revenue", False), (ni_label, ni_key, False), ("EPS Diluted (GAAP)", "eps", True)):
        if key in y and y[key].get(basis):
            line = cmp_line(label, y[key][basis], True, per_share)
            if line:
                lines.append(line)
    if "cfo" in y and None not in y["cfo"]["ytd"]:
        cur, pri = y["cfo"]["ytd"]
        lines.append(f"Cash from Ops {pct(change(cur, pri), 2, sign=True)} ({money_m(cur)} vs. {money_m(pri)})")
    def pick(key: str):
        d = y.get(key, {})
        return d.get(basis) or d.get("q") or d.get("ytd")      # in Q1 the year-to-date columns are the quarter

    rev, opi, ni, gp = pick("revenue"), pick("op_income"), pick("net_income"), pick("gross_profit")
    def margin(label: str, num) -> None:
        if rev and num and None not in (rev[0], rev[1], num[0], num[1]) and rev[0] and rev[1]:
            lines.append(f"{label} {pct(num[0] / rev[0], margin_digits)} vs. {pct(num[1] / rev[1], margin_digits)}")

    margin("Gross Margin", gp)
    margin("Operating Margin", opi)
    margin("Net Margin", ni)
    return lines if len(lines) > 1 else []        # nothing to compare: leave the whole block out


def _qoq_block(f: Facts, heading: str) -> list[str]:
    q = f.q_qoq
    lines = [heading]
    a, li = q.get("assets", (None, None)), q.get("liabilities", (None, None))
    cur = a[0] / li[0] if a[0] and li[0] else None
    pri = a[1] / li[1] if a[1] and li[1] else None
    lines.append(f"A/L: {ratio(cur)} vs. {ratio(pri)}")
    for label, key in (("Retained earnings", "retained"), ("Equity", "equity")):
        c, p = q.get(key, (None, None))
        lines.append(f"{label}: {pct(change(c, p), 2, sign=True)}")
    return lines


# ---------------------------------------------------------------- templates


def _join(sections: list[list[str]]) -> str:
    return "\n\n".join("\n".join(s) for s in sections if s) + "\n"


def _description(f: Facts, description: str | None) -> str:
    return description or "[one-line description of the company]"


def render_quarter(f: Facts, *, sheet: SheetFields | None = None, highlights: str | None = None) -> tuple[str, str]:
    q = f.quarter_number or 0
    cur, last_year, prev = _periods(f)
    ytd = f.ytd_label if q >= 2 else ""
    ytd_note = f" ({ytd} to {ytd})" if ytd else ""
    intro = ["Dear All,", "", f"Please find attached the quarter update of {f.ticker}."] + _header_block(f, sheet)
    from services.email_narrative import quarter_highlights

    hl = [f"{f.quarter_label or 'Latest quarter'} Financial Highlights",
          highlights or quarter_highlights(f) or "[What drove the quarter: segment growth and the reasons behind it. To be completed by the analyst.]"]
    proj: list[str] = []
    if f.projection:
        p = f.projection
        # the projection report may lack last year's figures; the workbook's last full fiscal year has them
        prior_spread = p.get("prior_spread") if p.get("prior_spread") is not None else f.fy_metrics.get("roic_wacc", (None,))[0]
        prior_roce = p.get("prior_roce") if p.get("prior_roce") is not None else f.fy_metrics.get("roce", (None,))[0]
        proj = [f"{p.get('next_fy', 'Next year')} Projection",
                f"Projected ROIC - WACC at {pct(p.get('roic_wacc'))} ({pct(prior_spread)} in {p.get('fy', 'last year')})",
                f"Projected ROCE at {pct(p.get('roce'))} ({pct(prior_roce)} in {p.get('fy', 'last year')})"]
    sections = [
        intro, hl, proj,
        _quarter_vs_block(f, f"Comparison {cur} to {last_year}{ytd_note}", with_ytd=q >= 2),
        _qoq_block(f, f"Comparison {cur} to {prev}"),
        _price_block(f),
        ["Very best,"],
    ]
    return f"{f.ticker} quarter update {cur}", _join(sections)


def render_annual(f: Facts, *, sheet: SheetFields | None = None, description: str | None = None, highlights: str | None = None) -> tuple[str, str]:
    fy, _prior = _fy_names(f)
    m = f.fy_metrics
    rev, ni, eps = m.get("revenue", (None,))[0], m.get("net_income", (None,))[0], m.get("eps", (None,))[0]
    from services.email_narrative import annual_highlights

    intro = ["Dear All,", "", f"Please find the annual update for {f.ticker} below ({_description(f, description)})"] + _header_block(f, sheet)
    hl = [f"{fy} Highlights", f"Net Revenue: {money_m(rev)}", f"Net Income: {money_m(ni)}", f"EPS: {usd(eps)}", "",
          highlights or annual_highlights(f) or "[What drove the year: demand, margins and the reasons behind them. To be completed by the analyst.]"]
    sections = [intro, hl, _fy_metrics_block(f, f"{fy} Metrics"), _fy_vs_block(f), _price_block(f), ["Very best,"]]
    return f"{f.ticker} annual update {fy}", _join(sections)


def render_new_company(f: Facts, *, sheet: SheetFields | None = None, description: str | None = None,
                       highlights: str | None = None, conclusion: str | None = None) -> tuple[str, str]:
    fy, _prior = _fy_names(f)
    q = f.quarter_number or 0
    cur, last_year, prev = _periods(f)
    ytd = f.ytd_label if q >= 2 else ""
    ytd_note = f" ({ytd} to {ytd})" if ytd else ""
    from services.email_narrative import new_company_conclusion, new_company_highlights

    name = f"{f.ticker}: {f.company}" if f.company else f.ticker
    subject_line = f"{f.ticker}: {description}" if description else f"{name}, [one-line description of the company]"
    intro = ["Dear All,", "", f"Please find attached the analysis of {subject_line}"] + _header_block(f, sheet)
    hl = ["Highlights", highlights or new_company_highlights(f) or "[Competitive position and the main story of the last years: to be completed by the analyst.]"]
    sections = [
        intro, hl, _fy_metrics_block(f, fy), _fy_vs_block(f),
        _quarter_vs_block(f, f"{cur} vs. {last_year}{ytd_note}", with_ytd=q >= 2, margin_digits=1),
        _qoq_block(f, f"{cur} vs. {prev}"),
        _price_block(f),
        ["Conclusion", conclusion or new_company_conclusion(f) or "[Overall view of the company: to be completed by the analyst.]"],
        ["Let me know if you have any questions.", "", "Very best"],
    ]
    return f"{f.ticker} new company analysis", _join(sections)


# ---------------------------------------------------------------- writing


class EmailDraftService:
    """Builds the draft from a completed workbook and saves it next to the other deliverables."""

    def produce(
        self,
        *,
        analysis_type: str,
        ticker: str,
        workbook_path: Path,
        output_dir: Path,
        company: str = "",
        sheet: SheetFields | None = None,
        description: str | None = None,
        highlights: str | None = None,
        conclusion: str | None = None,
        projection: dict[str, Any] | None = None,
        base_name: str | None = None,
        fiscal_year: int | None = None,
        fiscal_quarter: int | None = None,
        attachments: list[Path] | None = None,
    ) -> dict[str, str]:
        facts = read_facts(workbook_path, ticker=ticker, company=company)
        if fiscal_year and fiscal_quarter in (1, 2, 3):
            # the pipeline knows the period it analysed: that wins over what the statements' headers say
            facts.quarter_number, facts.quarter_year = int(fiscal_quarter), int(fiscal_year)
            facts.quarter_label = f"{fiscal_year} Q{fiscal_quarter}"
            facts.ytd_label = {1: "3M", 2: "6M", 3: "9M"}[int(fiscal_quarter)]
        if projection:
            facts.projection = projection
        if description is None and analysis_type in ("annual_update", "new_company"):
            description = self._describe(analysis_type, ticker, company or facts.company, output_dir)
        if analysis_type == "quarterly_update":
            subject, body = render_quarter(facts, sheet=sheet, highlights=highlights)
        elif analysis_type == "annual_update":
            subject, body = render_annual(facts, sheet=sheet, description=description, highlights=highlights)
        else:
            subject, body = render_new_company(facts, sheet=sheet, description=description, highlights=highlights, conclusion=conclusion)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = base_name or f"Email draft {subject}"
        txt = output_dir / f"{stem}.txt"
        txt.write_text(f"Subject: {subject}\n\n{body}", encoding="utf-8")
        eml = output_dir / f"{stem}.eml"
        msg = EmailMessage()
        msg["To"] = os.environ.get("HAP_EMAIL_DRAFT_TO", DEFAULT_TO)
        msg["Subject"] = subject
        msg["X-Unsent"] = "1"          # opens as an editable draft in Outlook and other mail apps
        msg.set_content(body)
        for path in attachments or []:
            path = Path(path)
            if not path.is_file():
                continue
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            main, _, sub = kind.partition("/")
            msg.add_attachment(path.read_bytes(), maintype=main, subtype=sub or "octet-stream", filename=path.name)
        eml.write_bytes(bytes(msg))
        return {"subject": subject, "text_path": str(txt), "eml_path": str(eml), "body": body}

    @staticmethod
    def _describe(analysis_type: str, ticker: str, company: str, output_dir: Path) -> str | None:
        """The one-line description taken from the company's own 10-K (see company_description_service)."""
        try:
            from services.company_description_service import describe

            found = describe(ticker, output_dir)
            name = company or found.name or ticker
            return found.annual(name) if analysis_type == "annual_update" else found.new_company(name)
        except Exception:  # noqa: BLE001 - the description is optional; the bracketed line stays
            return None

    def produce_safe(self, **kwargs: Any) -> dict[str, Any]:
        """Like produce(), but a problem with the email never stops an analysis: the paths are None and `error` says what went wrong."""
        try:
            return self.produce(**kwargs)
        except Exception as exc:  # noqa: BLE001 - the email is advisory
            return {"subject": None, "text_path": None, "eml_path": None, "body": None, "error": f"{type(exc).__name__}: {exc}"}


def file_name(path: str | None) -> str | None:
    return Path(path).name if path else None
