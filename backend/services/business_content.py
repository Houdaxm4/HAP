"""Content for the 2-page business document, taken from the Business (Item 1) and Risk Factors (Item 1A) sections of the latest 10-K.

No AI model: sentences are selected by what they say (what the company is, its segments, customers and markets, competition, recent deals,
risk headlines) and shortened at a clause boundary. Each list holds at most a few sentences so the document stays within two pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from services.company_description_service import _SENT_END, _SKIP, _clip

_ITEM1_START = re.compile(r"item\s*1\.?\s*b\s?usiness", re.IGNORECASE)
_ITEM1A_START = re.compile(r"item\s*1a\.?\s*risk\s*f\s?actors", re.IGNORECASE)
_BOILER = re.compile(
    r"&#|fiscal year (?:end|20)|any of (?:these|the following) risks|following risks|pandemic|health crisis|"
    r"forward-looking|safe harbor|incorporated by reference|available (?:free of charge|on our website)|www\.|sec\.gov|annual report on form|"
    r"table of contents|trademarks?|copyright|all rights reserved", re.IGNORECASE
)


@dataclass
class BusinessContent:
    overview: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)
    customers: list[str] = field(default_factory=list)
    competition: list[str] = field(default_factory=list)
    developments: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    text = text.replace("&#8220;", '"').replace("&#8221;", '"').replace("&#8217;", "'").replace("&amp;", "&").replace("&#8226;", " ")
    return re.sub(r"\s+", " ", text)


def item1_text(text: str) -> str:
    """The body of Item 1: from the real heading (not the table of contents) to Item 1A."""
    for m in _ITEM1_START.finditer(text):
        window = text[m.start(): m.start() + 1200]
        if _ITEM1A_START.search(window[:260]):
            continue
        end = _ITEM1A_START.search(text, m.end() + 3000)
        return _clean(text[m.start(): end.start() if end else m.start() + 60000])
    return ""


def risk_text(text: str) -> str:
    for m in _ITEM1A_START.finditer(text):
        window = text[m.start(): m.start() + 600]
        if re.search(r"item\s*1b", window[:200], re.IGNORECASE):
            continue                                          # table of contents
        end = re.search(r"item\s*1b\.?\s*unresolved", text[m.end() + 3000:], re.IGNORECASE)
        stop = m.end() + 3000 + end.start() if end else m.start() + 40000
        return _clean(text[m.start(): stop])
    return ""


def _is_table_text(sentence: str) -> bool:
    """Table rows read as many numbers: not a sentence about the business."""
    digits = sum(ch.isdigit() for ch in sentence)
    return digits > 0.12 * len(sentence) or bool(re.search(r"\$\s*[\d,.]+\s+\$\s*[\d,.]+", sentence))


def _sentences(block: str, minimum: int = 40, maximum: int = 420) -> list[str]:
    out = []
    for s in _SENT_END.split(block):
        s = s.strip()
        if minimum <= len(s) <= maximum and not _BOILER.search(s) and not _SKIP.search(s) and not _is_table_text(s):
            out.append(s)
    return out


def _tidy(sentence: str, limit: int = 260) -> str:
    sentence = re.sub(r"^(?:[A-Z][A-Z&,'/\-]*\s+){3,}(?=[A-Z][a-z])", "", sentence)       # a run-together ALL-CAPS heading before the sentence
    sentence = re.sub(r"\(.*?\)", "", sentence)                   # parenthetical asides
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if len(sentence) > limit:
        cut = max(sentence.rfind(",", 0, limit), sentence.rfind(";", 0, limit))
        sentence = sentence[: cut if cut > 100 else limit].rstrip(" ,;") + "..."
    return sentence if sentence.endswith((".", "...")) else sentence + "."


def _pick(sentences: list[str], pattern: str, count: int, limit: int = 260, skip: set[str] | None = None) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    out: list[str] = []
    for s in sentences:
        if skip and s in skip:
            continue
        if rx.search(s):
            out.append(_tidy(s, limit))
            if len(out) == count:
                break
    return out


def extract(text: str) -> BusinessContent:
    body = item1_text(text)
    content = BusinessContent()
    if not body:
        return content
    for heading in ("general", "overview", "who are we and what do we do", "company overview", "our business"):
        body = re.sub(rf"^(?:item\s*1\.?\s*b\s?usiness)?\s*{heading}[:\s]+", "", body, flags=re.IGNORECASE)
    sentences = _sentences(body)
    overview_src = [s for s in sentences[:12]]
    content.overview = [_tidy(s, 320) for s in overview_src[:4]]
    used = set(overview_src[:4])
    content.segments = _pick(sentences, r"(?:reportable|reporting|operating) segments?", 2, 300, used)
    taken = {s for s in sentences if _tidy(s, 280) in content.segments}
    content.segments += _pick(sentences, r"\bsegments?\b", 3 - len(content.segments), 280, used | taken)
    used.update(s for s in sentences if _tidy(s, 280) in content.segments)
    content.customers = _pick(sentences, r"\bcustomers?\b|end[- ]markets?|\bmarkets? (?:we|that)\b", 3, 240, used)
    comp = re.search(r"\bcompetition\b[:\s]+(.{200,1600})", body, re.IGNORECASE)
    if comp:
        content.competition = [_tidy(s, 260) for s in _sentences(comp.group(1))[:2]]
    content.developments = _pick(sentences, r"\b(acquir\w+|acquisition|divest\w+|completed the sale|sold)\b.*\b20\d\d\b|\b20\d\d\b.*\b(acquir\w+|acquisition|divest\w+)\b", 3, 240, used)
    content.risks = _risk_headlines(risk_text(text))
    return content


def _risk_headlines(block: str) -> list[str]:
    if not block:
        return []
    block = re.sub(r"^item\s*1a\.?\s*risk\s*f\s?actors\s*", "", block, flags=re.IGNORECASE)
    summary =re.search(r"summary of (?:material |principal |key )?risk factors?(.{300,3500})", block, re.IGNORECASE)
    source = summary.group(1) if summary else block[: 12000]
    out: list[str] = []
    for s in _sentences(source, 50, 230):
        if re.search(r"\b(could|may|might|adversely|negatively|harm)\b", s, re.IGNORECASE) and re.match(r"^(?:we|our|the|if|a|an|changes|changes in|any|failure|disruption|inflation|international)\b", s, re.IGNORECASE):
            out.append(_tidy(s, 200))
        if len(out) == 6:
            break
    return out
