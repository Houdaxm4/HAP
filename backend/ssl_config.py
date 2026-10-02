"""TLS trust for outbound HTTPS (SEC EDGAR and similar)."""

from __future__ import annotations

import ssl
from functools import lru_cache


@lru_cache(maxsize=1)
def default_ssl_context() -> ssl.SSLContext:
    """Use the OS certificate store, not httpx's certifi default.

    httpx 0.28 verifies against certifi unless given an SSLContext. On Windows
    that Mozilla bundle often misses extra roots already in the OS store
    (campus/corporate inspection CAs), which surfaces as
    CERTIFICATE_VERIFY_FAILED against sec.gov. Python's default context loads
    those OS roots. If the store is empty (stripped Linux image), fall back to
    certifi.
    """
    ctx = ssl.create_default_context()
    if _ca_count(ctx) == 0:
        fallback = _certifi_context()
        if fallback is not None:
            return fallback
    return ctx


def _ca_count(ctx: ssl.SSLContext) -> int:
    stats = getattr(ctx, "cert_store_stats", None)
    if stats is None:
        return -1
    try:
        return int(stats().get("x509_ca", 0))
    except Exception:
        return -1


def _certifi_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())
