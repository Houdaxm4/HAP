"""Regression tests for the storage/upload/auth hardening fixes."""

from __future__ import annotations

import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from starlette.datastructures import UploadFile
from starlette.requests import Request

import hap_auth.http as auth_http
from hap_auth import AuthConfigError
from main import app
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.file_service import FileService, FileUploadError
from services.output_service import OutputService
from services.safe_io import InvalidAnalysisIdError, validate_analysis_id, write_json_atomic


def _xlsx_bytes() -> bytes:
    buffer = io.BytesIO()
    Workbook().save(buffer)
    return buffer.getvalue()


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.fixture
def services(tmp_path):
    analyses = AnalysisService(tmp_path / "analyses")
    files = FileService(tmp_path / "uploads")
    analysis = analyses.create(CreateAnalysisRequest(company="X", ticker="x", analysis_type="annual_update"))
    return analyses, files, analysis


# ---- analysis id validation ---------------------------------------------------------------


@pytest.mark.parametrize("good", ["a1", "3bc7b27e-fa52-42e2-947c-9d9d4c5aee57", "scope1", "A_b-9"])
def test_valid_ids(good):
    assert validate_analysis_id(good) == good


@pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a\\b", "..\\..\\x", "../x", " a", "a" * 65, "a.json", "x\x00y"])
def test_invalid_ids(bad):
    with pytest.raises(InvalidAnalysisIdError):
        validate_analysis_id(bad)


def test_unsafe_ids_cannot_reach_the_filesystem(tmp_path):
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    with pytest.raises(AnalysisNotFoundError):
        analyses.get("..\\..\\boot")
    with pytest.raises(InvalidAnalysisIdError):
        outputs.analysis_output_dir("../escape")
    assert not (tmp_path / "escape").exists()


# ---- atomic writes ------------------------------------------------------------------------


def test_atomic_write_replaces_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "a.json"
    write_json_atomic(target, {"v": 1})
    write_json_atomic(target, {"v": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_atomic_write_failure_keeps_old_content(tmp_path):
    target = tmp_path / "a.json"
    write_json_atomic(target, {"ok": True})
    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


# ---- uploads ------------------------------------------------------------------------------


def test_valid_workbook_is_accepted(services):
    _, files, analysis = services
    updated = asyncio.run(files.handle_uploads(analysis, prefilled_workbook=_upload("model.xlsx", _xlsx_bytes())))
    assert updated.files.prefilled_workbook.size_bytes > 0
    stored = files.get_prefilled_workbook_path(updated)
    assert stored.read_bytes()[:2] == b"PK"
    assert not list(stored.parent.glob("*.part"))


def test_non_zip_content_is_rejected(services):
    _, files, analysis = services
    with pytest.raises(FileUploadError, match="not a valid .xlsx"):
        asyncio.run(files.handle_uploads(analysis, prefilled_workbook=_upload("model.xlsx", b"MZ not a workbook")))
    assert not list(files.analysis_upload_dir(analysis.analysis_id).iterdir())


def test_wrong_extension_is_rejected(services):
    _, files, analysis = services
    with pytest.raises(FileUploadError, match="Unsupported file extension"):
        asyncio.run(files.handle_uploads(analysis, prefilled_workbook=_upload("model.exe", _xlsx_bytes())))


def test_empty_upload_is_rejected(services):
    _, files, analysis = services
    with pytest.raises(FileUploadError, match="empty"):
        asyncio.run(files.handle_uploads(analysis, prefilled_workbook=_upload("model.xlsx", b"")))


def test_oversize_upload_is_rejected_and_cleaned_up(services, monkeypatch):
    _, files, analysis = services
    monkeypatch.setenv("HAP_MAX_UPLOAD_MB", "0.01")  # ~10 KB
    big = b"PK\x03\x04" + b"0" * 50_000
    with pytest.raises(FileUploadError, match="exceeds"):
        asyncio.run(files.handle_uploads(analysis, prefilled_workbook=_upload("model.xlsx", big)))
    assert not list(files.analysis_upload_dir(analysis.analysis_id).iterdir())


# ---- auth ---------------------------------------------------------------------------------


def test_login_returns_503_not_a_crash_when_auth_is_misconfigured(monkeypatch):
    monkeypatch.setenv("HAP_AUTH_ENABLED", "true")

    def broken():
        raise AuthConfigError("HAP_SESSION_SECRET is missing")

    monkeypatch.setattr(auth_http, "validate_auth_configuration", broken)
    client = TestClient(app)
    response = client.post("/auth/login", json={"username": "u", "password": "p"})
    assert response.status_code == 503
    other = client.get("/analyses")  # the gate must also answer cleanly, not raise NameError
    assert other.status_code == 503


def test_throttle_key_uses_the_proxy_appended_address_not_the_spoofable_one():
    def request(xff: str) -> Request:
        return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("10.0.0.5", 1)})

    assert auth_http.client_key(request("6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    assert auth_http.client_key(request("203.0.113.9")) == "203.0.113.9"
