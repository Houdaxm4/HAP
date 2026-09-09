"""Runtime configuration. Analysis/pipeline logic does not belong here."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
DEFAULT_STORAGE_ROOT = BACKEND_ROOT / "storage"
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def storage_root() -> Path:
    """Root for analyses, uploads, outputs, and parse cache.

    Override with HAP_STORAGE_DIR (Render persistent disk mount).
    Unset → backend/storage, same as local development today.
    """
    raw = os.environ.get("HAP_STORAGE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_STORAGE_ROOT.resolve()


def analyses_dir() -> Path:
    return storage_root() / "analyses"


def uploads_dir() -> Path:
    return storage_root() / "uploads"


def outputs_dir() -> Path:
    return storage_root() / "outputs"


def parse_cache_dir() -> Path:
    return storage_root() / "parse_cache"


def cors_allow_origins() -> list[str]:
    """Browser origins allowed to call the API.

    HAP_CORS_ORIGINS is a comma-separated list. Unset → localhost Next.js.
    Use ``*`` only if credentials are not required (see cors_allow_credentials).
    """
    raw = os.environ.get("HAP_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


def cors_allow_credentials() -> bool:
    origins = cors_allow_origins()
    return origins != ["*"]


def storage_is_writable() -> bool:
    root = storage_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".hap_healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
