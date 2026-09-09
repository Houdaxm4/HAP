"""Configuration helpers — no analysis/pipeline logic."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import settings
from main import app
from services.analysis_service import AnalysisService
from services.file_service import FileService
from services.output_service import OutputService
from services.workbook_service import WorkbookService

client = TestClient(app)


def test_default_storage_is_backend_storage(monkeypatch):
    monkeypatch.delenv("HAP_STORAGE_DIR", raising=False)
    root = settings.storage_root()
    assert root == (Path(settings.BACKEND_ROOT) / "storage").resolve()
    assert settings.analyses_dir() == root / "analyses"
    assert settings.uploads_dir() == root / "uploads"
    assert settings.outputs_dir() == root / "outputs"
    assert settings.parse_cache_dir() == root / "parse_cache"


def test_hap_storage_dir_overrides_all_subpaths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HAP_STORAGE_DIR", str(tmp_path))
    assert settings.storage_root() == tmp_path.resolve()
    assert AnalysisService().storage_dir == tmp_path.resolve() / "analyses"
    assert FileService().uploads_dir == tmp_path.resolve() / "uploads"
    assert OutputService().outputs_dir == tmp_path.resolve() / "outputs"
    assert WorkbookService().cache_dir == tmp_path.resolve() / "parse_cache"


def test_default_cors_is_localhost(monkeypatch):
    monkeypatch.delenv("HAP_CORS_ORIGINS", raising=False)
    assert settings.cors_allow_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert settings.cors_allow_credentials() is True


def test_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv(
        "HAP_CORS_ORIGINS",
        "https://hap-web.onrender.com, http://localhost:3000",
    )
    assert settings.cors_allow_origins() == [
        "https://hap-web.onrender.com",
        "http://localhost:3000",
    ]


def test_health_endpoints():
    for path in ("/health", "/healthz"):
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["storage_ok"] is True
        assert "auth_required" in body
        assert "auth_configured" in body
        assert "HAP_SESSION_SECRET" not in str(body)
