"""Online research tools for the agent. Every result is labeled evidence and is logged for audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research import sources
from research.evidence import Evidence
from research.http import GuardedFetcher, ResearchFetchError
from research.policy import ResearchPolicyError, site_domain

RESEARCH_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_recent_filings",
        "description": (
            "Recent SEC EDGAR filings (10-K, 10-Q, 8-K) for this analysis's company, with dates and links. "
            "Regulatory source: the most reliable evidence available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"forms": {"type": "array", "items": {"type": "string", "enum": ["10-K", "10-Q", "8-K"]}}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_delayed_price",
        "description": "Free delayed daily prices for this company's ticker (last few trading days). Indicative only.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 30}},
            "additionalProperties": False,
        },
    },
    {
        "name": "search_news",
        "description": (
            "Recent news headlines about a topic (default: the company). Unverified aggregator results: use them to "
            "find leads and say so; never present a headline as confirmed fact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 2, "maxLength": 120}},
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_ir_page",
        "description": (
            "Fetch a page on the company's own investor-relations website (only the company's domain is allowed; "
            "arbitrary URLs are refused). Company-stated, not independent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    },
]

RESEARCH_TOOL_NAMES = {schema["name"] for schema in RESEARCH_TOOL_SCHEMAS}


class ResearchToolbox:
    """Research tools bound to one company. `evidence_log` (JSONL) records everything fetched."""

    def __init__(
        self,
        *,
        ticker: str,
        company: str,
        cik: str | None = None,
        evidence_log: Path | None = None,
        sec_service: Any = None,
        fetcher: GuardedFetcher | None = None,
        company_domain: str | None = None,
    ) -> None:
        self.ticker = sources.clean_ticker(ticker)
        self.company = company
        self.cik = cik
        self.evidence_log = evidence_log
        self._sec = sec_service
        self._company_domain = company_domain
        self.fetcher = fetcher or GuardedFetcher()
        self.collected: list[Evidence] = []

    # ---- dispatch -------------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any] | None) -> tuple[str, bool]:
        args = args if isinstance(args, dict) else {}
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Unknown research tool '{name}'.", True
        try:
            evidence = handler(**args)
        except (ResearchPolicyError, ResearchFetchError, ValueError) as exc:
            return f"{name} failed: {exc}", True
        except TypeError as exc:
            return f"Invalid arguments for {name}: {exc}", True
        except Exception as exc:  # noqa: BLE001 - the agent loop must never crash on a source outage
            return f"{name} failed ({type(exc).__name__}). The source may be unavailable; say so and continue.", True
        self._record(evidence)
        return evidence.render(), False

    def _record(self, evidence: Evidence) -> None:
        self.collected.append(evidence)
        if self.evidence_log is None:
            return
        try:
            self.evidence_log.parent.mkdir(parents=True, exist_ok=True)
            entry = evidence.to_dict()
            entry["content"] = entry["content"][:4000]
            with self.evidence_log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except OSError:
            pass  # auditing is best effort; it must not break an answer

    # ---- tools ----------------------------------------------------------------------------

    def _sec_service(self) -> Any:
        if self._sec is None:
            from services.sec_service import SecService
            self._sec = SecService()
        return self._sec

    def _resolve_cik(self) -> str:
        if self.cik:
            return self.cik
        self.cik = self._sec_service().resolve_cik(self.ticker)
        return self.cik

    def _tool_get_recent_filings(self, forms: list[str] | None = None) -> Evidence:
        wanted = {f for f in (forms or ["10-K", "10-Q", "8-K"]) if f in {"10-K", "10-Q", "8-K"}} or {"10-K", "10-Q", "8-K"}
        cik = self._resolve_cik()
        filings = self._sec_service().list_recent_filings(cik, forms=wanted)
        if not filings:
            raise ValueError("No matching filings found.")
        lines = [
            f"- {f.get('filing_date')} | {f.get('filing_type')} {f.get('items') or ''} | {f.get('document_url')}"
            for f in filings[:15]
        ]
        first = filings[0]
        return Evidence(
            kind="sec_filing", source="SEC EDGAR", url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            reliability="regulatory", title=f"{self.ticker} recent filings", as_of=first.get("filing_date"),
            content="\n".join(lines), data={"count": len(filings)},
        )

    def _tool_get_delayed_price(self, days: int = 5) -> Evidence:
        return sources.price_evidence(self.fetcher, self.ticker, days)

    def _tool_search_news(self, query: str | None = None) -> Evidence:
        return sources.news_evidence(self.fetcher, query or f"{self.company} {self.ticker} stock")

    def _tool_fetch_ir_page(self, url: str) -> Evidence:
        domain = self._company_domain or self._discover_domain()
        if not domain:
            raise ResearchPolicyError(
                "The company's website is not known. Ask the analyst for the IR site, then add its domain to HAP_RESEARCH_EXTRA_DOMAINS."
            )
        self.fetcher.extra_allowed = {domain}
        return sources.ir_evidence(self.fetcher, url)

    def _discover_domain(self) -> str | None:
        try:
            cik = self._resolve_cik()
            from services.sec_service import SEC_SUBMISSIONS_URL
            website = self._sec_service()._get_json(SEC_SUBMISSIONS_URL.format(cik=cik)).get("website")
        except Exception:  # noqa: BLE001
            return None
        self._company_domain = site_domain(website) if website else None
        return self._company_domain
