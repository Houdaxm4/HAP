"""Tests for workbook introspection and production workbook requirements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.custom_run_parser import CustomRunParseError, CustomRunParser
from ingestion.production_workbook_profile import (
    PRODUCTION_AAPL_PROFILE,
    PRODUCTION_AAPL_WORKBOOK,
    load_production_profile,
    production_profile_available,
    production_workbook_available,
)
from ingestion.workbook_introspector import WorkbookIntrospector
from tests.conftest import build_profiled_custom_run_workbook, build_test_profile


def test_introspector_dumps_worksheet_preview(tmp_path: Path):
    workbook_path = tmp_path / "custom_run_filter.xlsx"
    build_profiled_custom_run_workbook(workbook_path)

    report = WorkbookIntrospector(preview_rows=5, preview_cols=4).inspect(workbook_path)

    assert len(report.worksheets) == 7
    assert report.worksheets[0].name == "TEST_meta_kv"
    assert report.worksheets[0].preview_rows


def test_production_workbook_missing_by_default():
    assert production_workbook_available() is False


def test_production_profile_missing_by_default():
    assert production_profile_available() is False


def test_load_production_profile_requires_committed_file():
    with pytest.raises(FileNotFoundError, match="Production Custom_Run_Filter profile is missing"):
        load_production_profile(PRODUCTION_AAPL_PROFILE)


@pytest.mark.production
def test_parse_production_aapl_workbook(production_custom_run_workbook):
    if not production_profile_available():
        pytest.skip(
            "Production profile not committed. Generate it from the real AAPL workbook first: "
            f"{PRODUCTION_AAPL_PROFILE}"
        )

    profile = load_production_profile()
    data = CustomRunParser(profile=profile).parse(
        production_custom_run_workbook,
        production_custom_run_workbook.name,
    )

    assert data.ticker
    assert data.metadata
    assert data.historical_metrics
    assert "metadata" in data.raw_sections


@pytest.mark.production
def test_production_workbook_rejects_invented_example_fixture():
    invented_fixture = Path(__file__).resolve().parents[1] / "fixtures" / "custom_run_filter_aapl.example.xlsx"
    if not invented_fixture.exists():
        pytest.skip("Invented Sprint 5 example fixture not present.")

    with pytest.raises(CustomRunParseError):
        CustomRunParser().parse(invented_fixture, invented_fixture.name)


def test_profile_json_round_trip():
    profile = build_test_profile()
    payload = profile.to_dict()
    restored = json.loads(json.dumps(payload))
    assert restored["sections"][0]["sheet_name"] == "TEST_meta_kv"
