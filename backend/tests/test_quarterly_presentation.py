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
from tests.ledger_util import entry, notes_text
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


def test_isolated_gaps_are_incomplete(gap_quarterly_wb: Path):
    wb = load_workbook(gap_quarterly_wb)
    try:
        health = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
        decision = decide_presentation(health)
        assert decision == PresentationDecision.STATEMENT_INCOMPLETE
        assert health.isolated_gaps is True
        assert health.structural_failure is False
    finally:
        wb.close()


def test_structural_failure_is_incomplete(broken_quarterly_wb: Path):
    wb = load_workbook(broken_quarterly_wb)
    try:
        health = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
        assert health.structural_failure is True
        assert decide_presentation(health) == PresentationDecision.STATEMENT_INCOMPLETE
    finally:
        wb.close()


def test_income_notes_are_placed_below_margin_formulas():
    from models.quarterly_presentation import (
        BloombergHealthAssessment,
        QuarterlyStatementPresentation,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Last Quarter IS Standardized"
    ws["A11"] = "Revenue"
    ws["C11"] = 100
    ws["A77"] = "Gross Margin"
    ws["C77"] = '=IF(C11="","",C21/C11)'
    ws["A78"] = "Operating Margin"
    ws["A79"] = "Net Margin"
    health = BloombergHealthAssessment(
        statement=QuarterlyStatementKind.INCOME,
        sheet=ws.title,
        present=True,
        reason="test",
    )
    entry = QuarterlyStatementPresentation(
        statement=QuarterlyStatementKind.INCOME,
        sheet=ws.title,
        health=health,
        decision=PresentationDecision.BLOOMBERG_PRESERVE,
        reason="test",
        data_source_primary="sec",
    )
    QuarterlyPresentationService()._write_statement_notes(wb, [entry], 2026, "Q2")
    assert ws["A77"].value == "Gross Margin"
    assert str(ws["C77"].value).startswith("=IF")
    header_rows = [
        row
        for row in range(1, (ws.max_row or 1) + 1)
        if ws.cell(row, 1).value == "Notes"
    ]
    assert header_rows and header_rows[0] > 79


def test_blank_values_do_not_rebuild_an_intact_taxonomy():
    """Partial or blank values are incomplete input. HAP does not rebuild the taxonomy."""
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    _add_lq_sheets(wb)
    income = wb["Last Quarter IS Standardized"]
    _healthy_is(income)
    income["A9"] = "YTD"
    for row in range(20, 32):
        income.cell(row, 3).value = None
    cash_flow = wb["Last Quarter CF Standardized"]
    for row, label in enumerate(
        (
            "Cash from Operating Activities",
            "Cash from Investing Activities",
            "Cash from Financing Activities",
            "Capital Expenditures",
            "Depreciation & Amortization",
            "Change in Working Capital",
            "Dividends Paid",
            "Net Change in Cash",
        ),
        start=11,
    ):
        cash_flow.cell(row, 1, label)
    partial = assess_statement_health(wb, QuarterlyStatementKind.INCOME)
    blank = assess_statement_health(wb, QuarterlyStatementKind.CASH_FLOW)
    assert decide_presentation(partial) == PresentationDecision.STATEMENT_INCOMPLETE
    assert partial.structural_failure is False
    assert decide_presentation(blank) == PresentationDecision.STATEMENT_INCOMPLETE
    assert blank.structural_failure is False
    broken = Workbook()
    broken.active.title = "Income - GAAP"
    _add_lq_sheets(broken)
    broken["Last Quarter IS Standardized"]["A11"] = "Misc line"
    broken["Last Quarter IS Standardized"]["A12"] = "Other"
    missing = assess_statement_health(broken, QuarterlyStatementKind.INCOME)
    assert decide_presentation(missing) == PresentationDecision.STATEMENT_INCOMPLETE


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


def test_sec_cf_is_ytd_labeled_when_standalone_cannot_be_derived():
    items = extract_sec_10q_statement(
        _mock_companyfacts(),
        QuarterlyStatementKind.CASH_FLOW,
        fiscal_year=2024,
        fiscal_period="Q4",
        include_unresolved=False,
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
    assets = next(i for i in items if i.label == "Total assets")
    assert assets.duration_kind == "instant"
    assert assets.period_end == "2024-09-28"
    assert assets.period_start is None


def test_structural_failure_does_not_write_sec(
    broken_quarterly_wb: Path, tmp_path: Path
):
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
    assert is_stmt.decision == PresentationDecision.STATEMENT_INCOMPLETE
    assert "STATEMENT_INCOMPLETE" in is_stmt.reason
    assert report.input_blockers
    assert not is_stmt.sec_rows_introduced

    wb = load_workbook(dest)
    try:
        ws = wb["Last Quarter IS Standardized"]
        assert ws["C11"].value != pytest.approx(94930.0)
        assert any(str(ws.cell(r, 1).value) == "Misc line" for r in range(11, 25))
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
    is_stmt = next(s for s in report.statements if s.statement == QuarterlyStatementKind.INCOME)
    revenue = next(d for d in is_stmt.source_discrepancies if d["label"] == "Revenue")
    assert revenue["authority"] == "sec"
    assert revenue["sec_value"] != before_rev
    after = load_workbook(dest)
    try:
        # Layout and the supplied value stay. The SEC figure is recorded, not written.
        assert after["Last Quarter IS Standardized"]["C11"].value == before_rev
        assert revenue["workbook_value"] == before_rev
        assert revenue["action"] == "flag_for_upstream"
        # a material difference from SEC is flagged (source_discrepancies, shaded cell) but no longer blocks
        assert not any("STATEMENT_DISCREPANCY" in b for b in report.input_blockers)
        assert after["Last Quarter IS Standardized"]["A12"].value == "Cost of Revenue"
        assert after["Last Quarter IS Standardized"]["C2"].value == "=C4"
        assert any(
            after["Last Quarter IS Standardized"].cell(row, 1).value == "Notes"
            for row in range(1, (after["Last Quarter IS Standardized"].max_row or 1) + 1)
        )
    finally:
        after.close()


def test_labeled_blank_cash_flow_is_filled_from_sec(tmp_path: Path):
    """A labeled cash-flow line left blank is filled from the 10-Q (derived Q2) and flagged; the layout is not rebuilt."""
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    _add_lq_sheets(wb)
    _healthy_is(wb["Last Quarter IS Standardized"])
    _healthy_bs(wb["Last Quarter BS Standardized"])
    cf = wb["Last Quarter CF Standardized"]
    labels = [
        (11, "Cash from Operating Activities"),
        (12, "Cash from Investing Activities"),
        (13, "Cash from Financing Activities"),
        (14, "Capital Expenditures"),
        (15, "Depreciation & Amortization"),
        (16, "Change in Working Capital"),
        (17, "Dividends Paid"),
        (18, "Net Change in Cash"),
    ]
    for row, label in labels:
        cf.cell(row, 1, label)
    cf["E11"] = "=IF(C11=\"\",\"\",C11)"
    src = tmp_path / "blank_cf.xlsx"
    dest = tmp_path / "filled_cf.xlsx"
    wb.save(src)
    wb.close()
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "val": 109_417_000_000,
                                "fy": 2024,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2024-08-01",
                                "accn": "0000320193-24-000123",
                                "start": "2024-04-01",
                                "end": "2024-06-30",
                            }
                        ]
                    }
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "val": 30_000_000,
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-01",
                                "accn": "0000320193-24-000100",
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                            },
                            {
                                "val": 80_000_000,
                                "fy": 2024,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2024-08-01",
                                "accn": "0000320193-24-000123",
                                "start": "2024-01-01",
                                "end": "2024-06-30",
                            },
                        ]
                    }
                }
            }
        }
    }
    report = QuarterlyPresentationService().plan_and_apply(
        analysis_id="blank-cf",
        ticker="AAPL",
        source_workbook_path=src,
        destination_workbook_path=dest,
        company_facts=facts,
    )
    cf_stmt = next(s for s in report.statements if s.statement == QuarterlyStatementKind.CASH_FLOW)
    assert cf_stmt.decision == PresentationDecision.BLOOMBERG_PRESERVE
    assert not any("STATEMENT_INCOMPLETE" in blocker for blocker in report.input_blockers)
    assert not report.unresolved_dependencies
    assert any(item["label"] == "Cash from Operating Activities" for item in report.filled_from_sec)
    out = load_workbook(dest)
    try:
        sheet = out["Last Quarter CF Standardized"]
        assert sheet["A11"].value == "Cash from Operating Activities"
        assert sheet["C11"].value == pytest.approx(80.0)  # the cash-flow sheet is cumulative: 6M YTD, not the standalone Q2 (50)
        assert sheet["C11"].comment is None and entry(out, "Last Quarter CF Standardized", "C11", "Filled from filing")
        assert sheet["G11"].value in (None, "")
        assert sheet["E11"].value == '=IF(C11="","",C11)'
    finally:
        out.close()


