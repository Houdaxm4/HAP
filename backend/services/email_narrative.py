"""Plain-language highlights and conclusion for the emails, written from the workbook numbers only (no AI model, no outside news).

Every sentence states a figure and how it compares: with the year before, with the same period last year, or with the company's own
10-year average. Nothing is claimed about causes (demand, competition, management) because the numbers do not say why.
When there are too few figures for a section, the function returns an empty string and the email keeps its bracketed line for the analyst.
"""

from __future__ import annotations

from services.email_draft_service import Facts, change, money_m, pct, usd


def _move(value: float | None, up: str, down: str, flat: str = "was little changed") -> str:
    if value is None:
        return ""
    if abs(value) < 0.005:
        return flat
    return up if value > 0 else down


def _vs_average(value: float | None, average: float | None, label: str) -> str:
    if value is None or average is None:
        return ""
    gap = value - average
    side = "above" if gap > 0.0025 else "below" if gap < -0.0025 else "in line with"
    return f"{label} at {pct(value)}, {side} its 10-year average of {pct(average)}" if side != "in line with" else f"{label} at {pct(value)}, in line with its 10-year average of {pct(average)}"


def _join(sentences: list[str]) -> str:
    return " ".join(s.strip() for s in sentences if s and s.strip())


def annual_highlights(f: Facts) -> str:
    m = f.fy_metrics
    rev, ni, eps = m.get("revenue", (None, None, None)), m.get("net_income", (None, None, None)), m.get("eps", (None, None, None))
    sentences: list[str] = []
    rev_chg = change(rev[0], rev[1])
    if rev_chg is not None:
        verb = "grew" if rev_chg > 0 else "declined"
        sentences.append(f"Revenue {verb} {pct(abs(rev_chg), 1)} to {money_m(rev[0])}.")
    ni_chg, eps_chg = change(ni[0], ni[1]), change(eps[0], eps[1])
    if ni_chg is not None and eps_chg is not None:
        verb = "rose" if ni_chg > 0 else "fell"
        sentences.append(f"Net income {verb} {pct(abs(ni_chg), 1)} to {money_m(ni[0])} and diluted EPS {pct(abs(eps_chg), 1)} {'higher' if eps_chg > 0 else 'lower'} at {usd(eps[0])}.")
    gm, om = m.get("gross_margin", (None, None, None)), m.get("op_margin", (None, None, None))
    if gm[0] is not None and gm[1] is not None:
        sentences.append(f"Gross margin {_move(gm[0] - gm[1], 'improved', 'slipped', 'held')} to {pct(gm[0], 1)} from {pct(gm[1], 1)}.")
    if om[0] is not None and om[1] is not None:
        sentences.append(f"Operating margin was {pct(om[0], 1)} against {pct(om[1], 1)} the year before.")
    rw = m.get("roic_wacc", (None, None, None))
    roce = m.get("roce", (None, None, None))
    returns = []
    if rw[0] is not None:
        sign = "negative" if rw[0] < 0 else "positive"
        returns.append(f"ROIC-WACC is {sign} at {pct(rw[0])}" + (f" ({pct(rw[2])} on a 10-year average)" if rw[2] is not None else ""))
    roce_text = _vs_average(roce[0], roce[2], "ROCE")
    if roce_text:
        returns.append(roce_text)
    if returns:
        sentences.append("; ".join(returns) + ".")
    return _join(sentences) if len(sentences) >= 2 else ""


