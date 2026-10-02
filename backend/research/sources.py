"""Source adapters. Parsing is separate from fetching so it can be tested offline."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

from research.evidence import Evidence
from research.http import GuardedFetcher

TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")


def clean_ticker(ticker: str) -> str:
    if not isinstance(ticker, str) or not TICKER_RE.match(ticker.strip()):
        raise ValueError("Invalid ticker.")
    return ticker.strip().upper()


# ---- prices (Yahoo Finance chart endpoint: free, unofficial, delayed) -----------------------

def parse_yahoo_chart(text: str) -> dict:
    payload = json.loads(text)
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise ValueError("No price data returned.")
    result = results[0]
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    quote_block = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, ts in enumerate(stamps):
        close = (quote_block.get("close") or [None] * len(stamps))[i]
        if close is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"),
            "close": float(close),
            "volume": (quote_block.get("volume") or [None] * len(stamps))[i],
        })
    return {"meta": meta, "rows": rows}


def price_evidence(fetcher: GuardedFetcher, ticker: str, days: int = 5) -> Evidence:
    symbol = clean_ticker(ticker)
    days = max(1, min(int(days), 30))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=1mo&interval=1d"
    final_url, text = fetcher.get(url, accept="application/json")
    parsed = parse_yahoo_chart(text)
    rows = parsed["rows"][-days:]
    meta = parsed["meta"]
    if not rows:
        raise ValueError(f"No price data for {symbol}.")
    last_price = meta.get("regularMarketPrice")
    lines = [f"{r['date']}  close {r['close']:.2f}  volume {r['volume']}" for r in rows]
    if last_price is not None:
        lines.append(f"Latest price: {last_price} {meta.get('currency', '')} (52-week range {meta.get('fiftyTwoWeekLow')} - {meta.get('fiftyTwoWeekHigh')})")
    return Evidence(
        kind="price_quote", source="Yahoo Finance chart data (free, delayed, unofficial)", url=final_url, reliability="market_data",
        title=f"{symbol} recent daily prices", as_of=rows[-1]["date"], content="\n".join(lines),
        data={"ticker": symbol, "last_date": rows[-1]["date"], "last_close": rows[-1]["close"], "latest_price": last_price},
    )


# ---- news (Google News RSS) ----------------------------------------------------------------

def parse_rss(text: str, limit: int = 10) -> list[dict[str, str]]:
    if "<!DOCTYPE" in text[:2000].upper() and "<!ENTITY" in text.upper():
        raise ValueError("Refusing XML with entity declarations.")
    root = ET.fromstring(text)
    items = []
    for item in root.iter("item"):
        source = item.find("source")
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "publisher": (source.text or "").strip() if source is not None else "",
        })
        if len(items) >= limit:
            break
    return items


def news_evidence(fetcher: GuardedFetcher, query: str, limit: int = 8) -> Evidence:
    query = " ".join(str(query).split())[:120]
    if len(query) < 2:
        raise ValueError("Query too short.")
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    final_url, text = fetcher.get(url, accept="application/rss+xml,application/xml,text/xml")
    items = parse_rss(text, max(1, min(limit, 15)))
    if not items:
        raise ValueError("No news found.")
    lines = [f"- {i['published']} | {i['publisher'] or 'unknown publisher'} | {i['title']}" for i in items]
    return Evidence(
        kind="news", source="Google News RSS", url=final_url, reliability="news",
        title=f"News: {query}", as_of=items[0]["published"] or None, content="\n".join(lines),
        data={"items": items},
    )


# ---- investor-relations pages --------------------------------------------------------------

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "a" and self._href:
            label = " ".join("".join(self._link_text).split())
            if label:
                self.links.append((label[:100], urljoin(self.base_url, self._href)))
            self._href = None
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._link_text.append(data)


def html_to_text(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    parser = _TextExtractor(base_url)
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, parser.links


def ir_evidence(fetcher: GuardedFetcher, url: str, max_links: int = 25) -> Evidence:
    final_url, html = fetcher.get(url)
    text, links = html_to_text(html, final_url)
    link_lines = "\n".join(f"- {label}: {href}" for label, href in links[:max_links])
    content = text + (f"\n\nLINKS:\n{link_lines}" if link_lines else "")
    return Evidence(
        kind="ir_page", source=f"Company IR page ({fetcher_host(final_url)})", url=final_url,
        reliability="company_stated", title="Investor relations page", content=content,
    )


def fetcher_host(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or url
