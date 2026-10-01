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


DEFAULT_MAX_UPLOAD_MB = 200


def max_upload_bytes() -> int:
    """Largest single upload accepted (HAP_MAX_UPLOAD_MB, default 200 MB)."""
    raw = os.environ.get("HAP_MAX_UPLOAD_MB", "").strip()
    try:
        megabytes = float(raw) if raw else float(DEFAULT_MAX_UPLOAD_MB)
    except ValueError:
        megabytes = float(DEFAULT_MAX_UPLOAD_MB)
    return int(max(megabytes, 0.001) * 1024 * 1024)


def sec_user_agent() -> str:
    """User-Agent sent to SEC EDGAR. SEC requires a real contact address.

    Set HAP_SEC_USER_AGENT, e.g. ``"HAP-Platform you@yourfirm.com"``.
    """
    return os.environ.get("HAP_SEC_USER_AGENT", "").strip()


# Routine chat uses the cheaper current Sonnet to stay inside the monthly budget;
# the strongest model is reserved for the agent's own "my take" view (HAP_STRONG_MODEL).
DEFAULT_AGENT_MODEL = "claude-sonnet-5-5"
DEFAULT_STRONG_MODEL = "claude-opus-5-5"
DEFAULT_MONTHLY_BUDGET_USD = 20.0


def agent_model() -> str:
    """Claude model for routine HAP Analyst chat (HAP_AGENT_MODEL)."""
    return os.environ.get("HAP_AGENT_MODEL", "").strip() or DEFAULT_AGENT_MODEL


def strong_model() -> str:
    """Strongest model, used sparingly for the agent's own view (HAP_STRONG_MODEL)."""
    return os.environ.get("HAP_STRONG_MODEL", "").strip() or DEFAULT_STRONG_MODEL


def monthly_budget_usd() -> float:
    """Hard monthly cap on Claude API spend in USD (HAP_MONTHLY_BUDGET_USD, default 20)."""
    raw = os.environ.get("HAP_MONTHLY_BUDGET_USD", "").strip()
    try:
        value = float(raw) if raw else DEFAULT_MONTHLY_BUDGET_USD
    except ValueError:
        value = DEFAULT_MONTHLY_BUDGET_USD
    return max(value, 0.0)


def feedback_dir() -> Path:
    return storage_root() / "feedback"


def usage_dir() -> Path:
    return storage_root() / "usage"


def answer_cache_dir() -> Path:
    return storage_root() / "answer_cache"


def lessons_dir() -> Path:
    return storage_root() / "lessons"


def lesson_min_support() -> int:
    """How many repeated cases before HAP proposes a lesson (HAP_LESSON_MIN_SUPPORT, default 3)."""
    try:
        return min(max(int(os.environ.get("HAP_LESSON_MIN_SUPPORT", "3")), 2), 50)
    except ValueError:
        return 3


def agent_effort() -> str:
    """Thinking depth: low | medium | high | xhigh | max (HAP_AGENT_EFFORT, default medium)."""
    value = os.environ.get("HAP_AGENT_EFFORT", "").strip().lower()
    return value if value in {"low", "medium", "high", "xhigh", "max"} else "medium"


def agent_fallbacks_enabled() -> bool:
    """Server-side refusal fallback (HAP_AGENT_FALLBACKS=0 turns it off)."""
    return os.environ.get("HAP_AGENT_FALLBACKS", "1").strip().lower() not in {"0", "false", "no", "off"}


def agent_max_iterations() -> int:
    """Upper bound on tool-use round trips per chat turn (HAP_AGENT_MAX_ITERATIONS)."""
    try:
        return min(max(int(os.environ.get("HAP_AGENT_MAX_ITERATIONS", "10")), 1), 25)
    except ValueError:
        return 10


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
