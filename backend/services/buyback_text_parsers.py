"""Extra ways to read annual share repurchases from 10-K text (shares and dollars in millions).

All three return fiscal year -> list of (shares_millions, dollars_millions or None). A pair is only used after the caller checks it against
the cash-flow dollars (dollars within 6%) or, for pairs without dollars, against a plausible price per share.

  parse_multi_year_repurchases      "In 2025, 2024 and 2023, we repurchased 2.7 million, 433 thousand and 399 thousand shares,
                                     respectively ... at a total cost of $365.0 million, $68.6 million and $47.6 million, respectively."
  parse_annual_shares_narrative     "Timken also repurchased 779,300 common shares during the year." (the year is the filing's year)
  parse_equity_statement_repurchases  the "Treasury stock acquired  <shares>  (<amount>)" row of the statement of stockholders' equity,
                                     one per fiscal year between two "Balance, June 30, <year>" rows
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<!\d)\.(?!\d)(?=\s|$)")
_YEARS = r"(?P<years>20\d\d(?:\s*,\s*(?:and\s+)?20\d\d|\s+and\s+20\d\d)*)"
_MULTI_HEAD = re.compile(
    r"(?:in|during)\s+(?:the\s+)?(?:(?:fiscal\s+)?years?\s+(?:ended\s+[A-Za-z]+\s+\d{1,2},?\s*)?)?" + _YEARS +
    r"\s*,?\s+(?:we|the\s+company|company)\s+(?:re)?purchased\s+(?:approximately\s+)?",
    re.IGNORECASE,
)
_SHARE_AMOUNT = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|thousand)?", re.IGNORECASE)
_DOLLAR_AMOUNT = re.compile(r"\$\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|billion|thousand)?", re.IGNORECASE)
_EXCLUDE = re.compile(r"authoriz|up to|may purchase|may repurchase|since |inception|program to date|cumulative", re.IGNORECASE)


def _shares_m(num: str, unit: str | None) -> float | None:
    value = float(num.replace(",", ""))
    unit = (unit or "").lower()
    if unit == "million":
        return value
    if unit == "thousand":
        return value / 1_000.0
    return value / 1_000_000.0 if value >= 10_000 else None        # a bare number below 10,000 could be thousands: not guessed


def _dollars_m(num: str, unit: str | None) -> float:
    value = float(num.replace(",", ""))
    unit = (unit or "").lower()
    return {"billion": value * 1_000.0, "million": value, "thousand": value / 1_000.0}.get(unit, value / 1_000_000.0 if value >= 10_000 else value)


def _sentence_start(text: str, pos: int) -> int:
    """Start of the sentence that contains pos (just after the previous full stop that is not a decimal point)."""
    last = 0
    for m in _SENTENCE_END.finditer(text, max(0, pos - 600), pos):
        last = m.end()
    return last or max(0, pos - 600)


def _sentence(text: str, start: int) -> str:
    end = _SENTENCE_END.search(text, start)
    return text[start: end.start() if end else min(len(text), start + 900)]


def parse_multi_year_repurchases(text: str) -> dict[int, list[tuple[float, float | None]]]:
    out: dict[int, list[tuple[float, float | None]]] = {}
    for head in _MULTI_HEAD.finditer(text):
        years = [int(y) for y in re.findall(r"20\d\d", head.group("years"))]
        sentence = _sentence(text, head.end())
        if _EXCLUDE.search(text[head.start(): head.end() + len(sentence)]):
            continue
        shares_part = re.split(r"\bshares\b", sentence, maxsplit=1, flags=re.IGNORECASE)
        if len(shares_part) < 2:
            continue
        before, after = shares_part
        amounts = [_shares_m(m.group("num"), m.group("unit")) for m in _SHARE_AMOUNT.finditer(before)]
        # the words 'common' or 'of our' can sit between the numbers and 'shares'; only numbers count
        amounts = [a for a in amounts if a is not None]
        dollars = [_dollars_m(m.group("num"), m.group("unit")) for m in _DOLLAR_AMOUNT.finditer(after)]
        if len(amounts) != len(years):
            continue
        if len(dollars) != len(years):
            dollars = [None] * len(years)
        for year, shares, amount in zip(years, amounts, dollars):
            pair = (round(shares, 6), None if amount is None else round(amount, 6))
            if pair not in out.setdefault(year, []):
                out[year].append(pair)
    return out


_ANNUAL_NARRATIVE = re.compile(
    r"(?:the\s+company|we|[A-Z][A-Za-z]+(?:\s+also)?)\s+(?:also\s+)?repurchased\s+(?:approximately\s+)?"
    r"(?:(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|thousand)?|(?P<half>half\s+a\s+million))\s+"
    r"(?:of\s+(?:its|our)\s+)?(?:common\s+)?shares(?:\s+of\s+(?:its\s+|our\s+)?common\s+stock)?(?P<rest>[^.]{0,200})",
    re.IGNORECASE,
)
_PURCHASE_FOR = re.compile(
    r"(?:the\s+company(?:'s|’s)\s+)?purchase\s+of\s+(?:approximately\s+)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|thousand)?\s+"
    r"(?:of\s+(?:its|our)\s+)?(?:common\s+)?shares(?:\s+of\s+(?:its\s+|our\s+)?common\s+stock)?\s+for\s+(?:approximately\s+)?"
    r"\$\s*(?P<d>\d[\d,]*(?:\.\d+)?)\s*(?P<du>million|billion)?",
    re.IGNORECASE,
)


def parse_annual_shares_narrative(text: str, filing_year: int) -> dict[int, list[tuple[float, float | None]]]:
    """Share counts in management's summary, tied to the filing's own year.

    'Timken also repurchased 779,300 common shares during the year.'   'The Company also repurchased 1.1 million shares of common stock in 2020.'
    'the Company's purchase of 3.1 million of its common shares for $101.0 million' (with dollars)
    """
    out: dict[int, list[tuple[float, float | None]]] = {}

    def add(shares: float | None, dollars: float | None) -> None:
        if shares is None:
            return
        pair = (round(shares, 6), None if dollars is None else round(dollars, 6))
        if pair not in out.setdefault(filing_year, []):
            out[filing_year].append(pair)

    for match in _ANNUAL_NARRATIVE.finditer(text):
        rest = match.group("rest")
        sentence = text[_sentence_start(text, match.start()): match.end()]
        year_ok = re.search(rf"during the (?:fiscal )?year|percent of (?:its|our) outstanding|% of (?:its|our) outstanding|\bin {filing_year}\b", rest, re.IGNORECASE)
        if _EXCLUDE.search(sentence) or not year_ok:
            continue
        add(0.5 if match.group("half") else _shares_m(match.group("num"), match.group("unit")), None)
    for match in _PURCHASE_FOR.finditer(text):
        context = text[_sentence_start(text, match.start()): match.end() + 160]
        if _EXCLUDE.search(context) or not re.search(rf"\b{filing_year}\b|during the (?:fiscal )?year", context):
            continue
        add(_shares_m(match.group("num"), match.group("unit")), _dollars_m(match.group("d"), match.group("du")))
    return out


_BALANCE = re.compile(r"Balance,?\s+(?:[A-Za-z]+\.?\s+\d{1,2},?\s+)?(20\d\d)", re.IGNORECASE)
_EQUITY_ROW = re.compile(
    r"(?:Treasury\s+(?:stock|shares)\s+(?:acquired|purchased|repurchased)|Purchases?\s+of\s+treasury\s+(?:stock|shares)|"
    r"(?:Repurchases?|Purchases?)\s+of\s+(?:common\s+)?(?:stock|shares)|Shares\s+repurchased)\s*(?P<nums>(?:\s*(?:[-–—]|\(?\s*[\d,]+(?:\.\d+)?\s*\)?)\s*){1,8})",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\(?\s*(\d[\d,]*(?:\.\d+)?)\s*\)?")


def parse_equity_statement_repurchases(text: str) -> dict[int, list[tuple[float, float | None]]]:
    out: dict[int, list[tuple[float, float | None]]] = {}
    balances = list(_BALANCE.finditer(text))
    for i in range(len(balances) - 1):
        year = int(balances[i + 1].group(1))
        if year != int(balances[i].group(1)) + 1:
            continue                                        # not consecutive balance rows: not one year of movements
        segment = text[balances[i].end(): balances[i + 1].start()]
        row = _EQUITY_ROW.search(segment)
        if not row:
            continue
        numbers = [float(n.replace(",", "")) for n in _NUMBER.findall(row.group("nums"))]
        if len(numbers) < 3:
            continue                                        # no shares column: nothing to read
        header = text[max(0, balances[0].start() - 1500): balances[0].start()].lower()
        if "in thousands" in header:
            scale = 1_000.0
        elif "in millions" in header:
            scale = 1.0
        else:
            continue
        shares_raw, amount_raw = numbers[0], numbers[1]
        dollars_m = amount_raw / scale
        shares_m = next((s for s in (shares_raw / scale, shares_raw, shares_raw / 1_000_000.0) if dollars_m / s >= 1.0 and dollars_m / s <= 5_000.0), None) if shares_raw else None
        if shares_m is None:
            continue
        pair = (round(shares_m, 6), round(dollars_m, 6))
        if pair not in out.setdefault(year, []):
            out[year].append(pair)
    return out
