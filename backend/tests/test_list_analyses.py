"""Tests for analysis list endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_analyses_returns_array():
    response = client.get("/analysis")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
