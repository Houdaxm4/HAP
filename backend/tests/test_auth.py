"""Private single-user authentication tests. Does not exercise analysis engines."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from hap_auth import (
    AuthConfigError,
    hash_password,
    verify_password,
    validate_auth_configuration,
)
from hap_auth.state import revoked_jtis, throttle
from main import app, output_service
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisService

PASSWORD = "test-only-passphrase-not-for-prod"
USERNAME = "houda@example.com"


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("HAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("HAP_ENV", "")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("HAP_AUTH_USERNAME", USERNAME)
    monkeypatch.setenv("HAP_AUTH_PASSWORD_HASH", hash_password(PASSWORD))
    monkeypatch.setenv("HAP_SESSION_SECRET", "a" * 48)
    monkeypatch.setenv("HAP_COOKIE_SECURE", "false")
    monkeypatch.setenv("HAP_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("HAP_SESSION_TTL_SECONDS", "43200")
    throttle.failures.clear()
    throttle.locked_until.clear()
    revoked_jtis.clear()
    validate_auth_configuration()
    return TestClient(app)


def _secret_leaks(payload: object) -> bool:
    blob = json.dumps(payload) if not isinstance(payload, str) else payload
    lowered = blob.lower()
    return any(
        token in lowered
        for token in (PASSWORD.lower(), "hap_session_secret", "$2b$", "password_hash")
    )


def test_hash_verification_roundtrip():
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$2")
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("wrong", hashed)
    assert PASSWORD not in hashed


def test_health_remains_public(auth_env: TestClient):
    response = auth_env.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_required"] is True
    assert body["auth_configured"] is True
    assert "HAP_SESSION_SECRET" not in json.dumps(body)
    assert not _secret_leaks(body)


def test_protected_unauthenticated_is_401(auth_env: TestClient):
    assert auth_env.get("/analyses").status_code == 401
    assert auth_env.post(
        "/analysis/create",
        json={"company": "Apple Inc.", "ticker": "AAPL", "analysis_type": "new_company"},
    ).status_code == 401


def test_valid_login_sets_httponly_cookie(auth_env: TestClient):
    response = auth_env.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "password" not in response.json()
    header = response.headers.get("set-cookie", "")
    assert "hap_session=" in header
    assert "httponly" in header.lower()
    assert "hap_session" in auth_env.cookies


def test_invalid_password_and_username_are_generic(auth_env: TestClient):
    bad_pw = auth_env.post("/auth/login", json={"username": USERNAME, "password": "nope"})
    bad_user = auth_env.post(
        "/auth/login",
        json={"username": "other@example.com", "password": PASSWORD},
    )
    assert bad_pw.status_code == 401
    assert bad_user.status_code == 401
    assert bad_pw.json()["detail"] == bad_user.json()["detail"] == "Invalid credentials"
    assert not _secret_leaks(bad_pw.json())


def test_me_and_logout(auth_env: TestClient):
    anon = auth_env.get("/auth/me")
    assert anon.status_code == 200
    assert anon.json()["authenticated"] is False
    login = auth_env.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert login.status_code == 200
    me = auth_env.get("/auth/me")
    assert me.json()["authenticated"] is True
    assert me.json()["username"] == USERNAME
    assert not _secret_leaks(me.json())
    out = auth_env.post("/auth/logout")
    assert out.status_code == 200
    me2 = auth_env.get("/auth/me")
    assert me2.json()["authenticated"] is False
    assert auth_env.get("/analyses").status_code == 401


def test_protected_and_download_require_session(auth_env: TestClient, tmp_path, monkeypatch):
    monkeypatch.setattr("main.analysis_service", AnalysisService(storage_dir=tmp_path / "analyses"))
    from main import analysis_service

    created = analysis_service.create(
        CreateAnalysisRequest(company="Apple Inc.", ticker="AAPL", analysis_type="new_company")
    )
    aid = created.analysis_id
    out_dir = tmp_path / "outputs"
    monkeypatch.setattr(output_service, "outputs_dir", out_dir)
    dest = out_dir / aid
    dest.mkdir(parents=True)
    (dest / "note.xlsx").write_bytes(b"xlsx")

    assert auth_env.get("/analyses").status_code == 401
    assert auth_env.get(f"/analysis/{aid}/outputs/note.xlsx").status_code == 401

    auth_env.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    listed = auth_env.get("/analyses")
    assert listed.status_code == 200
    download = auth_env.get(f"/analysis/{aid}/outputs/note.xlsx")
    assert download.status_code == 200


def test_production_missing_auth_config_fails(monkeypatch):
    monkeypatch.setenv("HAP_ENV", "production")
    monkeypatch.delenv("HAP_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("HAP_AUTH_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("HAP_SESSION_SECRET", "")
    with pytest.raises(AuthConfigError):
        validate_auth_configuration()


def test_session_expiration(auth_env: TestClient, monkeypatch):
    clock = {"now": 1_700_000_000.0}

    def fake_time() -> float:
        return clock["now"]

    monkeypatch.setattr("hap_auth.time.time", fake_time)
    monkeypatch.setenv("HAP_SESSION_TTL_SECONDS", "60")
    login = auth_env.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert login.status_code == 200
    assert auth_env.get("/analyses").status_code == 200
    clock["now"] += 120
    assert auth_env.get("/analyses").status_code == 401


def test_login_throttling(auth_env: TestClient, monkeypatch):
    monkeypatch.setattr("hap_auth.state.MAX_FAILED_ATTEMPTS", 3)
    for _ in range(3):
        auth_env.post("/auth/login", json={"username": USERNAME, "password": "wrong"})
    blocked = auth_env.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert blocked.status_code == 429
