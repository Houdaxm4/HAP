"""What the research tools may reach. Fixed allow-list plus the company's own IR domain.

The model cannot widen this: arbitrary URLs are refused, so a poisoned page cannot make HAP fetch (or send
data to) an address of its choosing.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

FIXED_DOMAINS = {
    "sec.gov": "regulatory",
    "finance.yahoo.com": "market_data",
    "query1.finance.yahoo.com": "market_data",
    "news.google.com": "news",
}


class ResearchPolicyError(Exception):
    pass


def research_enabled() -> bool:
    return os.environ.get("HAP_RESEARCH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def extra_domains() -> set[str]:
    raw = os.environ.get("HAP_RESEARCH_EXTRA_DOMAINS", "")
    return {d.strip().lower().lstrip(".") for d in raw.split(",") if d.strip()}


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def check_url(url: str, extra_allowed: set[str] | None = None) -> str:
    """Return the host if the URL is allowed, else raise ResearchPolicyError."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ResearchPolicyError("Only https URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if not host or _is_ip_literal(host) or host == "localhost" or host.endswith((".local", ".internal")):
        raise ResearchPolicyError("That host is not allowed.")
    if parsed.username or parsed.password:
        raise ResearchPolicyError("URLs with embedded credentials are not allowed.")
    allowed = set(FIXED_DOMAINS) | extra_domains() | {d.lower() for d in (extra_allowed or set())}
    if not any(_host_matches(host, d) for d in allowed):
        raise ResearchPolicyError(
            f"{host} is not on the allowed-source list (SEC, delayed prices, news, the company's own IR site)."
        )
    return host


def site_domain(url_or_host: str) -> str | None:
    """Registrable-ish domain of a company website (drops a leading www.)."""
    parsed = urlparse(url_or_host if "//" in url_or_host else f"https://{url_or_host}")
    host = (parsed.hostname or "").lower()
    if not host or _is_ip_literal(host) or "." not in host:
        return None
    return host[4:] if host.startswith("www.") else host
