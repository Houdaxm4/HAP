"""Operating-lease commitments stated as text in a pre-ASC 842 10-K note (millions of dollars).

For example (Standex, fiscal 2018):
  "Rental expense ... for the years ended June 30, 2018, 2017, and 2016 was approximately $10.2 million, $8.0 million and $6.6 million ...
   The gross minimum annual rental commitments under non-cancelable operating leases ... (in thousands) Lease Sublease Net obligation
   2019 10,202 329 9,873  2020 8,704 336 8,368 ... 2023 7,204 367 6,837  Thereafter 15,995 2,670 13,325"
The first amount in each row is the gross lease commitment, which is what the template's lease schedule holds (year 1 to year 5 and thereafter).
"""

from __future__ import annotations

import re

_HEAD = re.compile(
    r"(?:gross\s+)?(?:future\s+)?minimum\s+(?:annual\s+)?(?:rental|lease)\s+(?:commitments|payments|obligations)[^:.]{0,200}?operating\s+leases",
    re.IGNORECASE,
)
_ROW = re.compile(r"\b(20\d\d)\s+\$?\s*(\d[\d,]*(?:\.\d+)?)")
_THEREAFTER = re.compile(r"thereafter\s+\$?\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_RENT = re.compile(
    r"(?:rental|rent)\s+expense[^.]{0,220}?(?:was|were|totaled|totaling)\s+(?:approximately\s+)?\$\s*(\d[\d,]*(?:\.\d+)?)\s*(million|thousand)?",
    re.IGNORECASE,
)


def parse_operating_lease_commitments(text: str) -> dict[str, float]:
    """Keys year_1..year_5, thereafter, total_undiscounted and (when stated) lease_cost, in millions. Empty when the table is not there."""
    head = _HEAD.search(text)
    if not head:
        return {}
    window = text[head.end(): head.end() + 900]
    lowered = window[:200].lower()
    if "in thousands" in lowered:
        scale = 1_000.0
    elif "in millions" in lowered:
        scale = 1.0
    else:
        return {}
    rows: list[tuple[int, float]] = []
    for m in _ROW.finditer(window):
        year, amount = int(m.group(1)), float(m.group(2).replace(",", ""))
        if rows and year != rows[-1][0] + 1:
            break                                           # the table ended
        rows.append((year, amount / scale))
        if len(rows) == 5:
            break
    if len(rows) != 5:
        return {}
    out = {f"year_{i + 1}": round(a, 6) for i, (_y, a) in enumerate(rows)}
    after = window[window.lower().find("thereafter"):] if "thereafter" in window.lower() else ""
    tail = _THEREAFTER.search(window)
    if tail:
        out["thereafter"] = round(float(tail.group(1).replace(",", "")) / scale, 6)
    out["total_undiscounted"] = round(sum(v for k, v in out.items() if k.startswith("year_") or k == "thereafter"), 6)
    _ = after
    rent = _RENT.search(text[max(0, head.start() - 900): head.start()])
    if rent:
        value = float(rent.group(1).replace(",", ""))
        unit = (rent.group(2) or "").lower()
        out["lease_cost"] = round(value if unit == "million" else value / 1_000.0 if unit == "thousand" else value / scale, 6)
    return out