def _idcc_comparative_facts() -> dict:
    """FY2026 Q2 filing columns, including prior-year facts tagged with the same fy/fp."""
    def series(unit, rows):
        return {"units": {unit: [
            {
                "val": value,
                "fy": 2026,
                "fp": fp,
                "form": "10-Q",
                "filed": "2026-07-30",
                "accn": "0001405495-26-000066",
                "start": start,
                "end": end,
            }
            for value, start, end, fp in rows
        ]}}

    return {"facts": {"us-gaap": {
        "EarningsPerShareDiluted": series("USD/shares", [
            (5.35, "2025-04-01", "2025-06-30", "Q2"),
            (8.81, "2025-01-01", "2025-06-30", "Q2"),
            (5.51, "2026-01-01", "2026-06-30", "Q2"),
            (3.4, "2026-04-01", "2026-06-30", "Q2"),
        ]),
        "EarningsPerShareBasic": series("USD/shares", [
            (6.97, "2025-04-01", "2025-06-30", "Q2"),
            (7.44, "2026-01-01", "2026-06-30", "Q2"),
            (4.51, "2026-04-01", "2026-06-30", "Q2"),
        ]),
        "NetIncomeLoss": series("USD", [
            (115_602_000, "2025-01-01", "2025-03-31", "Q2"),
            (296_170_000, "2025-01-01", "2025-06-30", "Q2"),
            (191_701_000, "2026-01-01", "2026-06-30", "Q2"),
            (116_372_000, "2026-04-01", "2026-06-30", "Q2"),
        ]),
        "RevenueFromContractWithCustomerExcludingAssessedTax": series("USD", [
            (300_596_000, "2025-04-01", "2025-06-30", "Q2"),
            (260_170_000, "2026-04-01", "2026-06-30", "Q2"),
        ]),
    }}}


