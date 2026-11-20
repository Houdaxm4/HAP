"""Management commentary for the email's Financial Highlights, taken from the company's own earnings release on SEC EDGAR.

The release is the 8-K (Item 2.02) filed after the quarter ended, Exhibit 99.1. HAP picks out, without any AI model, two kinds of sentences:
  * results: why the numbers moved (driven by, due to, primarily, growth in ...), and
  * outlook: what management plans or expects for the short and medium term (expect, outlook, guidance, invest, plan, repurchase ...).
The sentences are quoted from the release (shortened when long), never rewritten, and the email names the filing they came from.
When the release cannot be found or holds nothing useful, the result is empty and the email keeps a bracketed line for the analyst.
The text of a release is treated as data only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any

import httpx

from ssl_config import default_ssl_context
from services.sec_service import SecService

MAX_RESULTS = 3
MAX_OUTLOOK = 4
MAX_SENTENCE = 260
WINDOW_DAYS = 100                          # the earnings 8-K comes within this many days after the quarter ends

_DISCLAIMER = re.compile(
    r"forward-looking|risks? and uncertaint|undue reliance|non-gaap|reconcil|safe harbor|private securities|"
    r"conference call|webcast|dial-in|replay|press release|investor relations|www\.|@|copyright|cautionary|"
    r"no expiration|does not obligate|without prior notice|may be suspended|these statements|current expectations about|"
    r"future events or future financial performance|actual results (?:may|could)|speak only as of",
    re.I,
)
_RESULT_CUES = re.compile(
    r"\b(driven by|due to|primarily|mainly|reflect(?:ing|s|ed)?|attributable|as a result of|benefit(?:ed|ing)? from|"
    r"growth in|increase in|decrease in|decline in|higher|lower|strong|record|demand|momentum)\b", re.I)
_OUTLOOK_CUES = re.compile(
    r"\b(expect(?:s|ed|ation)?|anticipat\w+|outlook|guidance|plans?|planned|intend\w*|invest(?:ing|ment|ments)?|capital allocation|"
    r"repurchase\w*|buyback|dividend|target\w*|will continue|continue to|focus(?:ed|ing)? on|strateg\w+|initiatives?|launch\w*|"
    r"expand\w*|acqui\w+|pipeline|backlog|capacity|fiscal 20\d\d|full[- ]year|next year|20(?:27|28|29|30))\b", re.I)
_FIRST_PERSON = re.compile(r"\b(we|our|us)\b", re.I)


@dataclass
class ReleaseCommentary:
    results: list[str] = field(default_factory=list)
    outlook: list[str] = field(default_factory=list)
    source_url: str | None = None
    filed: str | None = None
    status: str = "NOT_FOUND"

    @property
    def found(self) -> bool:
        return bool(self.results or self.outlook)


def _text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"</(p|div|tr|li|h\d|table)>|<br\s*/?>", ". ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[﻿​‌‍]", "", unescape(html)).replace("\xa0", " ")
    text = re.sub(r"[•▪●·■]", ". ", text)                       # bullets separate sentences
    text = re.sub(r"[-–— ]*\bMORE\b[-–— ]*", " ", text)              # page-break marker of press releases
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"(\s*\.\s*){2,}", ". ", re.sub(r"\n+", " ", text)).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])[\"”’']?\s+(?=[A-Z\"“])", text)
    return [p.strip(" \"“”") for p in parts]


def _usable(sentence: str) -> bool:
    if not 60 <= len(sentence) <= 420 or _DISCLAIMER.search(sentence) or "�" in sentence:
        return False
    if re.match(r"^[A-Z][\w&.,' -]{0,60}\b(Reports|Announces|Reported)\b", sentence):          # the headline
        return False
    letters = sum(c.isalpha() for c in sentence)
    digits = sum(c.isdigit() for c in sentence)
    return letters > 0.6 * len(sentence) and digits < 0.2 * len(sentence)       # prose, not a table row or a list of figures


def _shorten(sentence: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    if len(sentence) <= MAX_SENTENCE:
        return sentence
    cut = max(sentence.rfind(", ", 0, MAX_SENTENCE), sentence.rfind("; ", 0, MAX_SENTENCE))
    return (sentence[:cut] if cut > 120 else sentence[:MAX_SENTENCE].rsplit(" ", 1)[0]).rstrip(",;:") + " ..."


def _pick(candidates: list[tuple[int, int, str]], limit: int) -> list[str]:
    """Best score first, then document order; near-duplicates are skipped."""
    chosen: list[tuple[int, str]] = []
    for score, position, sentence in sorted(candidates, key=lambda c: (-c[0], c[1])):
        words = set(re.findall(r"[a-z]{4,}", sentence.lower()))
        if any(len(words & set(re.findall(r"[a-z]{4,}", other.lower()))) > 0.6 * max(len(words), 1) for _p, other in chosen):
            continue
        chosen.append((position, sentence))
        if len(chosen) == limit:
            break
    def tidy(sentence: str) -> str:
        text = _shorten(sentence).replace(':."', '."').replace(":.", ".").replace('."."', '."')
        text = text.replace('.".', '."')
        return text if text.endswith((" ...", ".", '."')) else text.rstrip(" :;,") + "."

    return [tidy(s) for _p, s in sorted(chosen)]


def extract_commentary(text: str) -> ReleaseCommentary:
    sentences = [s for s in _sentences(_text(text) if "<" in text else text) if _usable(s)]
    total = max(len(sentences), 1)
    results: list[tuple[int, int, str]] = []
    outlook: list[tuple[int, int, str]] = []
    for position, s in enumerate(sentences):
        outlook_hits = len(_OUTLOOK_CUES.findall(s))
        result_hits = len(_RESULT_CUES.findall(s))
        forward = len(re.findall(r"\b(expect\w*|anticipat\w+|outlook|guidance|plans?|intend\w*|will|continue to|invest\w*|repurchase\w*|target\w*)\b", s, re.I))
        if forward and (_FIRST_PERSON.search(s) or outlook_hits >= 2):
            outlook.append((outlook_hits + forward, position, s))              # a sentence goes under one heading only
        elif result_hits and position < 0.6 * total:
            results.append((result_hits + (1 if re.search(r"\d", s) else 0), position, s))
    out = ReleaseCommentary(results=_pick(results, MAX_RESULTS), outlook=_pick(outlook, MAX_OUTLOOK))
    out.status = "FOUND" if out.found else "NO_COMMENTARY"
    return out


def _period_end(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


class EarningsReleaseService:
    def __init__(self, sec: SecService | None = None) -> None:
        self.sec = sec or SecService()

    def _fetch(self, url: str) -> str:
        """The release as text; the bytes are decoded as UTF-8 (Windows-1252 when that fails) so quotes and dashes survive."""
        self.sec._respect_rate_limit()
        with httpx.Client(timeout=60.0, headers={"User-Agent": self.sec.user_agent}, follow_redirects=True, verify=default_ssl_context()) as client:
            response = client.get(url)
            response.raise_for_status()
        try:
            return response.content.decode("utf-8")
        except UnicodeDecodeError:
            return response.content.decode("cp1252", errors="replace")

    def commentary(self, ticker: str, period_end: Any) -> ReleaseCommentary:
        end = _period_end(period_end)
        if end is None:
            return ReleaseCommentary(status="NO_PERIOD")
        try:
            cik = self.sec.resolve_cik(ticker)
            recent = self.sec._get_json(f"https://data.sec.gov/submissions/CIK{cik}.json").get("filings", {}).get("recent", {})
            candidates = []
            for i, form in enumerate(recent.get("form", [])):
                if form != "8-K" or "2.02" not in str(recent.get("items", [""] * (i + 1))[i]):
                    continue
                filed = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").date()
                if end < filed <= end + timedelta(days=WINDOW_DAYS):
                    candidates.append((filed, recent["accessionNumber"][i], recent["primaryDocument"][i]))
            if not candidates:
                return ReleaseCommentary(status="NO_8K")
            filed, accession, primary = min(candidates)                         # the first earnings 8-K after the quarter ended
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"
            index = self.sec._get_json(f"{base}/index.json")
            names = [item.get("name", "") for item in index.get("directory", {}).get("item", [])]
            exhibit = next((n for n in names if re.search(r"ex-?99[-_.]?1?", n, re.I) and n.lower().endswith((".htm", ".html"))), None)
            url = f"{base}/{exhibit or primary}"
            found = extract_commentary(self._fetch(url))
            found.source_url, found.filed = url, filed.isoformat()
            return found
        except Exception as exc:  # noqa: BLE001 - the commentary is optional; the email keeps its bracketed line
            return ReleaseCommentary(status=f"ERROR: {type(exc).__name__}")
