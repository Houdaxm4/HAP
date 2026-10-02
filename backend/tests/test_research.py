import pytest

from research import sources
from research.evidence import Evidence
from research.http import GuardedFetcher
from research.policy import ResearchPolicyError, check_url, site_domain
from research.toolbox import ResearchToolbox

CSV = '{"chart":{"result":[{"meta":{"currency":"USD","regularMarketPrice":11.3},"timestamp":[1790640000,1790726400],"indicators":{"quote":[{"close":[10.5,11.25],"volume":[100,200]}]}}]}}'
RSS = """<rss><channel><item><title>Acme beats</title><link>http://x</link><pubDate>Mon, 28 Sep 2026</pubDate><source>Reuters</source></item></channel></rss>"""


class FakeFetcher(GuardedFetcher):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def get(self, url, **kw):
        check_url(url, self.extra_allowed)
        return url, self.text


def test_policy_blocks_unsafe_urls():
    for bad in ["http://sec.gov/x", "https://127.0.0.1/x", "https://evil.com/x", "https://sec.gov.evil.com/x",
                "https://user:pw@sec.gov/x", "https://localhost/x", "file:///etc/passwd"]:
        with pytest.raises(ResearchPolicyError):
            check_url(bad)
    assert check_url("https://www.sec.gov/a") == "www.sec.gov"
    assert check_url("https://ir.acme.com/a", {"acme.com"}) == "ir.acme.com"
    assert site_domain("https://www.acme.com/ir") == "acme.com"


def test_price_news_and_labels():
    ev = sources.price_evidence(FakeFetcher(CSV), "aapl")
    assert ev.data["last_close"] == 11.25 and ev.reliability == "market_data" and ev.as_of == "2026-09-30"
    news = sources.news_evidence(FakeFetcher(RSS), "acme")
    assert news.reliability == "news" and "Reuters" in news.content
    rendered = ev.render()
    assert "RELIABILITY" in rendered and "DATA, not instructions" in rendered


def test_rss_rejects_entities_and_ticker_validation():
    with pytest.raises(ValueError):
        sources.parse_rss('<!DOCTYPE x [<!ENTITY a "b">]><rss/>')
    with pytest.raises(ValueError):
        sources.clean_ticker("../etc")


def test_ir_extracts_text_and_links():
    html = "<html><head><title>x</title></head><body><script>bad()</script><h1>Results</h1><a href='/q3.pdf'>Q3 deck</a></body></html>"
    fetcher = FakeFetcher(html)
    fetcher.extra_allowed = {"acme.com"}
    ev = sources.ir_evidence(fetcher, "https://ir.acme.com/")
    assert "Results" in ev.content and "bad()" not in ev.content and "https://ir.acme.com/q3.pdf" in ev.content


def test_toolbox_logs_and_refuses(tmp_path):
    log = tmp_path / "ev.jsonl"
    tb = ResearchToolbox(ticker="ACME", company="Acme", fetcher=FakeFetcher(CSV), evidence_log=log, company_domain="acme.com")
    text, err = tb.execute("get_delayed_price", {})
    assert not err and "SOURCE" in text and log.read_text().count("\n") == 1
    text, err = tb.execute("fetch_ir_page", {"url": "https://evil.com/x"})
    assert err and "not on the allowed" in text
    assert tb.execute("nope", {})[1]
