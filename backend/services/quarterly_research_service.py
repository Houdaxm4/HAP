"""External research for Word Quarterly Update (releases, SEC, IR, earnings call)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

from models.quarterly_update import QuarterlyResearchReport, ResearchSourceEntry

YAHOO_NEWS = "https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=0&newsCount=10"
SEC_USER_AGENT = "HAP-Platform contact@houda-analyst.com"

# Known Investor Relations landing pages (official company material).
_IR_PAGES: dict[str, str] = {
    "AAPL": "https://investor.apple.com/investor-relations/default.aspx",
    "MSFT": "https://www.microsoft.com/en-us/investor",
    "AMZN": "https://ir.aboutamazon.com/",
}

# Company newsroom / earnings release patterns.
_NEWSROOM: dict[str, str] = {
    "AAPL": "https://www.apple.com/newsroom/",
}


def _is_template_junk(text: str) -> bool:
    """Reject handlebars/SPA placeholders and empty snippets."""
    if not text or not text.strip():
        return True
    if "{{" in text or "{{#" in text:
        return True
    return len(text.strip()) < 30


def _is_transcript_narrative(text: str) -> bool:
    """True when text looks like actual earnings-call transcript content."""
    if _is_template_junk(text):
        return False
    tl = text.lower()
    markers = (
        "operator:",
        "question-and-answer",
        "prepared remarks",
        "good morning",
        "thank you for joining",
        "conference call",
        "executive:",
        "analyst:",
    )
    if any(m in tl for m in markers):
        return True
    return len(text.strip()) >= 200


def _ticker_in_text(ticker: str, text: str) -> bool:
    t = ticker.upper()
    return t in text.upper() or t.lower() in text.lower()


class QuarterlyResearchService:
    """Gather official/secondary sources for Financial Highlights — no fabrication."""

    def gather(
        self,
        *,
        analysis_id: str,
        ticker: str,
        fiscal_year: int | None = None,
        fiscal_quarter: int | None = None,
        sec_manifest: dict[str, Any] | None = None,
    ) -> QuarterlyResearchReport:
        t = ticker.upper()
        fy = fiscal_year or 0
        q = fiscal_quarter or 0
        sources: list[ResearchSourceEntry] = []
        reported: list[str] = []
        mgmt: list[str] = []
        hap: list[str] = []
        earnings_call_status = "EARNINGS_CALL_SOURCE_UNAVAILABLE"
        earnings_call_url: str | None = None
        official_release_used = False
        ir_page_url = _IR_PAGES.get(t)

        # 1. Official IR page
        if ir_page_url:
            ir_snip = self._fetch_text_snippet(ir_page_url, max_len=500)
            sources.append(
                ResearchSourceEntry(
                    source_kind="ir_page",
                    title=f"{t} Investor Relations",
                    url=ir_page_url,
                    snippet=ir_snip or f"Official IR portal for {t}.",
                    reliability="official",
                )
            )

        # 2. Company newsroom / earnings release search
        newsroom = _NEWSROOM.get(t)
        if newsroom:
            release = self._find_newsroom_release(newsroom, t, fy, q)
            if release:
                sources.append(release)
                if release.snippet and not _is_template_junk(release.snippet):
                    reported.append(release.snippet[:600])
                else:
                    reported.append(release.title)
                official_release_used = True

        # 2b. IR quarterly earnings page (when newsroom search misses SPA sites)
        if ir_page_url and not any(s.source_kind == "ir_release" for s in sources):
            ir_release = self._find_ir_quarterly_release(ir_page_url, t, fy, q)
            if ir_release:
                sources.append(ir_release)
                if ir_release.snippet and not _is_template_junk(ir_release.snippet):
                    reported.append(ir_release.snippet[:600])
                else:
                    reported.append(ir_release.title)
                official_release_used = True

        # 3. SEC filings (8-K earnings, 10-Q)
        if sec_manifest:
            for filing in sec_manifest.get("selected_filings") or []:
                form = str(filing.get("filing_type") or filing.get("form") or "")
                if form not in {"8-K", "10-Q"}:
                    continue
                url = (
                    filing.get("primary_document_url")
                    or filing.get("document_url")
                    or filing.get("url")
                )
                title = f"SEC {form} filed {filing.get('filing_date', '')}"
                sec_snippet = None
                if url:
                    sec_snippet = self._fetch_text_snippet(url, max_len=700)
                sources.append(
                    ResearchSourceEntry(
                        source_kind="sec_8k" if form == "8-K" else "sec_10q",
                        title=title,
                        url=url,
                        snippet=(
                            sec_snippet
                            or (
                                f"Official SEC {form} filing for {t} "
                                f"(accession {filing.get('accession_number', 'n/a')})."
                            )
                        ),
                        reliability="official",
                    )
                )
                if form == "8-K":
                    reported.append(
                        sec_snippet
                        or (
                            f"Form 8-K filed {filing.get('filing_date', 'n/a')} — "
                            "typically includes earnings release exhibit."
                        )
                    )
                    official_release_used = True
                if form == "10-Q":
                    if sec_snippet and not _is_template_junk(sec_snippet):
                        reported.append(sec_snippet[:600])
                    else:
                        reported.append(
                            f"SEC Form 10-Q filed {filing.get('filing_date', 'n/a')} "
                            f"(report date {filing.get('report_date', 'n/a')})."
                        )
                    official_release_used = True

        # 4. Earnings call transcript — IR page links, then transcript search
        call = self._find_earnings_call(t, fy, q, ir_page_url)
        if call is None and ir_page_url:
            call = self._find_ir_transcript_link(ir_page_url, t)
        if call:
            snippet = call.snippet or call.title or ""
            url = call.url or ""
            is_webcast_only = "webcast" in url.lower() and "transcript" not in url.lower()
            has_transcript = _is_transcript_narrative(snippet) and not _is_template_junk(snippet)
            if has_transcript and not is_webcast_only:
                sources.append(call)
                earnings_call_url = call.url
                if call.source_kind == "earnings_call":
                    earnings_call_status = "AVAILABLE"
                    mgmt.append(snippet)
                elif call.source_kind == "earnings_call_secondary":
                    earnings_call_status = "AVAILABLE_SECONDARY_TRANSCRIPT"
                    mgmt.append(f"(Secondary transcript source) {snippet}")
            elif is_webcast_only or _is_template_junk(snippet):
                # Webcast landing pages are not transcripts — record but do not treat as call.
                sources.append(
                    ResearchSourceEntry(
                        source_kind="earnings_call_webcast",
                        title=call.title,
                        url=call.url,
                        snippet="Official webcast link only; transcript text not retrieved.",
                        reliability="official",
                    )
                )
                earnings_call_url = call.url

        # 5. Yahoo news — facts only, NOT earnings call substitute; ticker-relevant only
        for item in self._yahoo_news(t, fy, q):
            if item.source_kind == "yahoo_news":
                sources.append(item)
                title_l = item.title.lower()
                if any(k in title_l for k in ("earnings", "results", "revenue", "quarter")):
                    if "transcript" not in title_l and "conference call" not in title_l:
                        reported.append(f"(Secondary) {item.snippet or item.title}")

        # HAP interpretation — never fabricate management quotes
        if mgmt and earnings_call_status.startswith("AVAILABLE"):
            hap.append(
                "Management commentary above is sourced from an earnings-call transcript or "
                "official IR material; HAP workbook metrics provide the quantitative baseline."
            )
        elif reported:
            hap.append(
                "Quantitative results are from the HAP workbook and official/SEC sources; "
                f"earnings-call transcript was not retrieved ({earnings_call_status})."
            )
        else:
            hap.append(
                f"Limited external narrative for {t} {fy} Q{q}; attach official release and call transcript."
            )

        official_n = sum(1 for s in sources if s.reliability == "official")
        summary = (
            f"Research: {len(sources)} source(s) ({official_n} official); "
            f"earnings_call={earnings_call_status}."
        )
        return QuarterlyResearchReport(
            analysis_id=analysis_id,
            ticker=t,
            fiscal_year=fy or None,
            fiscal_quarter=q or None,
            sources=sources,
            reported_facts=reported[:8],
            management_explanations=mgmt[:8],
            hap_interpretations=hap[:4],
            earnings_call_status=earnings_call_status,
            official_release_used=official_release_used,
            ir_page_url=ir_page_url,
            earnings_call_url=earnings_call_url,
            summary=summary,
        )

    def _find_newsroom_release(
        self, newsroom_url: str, ticker: str, fy: int, q: int
    ) -> ResearchSourceEntry | None:
        html = self._fetch_html(newsroom_url)
        if not html:
            return None
        # Find links mentioning earnings / quarter
        pattern = re.compile(
            r'href="([^"]+)"[^>]*>([^<]*(?:earnings|results|Q\d|quarter)[^<]*)',
            re.I,
        )
        for href, title in pattern.findall(html)[:20]:
            title_clean = unescape(title.strip())
            if not title_clean:
                continue
            url = href if href.startswith("http") else urllib.parse.urljoin(newsroom_url, href)
            if any(k in title_clean.lower() for k in ("earnings", "results", "quarter")):
                snippet = self._fetch_text_snippet(url, max_len=600) or title_clean
                return ResearchSourceEntry(
                    source_kind="ir_release",
                    title=title_clean[:200],
                    url=url,
                    snippet=snippet[:600],
                    reliability="official",
                )
        return None

    def _find_ir_quarterly_release(
        self, ir_url: str, ticker: str, fy: int, q: int
    ) -> ResearchSourceEntry | None:
        html = self._fetch_html(ir_url)
        if not html:
            return None
        q_pat = re.compile(rf"Q{q}|quarter\s*{q}|{fy}", re.I)
        for href, title in re.findall(r'href="([^"]+)"[^>]*>([^<]{0,160})', html)[:60]:
            title_clean = unescape(title.strip())
            combined = f"{href} {title_clean}"
            if not q_pat.search(combined):
                continue
            if not any(k in combined.lower() for k in ("earnings", "results", "financial", "10-q")):
                continue
            url = href if href.startswith("http") else urllib.parse.urljoin(ir_url, href)
            if "{{" in url:
                continue
            snippet = self._fetch_text_snippet(url, max_len=700) or title_clean
            if _is_template_junk(snippet):
                continue
            return ResearchSourceEntry(
                source_kind="ir_release",
                title=title_clean[:200] or f"{ticker} quarterly results",
                url=url,
                snippet=snippet[:700],
                reliability="official",
            )
        return None

    def _find_ir_transcript_link(self, ir_url: str, ticker: str) -> ResearchSourceEntry | None:
        html = self._fetch_html(ir_url)
        if not html:
            return None
        for href, title in re.findall(r'href="([^"]+)"[^>]*>([^<]{0,120})', html)[:40]:
            combined = f"{href} {title}".lower()
            if "transcript" not in combined and "conference call" not in combined:
                continue
            if "webcast" in href.lower() and "transcript" not in href.lower():
                continue
            url = href if href.startswith("http") else urllib.parse.urljoin(ir_url, href)
            if "{{" in url:
                continue
            snippet = self._fetch_text_snippet(url, max_len=800) or unescape(title.strip())
            if _is_template_junk(snippet) or not _is_transcript_narrative(snippet):
                continue
            return ResearchSourceEntry(
                source_kind="earnings_call",
                title=unescape(title.strip())[:200] or f"{ticker} earnings call",
                url=url,
                snippet=snippet[:800],
                reliability="official",
            )
        return None

    def _find_earnings_call(
        self, ticker: str, fy: int, q: int, ir_url: str | None
    ) -> ResearchSourceEntry | None:
        queries = [
            f"{ticker} earnings call transcript Q{q} {fy}",
            f"{ticker} conference call transcript",
        ]
        transcript_hosts = ("seekingalpha.com", "fool.com", "thestreet.com", "investor.")
        for query in queries:
            payload = self._get_json(YAHOO_NEWS.format(query=urllib.parse.quote(query)))
            if not payload:
                continue
            for item in (payload.get("news") or [])[:8]:
                title = str(item.get("title") or "").strip()
                link = str(item.get("link") or item.get("url") or "")
                if not title or not link:
                    continue
                tl = title.lower()
                if "transcript" not in tl and "conference call" not in tl and "earnings call" not in tl:
                    continue
                is_official = bool(re.search(r"investor\.|ir\.|apple\.com/investor", link, re.I))
                is_transcript_host = any(h in link.lower() for h in transcript_hosts)
                if not is_official and not is_transcript_host:
                    continue
                snippet = self._fetch_text_snippet(link, max_len=800) or str(item.get("summary") or "")[:400]
                if _is_template_junk(snippet) or not _is_transcript_narrative(snippet):
                    continue
                return ResearchSourceEntry(
                    source_kind="earnings_call" if is_official else "earnings_call_secondary",
                    title=title,
                    url=link,
                    snippet=snippet[:800] if snippet else title,
                    reliability="official" if is_official else "secondary",
                )
        return None

    def _yahoo_news(self, ticker: str, fy: int, q: int) -> list[ResearchSourceEntry]:
        query = f"{ticker} earnings Q{q} {fy}" if q else f"{ticker} earnings"
        payload = self._get_json(YAHOO_NEWS.format(query=urllib.parse.quote(query)))
        if not payload:
            return []
        out: list[ResearchSourceEntry] = []
        for item in (payload.get("news") or [])[:8]:
            title = str(item.get("title") or "").strip()
            link = item.get("link") or item.get("url")
            if not title:
                continue
            if not _ticker_in_text(ticker, title) and not _ticker_in_text(ticker, str(item.get("summary") or "")):
                continue
            if any(k in title.lower() for k in ("transcript", "conference call", "earnings call")):
                continue  # handled separately — not generic news
            snippet = str(item.get("summary") or "")[:400]
            reliability = "secondary"
            if link and re.search(r"investor\.|ir\.|sec\.gov|apple\.com/newsroom", str(link), re.I):
                reliability = "official"
            out.append(
                ResearchSourceEntry(
                    source_kind="yahoo_news",
                    title=title,
                    url=link,
                    snippet=snippet or title,
                    reliability=reliability,
                )
            )
        return out

    @staticmethod
    def _fetch_html(url: str) -> str | None:
        ua = SEC_USER_AGENT if "sec.gov" in url.lower() else "HAP2-ModeA/1.0"
        req = urllib.request.Request(url, headers={"User-Agent": ua}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError):
            return None

    def _fetch_text_snippet(self, url: str, *, max_len: int = 500) -> str | None:
        html = self._fetch_html(url)
        if not html:
            return None
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        if "sec.gov" in url.lower():
            text = re.sub(r"<ix:[^>]*>.*?</ix:[^>]+>", " ", text, flags=re.I | re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = unescape(re.sub(r"\s+", " ", text)).strip()
            for sentence in re.findall(r"[A-Z][^.!?]{50,400}[.!?]", text):
                sl = sentence.lower()
                if "pursuant to section" in sl or "transition report" in sl:
                    continue
                if any(
                    k in sl
                    for k in (
                        "revenue",
                        "net income",
                        "quarter",
                        "products",
                        "services",
                        "iphone",
                        "operating",
                    )
                ):
                    return sentence[:max_len]
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:max_len] if text else None

    @staticmethod
    def _get_json(url: str) -> dict[str, Any] | None:
        req = urllib.request.Request(url, headers={"User-Agent": "HAP2-ModeA/1.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
