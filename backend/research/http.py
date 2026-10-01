"""Small guarded HTTP fetcher: policy-checked, size-capped, redirects re-checked."""

from __future__ import annotations

import time
from urllib.parse import urljoin

import httpx

from research.policy import ResearchPolicyError, check_url
from settings import sec_user_agent
from ssl_config import default_ssl_context

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 4
TIMEOUT = 20.0


class ResearchFetchError(Exception):
    pass


class GuardedFetcher:
    def __init__(self, extra_allowed: set[str] | None = None, min_interval: float = 0.25) -> None:
        self.extra_allowed = extra_allowed or set()
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str, *, accept: str = "text/html,text/plain,application/xml,text/csv;q=0.9,*/*;q=0.5") -> tuple[str, str]:
        """Return (final_url, text). Raises ResearchPolicyError / ResearchFetchError."""
        current = url
        with httpx.Client(
            timeout=TIMEOUT, follow_redirects=False, verify=default_ssl_context(),
            headers={"User-Agent": sec_user_agent() or "HAP research (contact: set HAP_SEC_USER_AGENT)", "Accept": accept},
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                check_url(current, self.extra_allowed)
                wait = self.min_interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
                try:
                    with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise ResearchFetchError("Redirect without a location.")
                            current = urljoin(current, location)
                            continue
                        if response.status_code != 200:
                            raise ResearchFetchError(f"HTTP {response.status_code} from {current}")
                        chunks: list[bytes] = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_BYTES:
                                break  # keep the first MAX_BYTES; callers treat the text as truncated data
                            chunks.append(chunk)
                        encoding = response.encoding or "utf-8"
                        return current, b"".join(chunks).decode(encoding, errors="replace")
                except httpx.HTTPError as exc:
                    raise ResearchFetchError(f"Network error fetching {current}: {type(exc).__name__}") from exc
        raise ResearchFetchError("Too many redirects.")


__all__ = ["GuardedFetcher", "ResearchFetchError", "ResearchPolicyError"]
