"""Research-and-development expense stated in a 10-K note, for years that the structured SEC data does not carry.

Some companies keep R&D inside selling and administrative expense and only state it in a note, for example:
  "Total research and development costs, which are classified under selling, general, and administrative expenses, were $5.5 million,
   $4.9 million, and $4.1 million for the years ended June 30, 2017, 2016, and 2015, respectively."
The amounts are matched to the years named in the same sentence, or to the filing's year and the years before it when no years are named.
Values are in millions of dollars. Only amounts written with "million" or "thousand" are used.
"""

from __future__ import annotations

import re

_HEAD = re.compile(r"research\s+and\s+development\s+(?:costs?|expenses?|expenditures?|spending)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<!\d)\.(?!\d)(?=\s|$)")
_AMOUNT = re.compile(r"\$\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|thousand|billion)", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")
_REJECT = re.compile(r"in-process|acquired|may be|expect|approximately \d+% of|percent of|% of", re.IGNORECASE)


def _millions(num: str, unit: str) -> float:
    value = float(num.replace(",", ""))
    return {"billion": value * 1_000.0, "million": value, "thousand": value / 1_000.0}[unit.lower()]


def parse_rd_costs(text: str, filing_year: int) -> dict[int, float]:
    """Fiscal year -> R&D expense in millions, from sentences about total research and development costs."""
    out: dict[int, float] = {}
    for head in _HEAD.finditer(text):
        end = _SENTENCE_END.search(text, head.end())
        sentence = text[head.start(): end.start() if end else head.end() + 500]
        if _REJECT.search(sentence) or _REJECT.search(text[max(0, head.start() - 40): head.start()]):
            continue
        amounts = [_millions(m.group("num"), m.group("unit")) for m in _AMOUNT.finditer(sentence)]
        if not 1 <= len(amounts) <= 5:
            continue
        years = [int(y) for y in _YEAR.findall(sentence)]
        if len(years) == len(amounts):
            pairs = list(zip(years, amounts))
        elif not years:
            pairs = [(filing_year - i, a) for i, a in enumerate(amounts)]      # most recent year first
        else:
            continue
        for year, amount in pairs:
            out.setdefault(year, amount)
    return out