def test_current_quarter_eps_and_net_income_are_not_prior_period_columns():
    from services.accounting_concept_matcher import interpret_workbook_label

    items = extract_sec_10q_statement(
        _idcc_comparative_facts(),
        QuarterlyStatementKind.INCOME,
        fiscal_year=2026,
        fiscal_period="Q2",
        include_unresolved=False,
    )
    diluted = next(item for item in items if item.xbrl_concept == "EarningsPerShareDiluted")
    basic = next(item for item in items if item.xbrl_concept == "EarningsPerShareBasic")
    net_income = next(item for item in items if item.xbrl_concept == "NetIncomeLoss")
    assert diluted.value == pytest.approx(3.4)
    assert diluted.period_start == "2026-04-01"
    assert diluted.period_end == "2026-06-30"
    assert diluted.extraction_method == "reported_standalone"
    assert diluted.unit == "USD/shares"
    assert diluted.ytd_value == pytest.approx(5.51)
    assert diluted.extraction_method != "derived_ytd_subtract"
    assert basic.value == pytest.approx(4.51)
    assert basic.period_start == "2026-04-01"
    assert basic.period_end == "2026-06-30"
    assert basic.unit == "USD/shares"
    assert basic.value != pytest.approx(diluted.value)
    assert net_income.value == pytest.approx(116.372)
    assert net_income.period_start == "2026-04-01"
    assert net_income.period_end == "2026-06-30"
    assert net_income.unit == "USD_millions"
    revenue = next(item for item in items if item.xbrl_concept == "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert revenue.value == pytest.approx(260.17)
    assert revenue.period_start == "2026-04-01"
    assert revenue.period_end == "2026-06-30"
    assert revenue.unit == "USD_millions"
    ytd_items = extract_sec_10q_statement(
        _idcc_comparative_facts(),
        QuarterlyStatementKind.INCOME,
        fiscal_year=2026,
        fiscal_period="Q2",
        duration_kind="ytd",
        include_unresolved=False,
    )
    diluted_ytd = next(item for item in ytd_items if item.xbrl_concept == "EarningsPerShareDiluted")
    assert diluted_ytd.duration_kind == "ytd"
    assert diluted_ytd.extraction_method == "reported_ytd"
    assert diluted_ytd.period_start == "2026-01-01"
    assert diluted_ytd.period_end == "2026-06-30"
    assert diluted_ytd.value == pytest.approx(5.51)
    assert diluted_ytd.value != pytest.approx(diluted.value)
    assert interpret_workbook_label("Diluted EPS, GAAP", QuarterlyStatementKind.INCOME) == ["diluted_eps"]
    assert interpret_workbook_label("Basic EPS, GAAP", QuarterlyStatementKind.INCOME) == ["basic_eps"]
    assert interpret_workbook_label("Diluted EPS from Cont Ops, Adjusted", QuarterlyStatementKind.INCOME) == []
    assert interpret_workbook_label("Basic EPS from Cont Ops, Adjusted", QuarterlyStatementKind.INCOME) == []
    assert interpret_workbook_label("EPS", QuarterlyStatementKind.INCOME) == []


def test_gaap_diluted_eps_conflict_keeps_adjusted_rows_and_formulas():
    from models.quarterly_presentation import BloombergHealthAssessment, QuarterlyStatementPresentation
    from services.quarterly_dependency_service import QuarterlyDependencyService

    facts = _idcc_comparative_facts()
    wb = Workbook()
    ws = wb.active
    ws.title = "Last Quarter IS Standardized"
    ws["A11"] = "Revenue"
    ws["C11"] = 260.17
    ws["A12"] = "    + Sales & Services Revenue"
    ws["C12"] = 110
    ws["A60"] = "Net Income, GAAP"
    ws["C60"] = 116.37
    ws["A67"] = "Basic EPS, GAAP"
    ws["C67"] = 4.51
    ws["A71"] = "Diluted EPS, GAAP"
    ws["C71"] = 1.11
    ws["A73"] = "Diluted EPS from Cont Ops, Adjusted"
    ws["C73"] = 3.38
    inputs = wb.create_sheet("Inputs")
    inputs["B5"] = "='Last Quarter IS Standardized'!C71"
    inputs["B6"] = "='Last Quarter IS Standardized'!C73"
    health = BloombergHealthAssessment(
        statement=QuarterlyStatementKind.INCOME,
        sheet=ws.title,
        present=True,
        reason="test",
    )
    entry = QuarterlyStatementPresentation(
        statement=QuarterlyStatementKind.INCOME,
        sheet=ws.title,
        health=health,
        decision=PresentationDecision.BLOOMBERG_PRESERVE,
        reason="test",
    )
    before = QuarterlyDependencyService().snapshot(wb)
    service = QuarterlyPresentationService()
    service._reconcile_populated_with_sec(wb, entry, facts, 2026, "Q2")
    after = QuarterlyDependencyService().reconnect(wb, before)
    diluted = next(d for d in entry.source_discrepancies if d["cell"].endswith("C71"))
    assert diluted["sec_value"] == pytest.approx(3.4)
    assert diluted["workbook_value"] == pytest.approx(1.11)
    assert diluted["action"] == "flag_for_upstream"
    assert ws["C71"].value == pytest.approx(1.11)
    assert ws["G71"].value in (None, "")
    assert ws["C67"].value == pytest.approx(4.51)
    assert ws["G67"].value in (None, "")
    assert ws["C73"].value == pytest.approx(3.38)
    assert ws["C12"].value == pytest.approx(110)
    assert ws["C60"].value == pytest.approx(116.37)
    assert ws["C11"].value == pytest.approx(260.17)
    assert inputs["B5"].value == "='Last Quarter IS Standardized'!C71"
    assert inputs["B6"].value == "='Last Quarter IS Standardized'!C73"
    assert after["changed_formulas"] == []
    assert after["unresolved_dependencies"] == []


def test_cash_flow_q2_uses_current_ytd_not_prior_year_columns():
    """Prior-year comparatives share fy/fp. Q2 cash flow is current 6-month minus current Q1."""
    def entry(value, start, end, fp):
        return {
            "val": value,
            "fy": 2026,
            "fp": fp,
            "form": "10-Q",
            "filed": "2026-07-30",
            "accn": "0001405495-26-000066",
            "start": start,
            "end": end,
        }

    facts = {"facts": {"us-gaap": {
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            entry(99_000_000, "2025-01-01", "2025-03-31", "Q1"),
            entry(16_081_000, "2026-01-01", "2026-03-31", "Q1"),
            entry(200_000_000, "2025-01-01", "2025-06-30", "Q2"),
            entry(98_617_000, "2026-01-01", "2026-06-30", "Q2"),
            entry(999_000_000, "2026-04-01", "2026-06-30", "Q2"),
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            entry(260_170_000, "2026-04-01", "2026-06-30", "Q2"),
        ]}},
    }}}
    items = extract_sec_10q_statement(
        facts,
        QuarterlyStatementKind.CASH_FLOW,
        fiscal_year=2026,
        fiscal_period="Q2",
        include_unresolved=False,
    )
    cfo = next(item for item in items if item.xbrl_concept == "NetCashProvidedByUsedInOperatingActivities")
    assert cfo.extraction_method == "derived_ytd_subtract"
    assert cfo.duration_kind == "standalone_quarter"
    assert cfo.value == pytest.approx(82.536)
    assert cfo.ytd_value == pytest.approx(98.617)
    assert cfo.period_end == "2026-06-30"
    assert "Q1 YTD 16.081" in (cfo.derivation or "")
    assert "Q2 YTD 98.617" in (cfo.derivation or "")
    ytd_items = extract_sec_10q_statement(
        facts,
        QuarterlyStatementKind.CASH_FLOW,
        fiscal_year=2026,
        fiscal_period="Q2",
        duration_kind="ytd",
        include_unresolved=False,
    )
    cfo_ytd = next(item for item in ytd_items if item.xbrl_concept == "NetCashProvidedByUsedInOperatingActivities")
    assert cfo_ytd.extraction_method == "reported_ytd"
    assert cfo_ytd.period_start == "2026-01-01"
    assert cfo_ytd.period_end == "2026-06-30"
    assert cfo_ytd.value == pytest.approx(98.617)



def test_cash_flow_fill_and_comparison_use_the_year_to_date_convention():
    from types import SimpleNamespace

    from models.quarterly_presentation import QuarterlyStatementKind
    from services.quarterly_presentation_service import sheet_value_for

    match = SimpleNamespace(value=50.0, sec_xbrl_concept="NetCashProvidedByUsedInOperatingActivities")
    items = [SimpleNamespace(xbrl_concept="NetCashProvidedByUsedInOperatingActivities", ytd_value=80.0)]
    assert sheet_value_for(QuarterlyStatementKind.CASH_FLOW, match, items, "Q2") == 80.0  # cumulative sheet
    assert sheet_value_for(QuarterlyStatementKind.CASH_FLOW, match, [], "Q2") is None      # no YTD companion: never fill the standalone
    assert sheet_value_for(QuarterlyStatementKind.CASH_FLOW, match, [], "Q1") == 50.0      # Q1: quarter == YTD
    assert sheet_value_for(QuarterlyStatementKind.INCOME, match, items, "Q2") == 50.0      # income cells are the quarter