def quarter_highlights(f: Facts) -> str:
    y = f.q_yoy
    basis = "ytd" if (f.quarter_number or 0) >= 2 else "q"
    span = f.ytd_label if basis == "ytd" else "quarter"

    def pair(key: str):
        d = y.get(key, {})
        return d.get(basis) or d.get("q") or d.get("ytd")

    sentences: list[str] = []
    rev, ni, eps, opi = pair("revenue"), pair("net_income"), pair("eps"), pair("op_income")
    if rev and None not in rev:
        c = change(*rev)
        if c is not None:
            sentences.append(f"Revenue for the {span} {'grew' if c > 0 else 'declined'} {pct(abs(c), 1)} to {money_m(rev[0])} (from {money_m(rev[1])}).")
    if ni and eps and None not in ni and None not in eps:
        cn, ce = change(*ni), change(*eps)
        if cn is not None and ce is not None:
            sentences.append(f"Net income {'rose' if cn > 0 else 'fell'} {pct(abs(cn), 1)} and diluted EPS {'rose' if ce > 0 else 'fell'} {pct(abs(ce), 1)} to {usd(eps[0])}.")
    if rev and opi and None not in rev and None not in opi and rev[0] and rev[1]:
        sentences.append(f"Operating margin was {pct(opi[0] / rev[0], 1)} against {pct(opi[1] / rev[1], 1)} a year earlier.")
    cfo = y.get("cfo", {}).get("ytd")
    if cfo and None not in cfo:
        c = change(*cfo)
        if c is not None:
            sentences.append(f"Cash from operations {'rose' if c > 0 else 'fell'} {pct(abs(c), 1)} to {money_m(cfo[0])}.")
    if f.projection and f.projection.get("roic_wacc") is not None:
        p = f.projection
        sentences.append(f"Projected ROIC-WACC is {pct(p['roic_wacc'])} against {pct(p.get('prior_spread'))} in {p.get('fy', 'the last fiscal year')}.")
    return _join(sentences) if len(sentences) >= 2 else ""


def new_company_highlights(f: Facts) -> str:
    sentences: list[str] = []
    series = f.fy_series.get("roic_wacc") or []
    values = [v for _fy, v in series if v is not None]
    if len(values) >= 5:
        lo, hi = min(values), max(values)
        latest = series[-1]
        sentences.append(
            f"ROIC-WACC has ranged between {pct(lo)} and {pct(hi)} over the last {len(values)} years and was {pct(latest[1])} in {latest[0]}."
        )
    rc = f.fy_metrics.get("roce", (None, None, None))
    text = _vs_average(rc[0], rc[2], "ROCE")
    if text:
        sentences.append(text[0].upper() + text[1:] + ".")
    rev = f.fy_metrics.get("revenue", (None, None, None))
    c = change(rev[0], rev[1])
    if c is not None:
        sentences.append(f"Revenue {'grew' if c > 0 else 'declined'} {pct(abs(c), 1)} in {f.fy or 'the latest fiscal year'}, to {money_m(rev[0])}.")
    da, cov = f.fy_metrics.get("debt_assets", (None,))[0], (f.fy_metrics.get("interest_cov") or f.fy_metrics.get("interest_cov_ar") or (None,))[0]
    if da is not None and cov is not None:
        sentences.append(f"Debt is {pct(da, 1)} of assets and interest is covered {cov:,.1f} times.")
    return _join(sentences) if len(sentences) >= 2 else ""


def new_company_conclusion(f: Facts) -> str:
    if f.price is None or f.max_entry is None:
        return ""
    side = "below" if f.price <= f.max_entry else "above"
    sentences = [
        f"At {usd(f.price)} the stock trades {side} its maximum entry price of {usd(f.max_entry)}, with the PE10 percentile at {pct(f.pe10_percentile)}."
    ]
    if f.ev_mos is not None:
        sentences.append(f"The enterprise-value margin of safety is {pct(f.ev_mos, 1, sign=True)} and the Graham entry price is {usd(f.graham_entry)}.")
    if f.expected_return is not None:
        adjusted = " (adjusted)" if f.expected_return_adjusted else ""
        sentences.append(f"The expected annual return is {pct(f.expected_return)}{adjusted}.")
    rw = f.fy_metrics.get("roic_wacc", (None, None, None))
    if rw[0] is not None:
        sentences.append(f"Returns on invested capital are {'below' if rw[0] < 0 else 'above'} the cost of capital ({pct(rw[0])} in {f.fy or 'the latest fiscal year'}).")
    return _join(sentences)
