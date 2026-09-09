"""Private single-user authentication. No analysis/pipeline logic."""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass

import bcrypt

logger = logging.getLogger("hap.auth")

COOKIE_NAME = "hap_session"
GENERIC_LOGIN_ERROR = "Invalid credentials"
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60
MAX_FAILED_ATTEMPTS = 8
LOCKOUT_SECONDS = 60


class AuthConfigError(Exception):
    """Raised when production/auth configuration is unsafe."""


@dataclass(frozen=True)
class SessionPrincipal:
    username: str
    jti: str


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def is_production() -> bool:
    env = _env("HAP_ENV").lower()
    if env in {"production", "prod"}:
        return True
    if _env("RENDER").lower() in {"true", "1"}:
        return True
    return False


def auth_enabled() -> bool:
    """Production always requires auth. Local defaults to off unless explicitly enabled."""
    if is_production():
        return True
    raw = _env("HAP_AUTH_ENABLED").lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return False


def auth_username() -> str:
    return _env("HAP_AUTH_USERNAME")


def auth_password_hash() -> str:
    return _env("HAP_AUTH_PASSWORD_HASH")


def session_secret() -> str:
    return _env("HAP_SESSION_SECRET")


def session_ttl_seconds() -> int:
    raw = _env("HAP_SESSION_TTL_SECONDS")
    if not raw:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS
    return max(60, value)


def cookie_secure() -> bool:
    raw = _env("HAP_COOKIE_SECURE").lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return is_production()


def cookie_samesite() -> str:
    raw = _env("HAP_COOKIE_SAMESITE").lower()
    if raw in {"lax", "strict", "none"}:
        return raw
    return "none" if cookie_secure() else "lax"


def cookie_samesite_literal() -> str:
    value = cookie_samesite()
    return {"lax": "lax", "strict": "strict", "none": "none"}[value]


def auth_is_configured() -> bool:
    username = auth_username()
    pw_hash = auth_password_hash()
    secret = session_secret()
    return bool(username and pw_hash.startswith("$2") and len(secret) >= 32)


def validate_auth_configuration() -> None:
    """Fail closed when auth is required but secrets are missing/invalid."""
    if not auth_enabled():
        return
    missing: list[str] = []
    if not auth_username():
        missing.append("HAP_AUTH_USERNAME")
    if not auth_password_hash().startswith("$2"):
        missing.append("HAP_AUTH_PASSWORD_HASH")
    if len(session_secret()) < 32:
        missing.append("HAP_SESSION_SECRET")
    if cookie_samesite() == "none" and not cookie_secure():
        raise AuthConfigError(
            "HAP_COOKIE_SAMESITE=none requires Secure cookies (HAP_COOKIE_SECURE=true or production)."
        )
    if missing:
        raise AuthConfigError(
            "Authentication is required but incomplete. Set: " + ", ".join(missing)
        )


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash.startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def credentials_match(username: str, password: str) -> bool:
    expected_user = auth_username()
    expected_hash = auth_password_hash()
    user_ok = hmac.compare_digest(username.strip(), expected_user)
    pass_ok = verify_password(password, expected_hash)
    return bool(user_ok and pass_ok)


def issue_session_token(username: str) -> str:
    exp = int(time.time()) + session_ttl_seconds()
    jti = uuid.uuid4().hex
    payload = json.dumps({"u": username, "j": jti, "e": exp}, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    signature = hmac.new(
        session_secret().encode("utf-8"),
        payload_b64.encode("ascii"),
        "sha256",
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def parse_session_token(token: str, revoked_jtis: set[str]) -> SessionPrincipal | None:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(
        session_secret().encode("utf-8"),
        payload_b64.encode("ascii"),
        "sha256",
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        raw = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        username = str(data["u"])
        jti = str(data["j"])
        exp = int(data["e"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None
    if time.time() >= exp:
        return None
    if jti in revoked_jtis:
        return None
    if not hmac.compare_digest(username, auth_username()):
        return None
    return SessionPrincipal(username=username, jti=jti)


def new_session_secret() -> str:
    return secrets.token_urlsafe(48)


def log_login_success() -> None:
    logger.info("login_success")


def log_login_failure() -> None:
    logger.info("login_failure")


def log_logout() -> None:
    logger.info("logout")
