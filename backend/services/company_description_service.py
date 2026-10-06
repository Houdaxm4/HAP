"""One-line company description for the email, taken from the company's own 10-K (no AI model).

The first sentence of Item 1 (Business) that says what the company is or does is cut into the part after its subject, so the email can say
"<Name> is a diversified industrial manufacturer ..." (annual update) or "<Name>, headquartered in <City, State>, is a ..." (new company).
The headquarters come from the SEC submissions record (business address).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "Washington, D.C.", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

_VERBS = r"(?:is|are|designs?|develops?|manufactures?|provides?|operates?|offers?|engages?\s+in|produces?|markets?|delivers?|supplies|serves?|owns?)"
_SKIP = re.compile(
    r"^(?:as used herein|this (?:annual )?report|the following|forward-looking|certain statements|our fiscal year|references? to|unless|item\s)", re.IGNORECASE
)
_SENT_END = re.compile(r"(?<!\b[A-Z])(?<!\d)(?<!\bInc)(?<!\bCorp)(?<!\bCo)(?<!\bLtd)(?<!\bU\.S)\.(?!\d)\s+(?=[A-Z])")


@dataclass
class CompanyDescription:
    predicate: str = ""            # "is a diversified industrial manufacturer with ..."
    headquarters: str = ""         # "Billerica, Massachusetts"
    name: str = ""                 # the company's name on file at the SEC
    source: str = ""

    def annual(self, name: str) -> str | None:
        return f"{name} {self.predicate}" if self.predicate else None

    def new_company(self, name: str) -> str | None:
        if not self.predicate:
            return None
        where = f", headquartered in {self.headquarters}," if self.headquarters else ""
        return f"{name}{where} {self.predicate}."


def _business_section(text: str) -> str:
    """The body of Item 1 (the occurrence that is followed by prose, not by the table of contents)."""
    starts = [m.start() for m in re.finditer(r"item\s*1\.?\s*b\s?usiness", text, re.IGNORECASE)]
    for pos in starts:
        window = text[pos: pos + 1200]
        if re.search(r"item\s*1a", window[:260], re.IGNORECASE):
            continue                                        # table of contents
        return text[pos: pos + 9000]
    return ""


def _third_person(verb: str) -> str:
    v = verb.lower()
    if v in {"is", "are"}:
        return "is"
    if v.startswith("engage"):
        return "engages in"
    if v.endswith("s") or v.endswith("ss"):
        return v
    return v + "s"


def _clip(predicate: str, limit: int = 230) -> str:
    predicate = re.sub(r"\s+", " ", predicate).strip().rstrip(".")
    if len(predicate) <= limit:
        return predicate
    cut = max(predicate.rfind(",", 0, limit), predicate.rfind(";", 0, limit), predicate.rfind(" and ", 0, limit))
    return predicate[: cut if cut > 80 else limit].rstrip(" ,;")


_COORDINATED = re.compile(r"(?P<lead>,\s*|\s+and\s+)(?P<verb>design|develop|manufacture|provide|produce|market|sell|distribute|operate|offer|serve|supply|own|engineer|build)(?=\s)")


def _agree_coordinated_verbs(predicate: str) -> str:
    head, tail = predicate[:90], predicate[90:]
    head = _COORDINATED.sub(lambda m: m.group("lead") + m.group("verb") + ("es" if m.group("verb").endswith("s") else "s"), head)
    return head + tail


def predicate_from_business_text(text: str) -> str:
    section = _business_section(text)
    if not section:
        return ""
    clean = section.replace("&#8220;", '"').replace("&#8221;", '"').replace("&#8217;", "'").replace("&amp;", "&")
    for sentence in _SENT_END.split(clean)[:40]:
        sentence = sentence.strip()
        for _ in range(3):      # headings can be stacked: "Item 1. Business General ..."
            sentence = re.sub(
                r"^(?:item\s*1\.?\s*b\s?usiness|general|overview|who are we and what do we do|company overview|our business)[:\s]*", "", sentence, flags=re.IGNORECASE
            ).strip()
        if len(sentence) < 50 or _SKIP.search(sentence):
            continue
        no_paren = re.sub(r"\([^)]*\)", "", sentence)
        m = re.search(rf"\b(?P<verb>{_VERBS})\b\s+(?P<rest>.+)$", no_paren)
        if not m:
            continue
        subject = no_paren[: m.start()].strip().lower()
        if len(subject) > 120 or len(subject) < 2:
            continue
        verb = m.group("verb")
        predicate = f"{_third_person(verb)} {m.group('rest')}"
        if verb.lower() not in {"is", "are"} and not verb.lower().endswith("s"):
            predicate = _agree_coordinated_verbs(predicate)       # "we design and manufacture" -> "designs and manufactures"
        if _SKIP.search(m.group("rest")):
            continue
        return _clip(predicate)
    return ""


def sec_text_fetch_enabled() -> bool:
    """Fetching filing text from the SEC for the description and business document; tests switch it off (HAP_SEC_TEXT_FETCH=0)."""
    return os.environ.get("HAP_SEC_TEXT_FETCH", "1").strip().lower() not in {"0", "false", "no"}


def sec_identity(ticker: str, sec=None) -> tuple[str, str]:
    """(company name, headquarters) from the SEC submissions record; empty strings when unavailable."""
    if not sec_text_fetch_enabled():
        return "", ""
    try:
        from services.sec_service import SEC_SUBMISSIONS_URL, SecService

        sec = sec or SecService()
        cik = sec.resolve_cik(ticker)
        record = sec._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        address = (record.get("addresses") or {}).get("business") or {}
        name = str(record.get("name") or "").strip().title()
    except Exception:  # noqa: BLE001 - optional detail
        return "", ""
    city = str(address.get("city") or "").strip().title()
    state = US_STATES.get(str(address.get("stateOrCountry") or "").strip().upper())
    return name, (f"{city}, {state}" if city and state else city)


def headquarters(ticker: str, sec=None) -> str:
    return sec_identity(ticker, sec)[1]


def _latest_cached_business_text(search_dir: Path | None) -> str:
    if not search_dir or not Path(search_dir).exists():
        return ""
    from services.new_company_buyback_service import html_to_text

    files = sorted(Path(search_dir).glob("sec_cache/**/10k_business_*.htm"), key=lambda p: p.name)
    if not files:
        return ""
    return html_to_text(files[-1].read_text(encoding="utf-8", errors="ignore"))


def _fetch_latest_business_text(ticker: str) -> str:
    if not sec_text_fetch_enabled():
        return ""
    try:
        from services.new_company_buyback_service import html_to_text
        from services.sec_service import SecService

        sec = SecService()
        cik = sec.resolve_cik(ticker)
        filings = [f for f in sec.list_recent_filings(cik, forms={"10-K"}) if f.get("document_url")]
        if not filings:
            return ""
        return html_to_text(sec.fetch_document_text(filings[0]["document_url"], cik=cik, cache_name="10k_business_latest.htm"))
    except Exception:  # noqa: BLE001
        return ""


def describe(ticker: str, search_dir: Path | None = None, *, with_headquarters: bool = True) -> CompanyDescription:
    """The description from the analysis folder's cached 10-K, or the newest 10-K from SEC when none is cached."""
    text = _latest_cached_business_text(search_dir) or _fetch_latest_business_text(ticker)
    predicate = predicate_from_business_text(text) if text else ""
    name, hq = sec_identity(ticker) if (predicate and with_headquarters) else ("", "")
    return CompanyDescription(
        predicate=predicate, headquarters=hq, name=name,
        source="the Business section of the company's latest 10-K" if predicate else "",
    )
