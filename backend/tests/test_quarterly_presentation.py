"""Focused tests: quarterly SEC 10-Q presentation authority."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from models.quarterly_presentation import (
    PresentationDecision,
    QuarterlyStatementKind,
)
from services.quarterly_health_service import (
    assess_statement_health,
    decide_presentation,
)
from services.quarterly_presentation_service import QuarterlyPresentationService
from services.sec_10q_statement_service import (
    classify_duration_from_dates,
    extract_sec_10q_statement,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_lq_sheets(wb: Workbook) -> None:
    for name in (
        "Last Quarter IS Standardized",
        "Last Quarter BS Standardized",
        "Last Quarter CF Standardized",
    ):
        if name not in wb.sheetnames:
            wb.create_sheet(name)


def _healthy_is(ws) -> None:
    data = [
        (11, "Revenue", 109417),
        (12, "Cost of Revenue", 54647),
        (13, "Gross Profit", 54770),
        (14, "Operating Income", 30000),
        (15, "Net Income", 25000),
    ]
    for r, lab, val in data:
        ws.cell(r, 1, lab)
        ws.cell(r, 3, val)
    for r in range(20, 32):
        ws.cell(r, 1, f"Detail {r}")
        ws.cell(r, 3, 10.0)


def _healthy_bs(ws) -> None:
    data = [
        (11, "Cash", 1000),
        (12, "Total current assets", 5000),
        (13, "Total assets", 20000),
        (14, "Total liabilities", 8000),
        (15, "Total shareholders equity", 12000),
    ]
    for r, lab, val in data:
        ws.cell(r, 1, lab)
        ws.cell(r, 3, val)
    for r in range(20, 32):
        ws.cell(r, 1, f"BS Line {r}")
        ws.cell(r, 3, 5.0)


def _healthy_cf(ws) -> None:
    data = [
        (11, "Cash from Operating Activities", 40000),
        (12, "Cash from Investing Activities", -10000),
        (13, "Cash from Financing Activities", -5000),
    ]
    for r, lab, val in data:
        ws.cell(r, 1, lab)
        ws.cell(r, 3, val)
    for r in range(20, 32):
        ws.cell(r, 1, f"CF Line {r}")
        ws.cell(r, 3, 1.0)


@pytest.fixture
def healthy_quarterly_wb(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    _add_lq_sheets(wb)
    _healthy_is(wb["Last Quarter IS Standardized"])
    _healthy_bs(wb["Last Quarter BS Standardized"])
    _healthy_cf(wb["Last Quarter CF Standardized"])
    # Formula outside body — must survive SEC replacement on other sheets / regions
    wb["Last Quarter IS Standardized"]["C2"] = "=C4"
    wb["Last Quarter IS Standardized"]["C4"] = "2026-06-27"
    path = tmp_path / "healthy_q.xlsx"
    wb.save(path)
    wb.close()
    return path


@pytest.fixture
def gap_quarterly_wb(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    _add_lq_sheets(wb)
    _healthy_is(wb["Last Quarter IS Standardized"])
    _healthy_bs(wb["Last Quarter BS Standardized"])
    _healthy_cf(wb["Last Quarter CF Standardized"])
    # Isolate 1–2 blanks on IS (still majors present)
    wb["Last Quarter IS Standardized"]["C20"] = None
    wb["Last Quarter IS Standardized"]["C21"] = None
    path = tmp_path / "gap_q.xlsx"
    wb.save(path)
    wb.close()
    return path


@pytest.fixture
def broken_quarterly_wb(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    _add_lq_sheets(wb)
    # Structural: few labels, missing majors
    ws = wb["Last Quarter IS Standardized"]
    ws["A11"] = "Misc line"
    ws["C11"] = None
    ws["A12"] = "Other"
    ws["C12"] = None
    # Leave BS/CF empty → also structural
    path = tmp_path / "broken_q.xlsx"
    wb.save(path)
    wb.close()
    return path


def _mock_companyfacts() -> dict:
    """Minimal facts: 3-month IS revenue + YTD operating CF + BS instant."""
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 94_930_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2024-06-30",
                                "end": "2024-09-28",
                            },
                            {
                                # YTD (~9 months) — must NOT be selected for IS quarter
                                "val": 200_000_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                            },
                        ]
                    },
                },
                "GrossProfit": {
                    "units": {
                        "USD": [
                            {
                                "val": 43_879_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2024-06-30",
                                "end": "2024-09-28",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 14_000_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2024-06-30",
                                "end": "2024-09-28",
                            }
                        ]
                    }
                },
                "OperatingIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 29_000_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2024-06-30",
                                "end": "2024-09-28",
                            }
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "val": 365_000_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "end": "2024-09-28",
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "val": 90_000_000_000,
                                "fy": 2024,
                                "fp": "Q4",
                                "form": "10-Q",
                                "filed": "2024-11-01",
                                "accn": "0000320193-24-000001",
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                            }
                        ]
                    }
                },
            }
        }
    }


def test_healthy_bloomberg_preserve(healthy_quarterly_wb: Path):
    wb = load_workbook(healthy_quarterly_wb)
    try:
        health = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
        assert decide_presentation(health) == PresentationDecision.BLOOMBERG_PRESERVE
    finally:
        wb.close()


def test_isolated_gaps_fill_gaps(gap_quarterly_wb: Path):
    wb = load_workbook(gap_quarterly_wb)
    try:
        health = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
        decision = decide_presentation(health)
        assert decision == PresentationDecision.BLOOMBERG_FILL_GAPS
        assert health.isolated_gaps is True
        assert health.structural_failure is False
    finally:
        wb.close()


def test_structural_broken_yahoo_basic_required(broken_quarterly_wb: Path):
    wb = load_workbook(broken_quarterly_wb)
    try:
        health = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
        assert health.structural_failure is True
        assert decide_presentation(health) == PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED
    finally:
        wb.close()


def test_duration_quarter_vs_ytd():
    assert (
        classify_duration_from_dates("2024-06-30", "2024-09-28") == "standalone_quarter"
    )
    assert classify_duration_from_dates("2023-10-01", "2024-09-28") == "ytd"
    assert classify_duration_from_dates(None, "2024-09-28") == "instant"


def test_sec_is_uses_standalone_not_ytd():
    items = extract_sec_10q_statement(
        _mock_companyfacts(),
        QuarterlyStatementKind.INCOME,
        fiscal_year=2024,
        fiscal_period="Q4",
    )
    rev = next(i for i in items if i.label == "Revenue")
    assert rev.duration_kind == "standalone_quarter"
    assert rev.value == pytest.approx(94930.0)  # millions
    assert rev.period_start == "2024-06-30"


def test_sec_cf_is_ytd_labeled():
    items = extract_sec_10q_statement(
        _mock_companyfacts(),
        QuarterlyStatementKind.CASH_FLOW,
        fiscal_year=2024,
        fiscal_period="Q4",
    )
    assert items
    assert all(i.duration_kind == "ytd" for i in items)


def test_sec_bs_instant_quarter_end():
    items = extract_sec_10q_statement(
        _mock_companyfacts(),
        QuarterlyStatementKind.BALANCE_SHEET,
        fiscal_year=2024,
        fiscal_period="Q4",
    )
    assets = next(i for i in items if "assets" in i.label.lower())
    assert assets.duration_kind == "instant"
    assert assets.period_end == "2024-09-28"
    assert assets.period_start is None


def test_yahoo_basic_template_replaces_bloomberg_structure(
    broken_quarterly_wb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from services.yahoo_quarterly_statement_service import YahooQuarterSnapshot, YahooQuarterlyBundle

    def _mock_fetch(_ticker: str) -> YahooQuarterlyBundle:
        snap = YahooQuarterSnapshot(
            end_date="2024-09-30",
            fields={
                "totalRevenue": 94930.0,
                "costOfRevenue": 51000.0,
                "totalOperatingExpenses": 15000.0,
                "operatingIncome": 29000.0,
                "netIncome": 14000.0,
                "basicEPS": 0.93,
                "dilutedEPS": 0.92,
            },
        )
        return YahooQuarterlyBundle(income_quarters=[snap, snap, snap, snap, snap])

    monkeypatch.setattr(
        "services.quarterly_presentation_service.YahooQuarterlyStatementService.fetch",
        lambda self, ticker: _mock_fetch(ticker),
    )

    dest = tmp_path / "completed.xlsx"
    upload_hash = _sha(broken_quarterly_wb)
    report = QuarterlyPresentationService().plan_and_apply(
        analysis_id="yahoo1",
        ticker="AAPL",
        source_workbook_path=broken_quarterly_wb,
        destination_workbook_path=dest,
        company_facts=_mock_companyfacts(),
    )
    assert _sha(broken_quarterly_wb) == upload_hash
    is_stmt = next(s for s in report.statements if s.statement == QuarterlyStatementKind.INCOME)
    assert is_stmt.decision == PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED
    assert is_stmt.yahoo_rows_introduced
    assert is_stmt.rows_superseded

    wb = load_workbook(dest)
    try:
        ws = wb["Last Quarter IS Standardized"]
        assert ws["A11"].value == "Total Revenues"
        assert ws["C11"].value == pytest.approx(94930.0)
        assert "Yahoo Finance basic template" in str(ws["A7"].value)
        assert not any(str(ws.cell(r, 1).value) == "Misc line" for r in range(11, 25))
    finally:
        wb.close()


def test_formulas_outside_body_preserved(broken_quarterly_wb: Path, tmp_path: Path):
    # Add formula outside body on broken IS sheet
    wb = load_workbook(broken_quarterly_wb)
    wb["Last Quarter IS Standardized"]["C2"] = "=C4"
    wb["Last Quarter IS Standardized"]["C4"] = "keep-me"
    wb.save(broken_quarterly_wb)
    wb.close()

    dest = tmp_path / "out.xlsx"
    QuarterlyPresentationService().plan_and_apply(
        analysis_id="f1",
        ticker="AAPL",
        source_workbook_path=broken_quarterly_wb,
        destination_workbook_path=dest,
        company_facts=_mock_companyfacts(),
    )
    out = load_workbook(dest)
    try:
        assert out["Last Quarter IS Standardized"]["C2"].value == "=C4"
        assert out["Last Quarter IS Standardized"]["C2"].data_type == "f"
        assert out["Last Quarter IS Standardized"]["C4"].value == "keep-me"
    finally:
        out.close()


def test_preserve_does_not_rewrite_healthy(healthy_quarterly_wb: Path, tmp_path: Path):
    dest = tmp_path / "p.xlsx"
    before = load_workbook(healthy_quarterly_wb)
    try:
        before_rev = before["Last Quarter IS Standardized"]["C11"].value
    finally:
        before.close()
    report = QuarterlyPresentationService().plan_and_apply(
        analysis_id="p1",
        ticker="AAPL",
        source_workbook_path=healthy_quarterly_wb,
        destination_workbook_path=dest,
        company_facts=_mock_companyfacts(),
    )
    assert all(
        s.decision == PresentationDecision.BLOOMBERG_PRESERVE for s in report.statements
    )
    after = load_workbook(dest)
    try:
        assert after["Last Quarter IS Standardized"]["C11"].value == before_rev
        assert after["Last Quarter IS Standardized"]["A12"].value == "Cost of Revenue"
    finally:
        after.close()
