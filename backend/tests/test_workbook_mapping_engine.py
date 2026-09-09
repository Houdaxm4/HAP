"""Unit tests for M3 write-intent engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from canonical_model.company import CompanyFinancialModel
from canonical_model.primitives import FinancialPoint, FinancialSeries
from workbook_mapping.engine import (
    IntentDecision,
    WriteIntentValidationError,
    load_mapping_specification,
    map_model_to_write_intents,
    validate_write_intents,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "workbook_mapping" / "Workbook_Manifest.json"
MAPPING_JSON = ROOT / "docs" / "workbook_mapping" / "CFM_Workbook_Mapping.json"


def _series(name: str, values: dict[str, float]) -> FinancialSeries:
    return FinancialSeries(
        name=name,
        points=[
            FinancialPoint(
                period=period,
                value=value,
                currency="USD",
                source="test",
                confidence=0.95,
            )
            for period, value in values.items()
        ],
    )


@pytest.fixture
def fixture_cfm() -> CompanyFinancialModel:
    model = CompanyFinancialModel(
        analysis_id="m3-test",
        ticker="AAPL",
        company="Apple Inc.",
    )
    model.income_statement.revenue = _series(
        "Revenue",
        {"FY2023": 383_285_000_000.0, "FY2024": 391_035_000_000.0},
    )
    model.income_statement.net_income = _series(
        "Net Income",
        {"FY2024": 93_736_000_000.0},
    )
    model.balance_sheet.total_assets = _series(
        "Total Assets",
        {"FY2024": 364_980_000_000.0},
    )
    model.refresh_periods()
    return model


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_map_model_emits_write_scaled_revenue(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    assert report.write_count >= 1

    revenue_fy2024 = [
        i
        for i in report.intents
        if i.mapping_id == "is.revenue"
        and i.period == "FY2024"
        and i.decision == IntentDecision.WRITE
    ]
    assert len(revenue_fy2024) == 1
    intent = revenue_fy2024[0]
    assert intent.sheet == "Income - GAAP"
    assert intent.cell == "K9"  # FY2024 in C..L → FY2016..FY2025
    assert intent.value == pytest.approx(391_035.0)
    assert intent.transformation == "divide_by_1_000_000"
    assert intent.existing_cell_classification == "Writable Input"
    assert intent.write_policy_result.startswith("writable:")
    assert intent.metric == "Revenue"


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_null_periods_are_skip_not_invented(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    revenue_fy2016 = [
        i for i in report.intents if i.mapping_id == "is.revenue" and i.period == "FY2016"
    ]
    assert revenue_fy2016
    assert all(i.decision == IntentDecision.SKIP for i in revenue_fy2016)
    assert all(i.value is None for i in revenue_fy2016)


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_validate_returns_only_write(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    approved = validate_write_intents(report)
    assert approved
    assert all(i.decision == IntentDecision.WRITE for i in approved)
    assert all(i.value is not None for i in approved)


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_conflict_fails_validation(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    approved = [
        i
        for i in report.intents
        if i.decision == IntentDecision.WRITE and isinstance(i.value, (int, float))
    ]
    assert approved
    clone = approved[0].model_copy(deep=True)
    clone.intent_id = clone.intent_id + ":dup"
    clone.mapping_id = clone.mapping_id + ".dup"
    clone.value = float(clone.value) + 1.0
    clone.decision = IntentDecision.BLOCK
    clone.write_policy_result = "ambiguous_conflict"
    clone.reason = "synthetic conflict"
    approved[0].decision = IntentDecision.BLOCK
    approved[0].write_policy_result = "ambiguous_conflict"
    approved[0].reason = "synthetic conflict"
    report.intents.append(clone)
    with pytest.raises(WriteIntentValidationError, match="ambiguous conflict"):
        validate_write_intents(report)


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_control_ticker_write(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    tickers = [
        i for i in report.intents if i.cfm_path == "ticker" and i.decision == IntentDecision.WRITE
    ]
    assert tickers
    assert all(i.value == "AAPL" for i in tickers)
    assert all(i.sheet in (
        "Income - GAAP",
        "Balance Sheet - Standardized",
        "Cash Flow - Standardized",
    ) for i in tickers)


@pytest.mark.skipif(not MAPPING_JSON.exists() and not MANIFEST.exists(), reason="mapping docs missing")
def test_period_tokens_not_silently_remapped(fixture_cfm: CompanyFinancialModel):
    mapping = load_mapping_specification()
    report = map_model_to_write_intents(fixture_cfm, mapping)
    period_map = next(p for p in mapping.period_column_maps if p.sheet == "Income - GAAP")
    for intent in report.intents:
        if intent.mapping_id != "is.revenue" or intent.decision != IntentDecision.WRITE:
            continue
        col = "".join(ch for ch in intent.cell if ch.isalpha())
        assert period_map.columns[col] == intent.period
