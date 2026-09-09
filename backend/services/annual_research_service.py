"""Official-first annual research for the Word report. Never invent earnings-call quotes."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

from models.annual_update import AnnualResearchReport, ResearchQuestion, ResearchSource
from services.quarterly_research_service import (
    _NEWSROOM as _NEWSROOM,
    _IR_PAGES as _IR_PAGES,
    SEC_USER_AGENT as SEC_USER_AGENT,
    _is_template_junk as _is_template_junk,
    _is_transcript_narrative as _is_transcript_narrative,
)

_YAHOO = "https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=0&newsCount=8"


class AnnualResearchService:
    def gather(
        self,
        *,
        analysis_id: str,
        ticker: str,
        fiscal_year: int | None = None,
        sec_manifest: dict[str, Any] | None = None,
        research_questions: list[ResearchQuestion] | None = None,
    ) -> AnnualResearchReport:
        t = ticker.upper()
        fy = fiscal_year or 0
        sources: list[ResearchSource] = []
        facts: list[str] = []
        mgmt: list[str] = []
        hap: list[str] = []
        call_status = "EARNINGS_CALL_SOURCE_UNAVAILABLE"
        call_url = None
        official = False
        ir = _IR_PAGES.get(t)

        if ir:
            snippet = self._snippet(ir, 500) or f"Official IR portal for {t}."
            sources.append(
                ResearchSource(
                    source_kind="ir_page",
                    title=f"{t} Investor Relations",
                    url=ir,
                    snippet=snippet,
                    reliability="official",
                )
            )

        newsroom = _NEWSROOM.get(t)
        if newsroom:
            rel = self._find_release(newsroom, t, fy)
            if rel:
                sources.append(rel)
                if rel.snippet:
                    facts.append(rel.snippet[:500])
                official = True

        if sec_manifest:
            for filing in sec_manifest.get("selected_filings") or sec_manifest.get("filings") or []:
                form = str(filing.get("form") or filing.get("filing_type") or "")
                if form not in {"10-K", "8-K", "20-F"}:
                    continue
                url = filing.get("primary_document_url") or filing.get("document_url") or filing.get("url")
                sources.append(
                    ResearchSource(
                        source_kind="sec_10k" if form == "10-K" else "sec_8k",
                        title=f"SEC {form} filed {filing.get('filing_date', filing.get('filed', ''))}",
                        url=url,
                        snippet=f"Official SEC {form} for {t}.",
                        reliability="official",
                    )
                )
                official = True
                facts.append(f"SEC {form} filed {filing.get('filing_date', filing.get('filed', 'n/a'))}.")

        call = self._find_call(t, fy)
        if call:
            if _is_transcript_narrative(call.snippet or ""):
                sources.append(call)
                call_url = call.url
                call_status = (
                    "AVAILABLE" if call.reliability == "official" else "AVAILABLE_SECONDARY_TRANSCRIPT"
                )
                mgmt.append(call.snippet or call.title)
            else:
                call_status = "EARNINGS_CALL_SOURCE_UNAVAILABLE"

        for item in self._yahoo(t, fy):
            sources.append(item)
            title_l = item.title.lower()
            if t.lower() in title_l or "apple" in title_l:
                if any(k in title_l for k in ("earnings", "results", "10-k", "annual")):
                    facts.append(f"(Secondary) {item.title}")

        if mgmt:
            hap.append(
                "Management commentary is sourced from an earnings-call transcript or official IR; "
                "HAP workbook metrics are the quantitative baseline."
            )
        else:
            hap.append(
                f"Quantitative results are from the HAP workbook and official/SEC sources; "
                f"earnings-call transcript was not retrieved ({call_status})."
            )

        return AnnualResearchReport(
            analysis_id=analysis_id,
            ticker=t,
            fiscal_year=fy or None,
            sources=sources,
            research_questions=list(research_questions or []),
            reported_facts=facts[:10],
            management_explanations=mgmt[:8],
            hap_interpretations=hap[:4],
            unsuccessful_searches=[
                q.rationale or q.question
                for q in (research_questions or [])
                if q.unsuccessful
            ],
            earnings_call_status=call_status,
            official_release_used=official,
            ir_page_url=ir,
            earnings_call_url=call_url,
            summary=(
                f"Annual research: {len(sources)} source(s); "
                f"{len(research_questions or [])} research question(s); "
                f"official_release={official}; earnings_call={call_status}."
            ),
        )

    def _find_release(self, newsroom: str, ticker: str, fy: int) -> ResearchSource | None:
        html = self._fetch(newsroom)
        if not html:
            return None
        for href, title in re.findall(r'href="([^"]+)"[^>]*>([^<]{0,160})', html)[:50]:
            blob = f"{href} {title}".lower()
            if not any(k in blob for k in ("earnings", "results", "annual", str(fy) if fy else "fy")):
                continue
            url = href if href.startswith("http") else urllib.parse.urljoin(newsroom, href)
            if "{{" in url:
                continue
            snippet = self._snippet(url, 700) or unescape(title.strip())
            if _is_template_junk(snippet):
                continue
            return ResearchSource(
                source_kind="earnings_release",
                title=unescape(title.strip())[:200] or f"{ticker} annual results",
                url=url,
                snippet=snippet[:700],
                reliability="official",
            )
        return None

    def _find_call(self, ticker: str, fy: int) -> ResearchSource | None:
        q = urllib.parse.quote(f"{ticker} FY{fy} earnings call transcript")
        payload = self._json(_YAHOO.format(query=q))
        if not payload:
            return None
        for item in (payload.get("news") or [])[:8]:
            title = str(item.get("title") or "")
            link = str(item.get("link") or item.get("url") or "")
            tl = title.lower()
            if "transcript" not in tl and "earnings call" not in tl:
                continue
            snippet = self._snippet(link, 800) if link else title
            official = bool(re.search(r"investor\.|ir\.|apple\.com", link, re.I))
            return ResearchSource(
                source_kind="earnings_call" if official else "earnings_call_secondary",
                title=title[:200],
                url=link,
                snippet=(snippet or title)[:800],
                reliability="official" if official else "secondary",
            )
        return None

    def _yahoo(self, ticker: str, fy: int) -> list[ResearchSource]:
        payload = self._json(_YAHOO.format(query=urllib.parse.quote(f"{ticker} FY{fy} earnings")))
        out: list[ResearchSource] = []
        if not payload:
            return out
        for item in (payload.get("news") or [])[:6]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            if ticker.upper() not in title.upper() and ticker.lower() not in title.lower():
                # require ticker token except well-known names
                if ticker.upper() == "AAPL" and "apple" not in title.lower():
                    continue
                elif ticker.upper() != "AAPL":
                    continue
            out.append(
                ResearchSource(
                    source_kind="yahoo_news",
                    title=title,
                    url=item.get("link") or item.get("url"),
                    snippet=str(item.get("summary") or title)[:400],
                    reliability="secondary",
                )
            )
        return out

    @staticmethod
    def _fetch(url: str) -> str | None:
        ua = SEC_USER_AGENT if "sec.gov" in url.lower() else "HAP-Platform/annual-update"
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError):
            return None

    def _snippet(self, url: str, n: int) -> str | None:
        html = self._fetch(url)
        if not html:
            return None
        text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:n] if text else None

    @staticmethod
    def _json(url: str) -> dict[str, Any] | None:
        req = urllib.request.Request(url, headers={"User-Agent": "HAP-Platform/annual-update"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
