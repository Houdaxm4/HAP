"""OS trust-store SSL context used for outbound HTTPS."""

from __future__ import annotations

import ssl

from ssl_config import default_ssl_context


def test_default_ssl_context_is_ssl_context():
    ctx = default_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert default_ssl_context() is ctx
