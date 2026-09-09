"""Tests for analysis-type-scoped completion."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from models.completion import CompletionDecision
from services.completion_scope import (
    AnalysisTypeMode,
    WorkbookSection,
    assess_quarterly_bloomberg_health,
    classify_workbook_section,
    is_required_for_mode,
    normalize_analysis_type,
    sections_for_mode,
)
from services.completion_service import CompletionService
from workbook_mapping.engine import IntentDecision, WriteIntent, WriteIntentReport


def _intent(
    *,
    intent_id: str,
    cell: str,
    value,
    sheet: str = "Income - GAAP",
    period: str = "FY2018",
    metric: str = "Revenue",
    cfm_path: str = "income_statement.revenue",
    decision: IntentDecision = IntentDecision.WRITE,
) -> WriteIntent:
    return WriteIntent(
        intent_id=intent_id,
        mapping_id=intent_id,
        sheet=sheet,
        cell=cell,
        metric=metric,
        period=period,
        value=value,
        source="sec_companyfacts",
        write_policy_result="writable:Hybrid",
        decision=decision,
        reason="test",
        cfm_path=cfm_path,
        confidence=0.9,
        existing_cell_classification="Writable Input",
    )


def _populate_healthy_quarterly(ws, kind: str) -> None:
    """Labeled + populated LQ body so health → BLOOMBERG_PRESERVE."""
    if kind == "IS":
        rows = [
            (11, "Revenue", 100000),
            (12, "Cost of Revenue", 50000),
            (13, "Gross Profit", 50000),
            (14, "Operating Income", 30000),
            (15, "Net Income", 25000),
        ]
    elif kind == "BS":
        rows = [
            (11, "Cash", 10000),
            (12, "Total current assets", 50000),
            (13, "Total assets", 100000),
            (14, "Total current liabilities", 20000),
            (15, "Total liabilities", 40000),
            (16, "Total shareholders equity", 60000),
        ]
    else:
        rows = [
            (11, "Cash from Operating Activities", 40000),
            (12, "Cash from Investing Activities", -10000),
            (13, "Cash from Financing Activities", -5000),
        ]
    for r, label, val in rows:
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=3, value=val)
    # Extra labeled populated rows to clear MIN_EXPECTED_ROWS
    for r in range(20, 30):
        ws.cell(row=r, column=1, value=f"Line {r}")
        ws.cell(row=r, column=3, value=float(r))


@pytest.fixture
def scoped_workbook(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Income - GAAP"
    ws["C3"] = "FY2025"  # End Year → annual_update target
    ws["E9"] = 265595  # FY2018 populated
    ws["L9"] = None  # FY2025 blank (col L = last annual col in mapping)
    ws["F9"] = None  # FY2019 blank

    tax = wb.create_sheet("Tax")
    tax["C10"] = None  # blank tax cell

    pe = wb.create_sheet("PE10")
    pe["B2"] = None

    current = wb.create_sheet("Current")
    current["B2"] = 190.0

    for name, kind in (
        ("Last Quarter IS Standardized", "IS"),
        ("Last Quarter BS Standardized", "BS"),
        ("Last Quarter CF Standardized", "CF"),
    ):
        q = wb.create_sheet(name)
        _populate_healthy_quarterly(q, kind)

    path = tmp_path / "scoped.xlsx"
    wb.save(path)
    wb.close()
    return path


@pytest.fixture
def empty_quarterly_workbook(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.active.title = "Income - GAAP"
    for name in (
        "Last Quarter IS Standardized",
        "Last Quarter BS Standardized",
        "Last Quarter CF Standardized",
    ):
        wb.create_sheet(name)  # empty grids
    path = tmp_path / "empty_q.xlsx"
    wb.save(path)
    wb.close()
    return path


def test_normalize_analysis_type_aliases():
    assert normalize_analysis_type("New Company") == AnalysisTypeMode.NEW_COMPANY
    assert normalize_analysis_type("annual_update") == AnalysisTypeMode.ANNUAL_UPDATE
    assert normalize_analysis_type("Quarterly Update") == AnalysisTypeMode.QUARTERLY_UPDATE


def test_mode_section_matrix():
    assert WorkbookSection.TAX in sections_for_mode(AnalysisTypeMode.NEW_COMPANY)
    assert WorkbookSection.ANNUAL_INCOME not in sections_for_mode(AnalysisTypeMode.NEW_COMPANY)
    assert WorkbookSection.ANNUAL_INCOME in sections_for_mode(AnalysisTypeMode.ANNUAL_UPDATE)
    assert WorkbookSection.QUARTERLY_INCOME in sections_for_mode(
        AnalysisTypeMode.QUARTERLY_UPDATE
    )
    assert WorkbookSection.ANNUAL_INCOME not in sections_for_mode(
        AnalysisTypeMode.QUARTERLY_UPDATE
    )


def test_identical_cell_different_decisions_by_analysis_type(scoped_workbook: Path):
    """Same blank historical revenue cell: OUT_OF_SCOPE vs FILL depending on mode."""
    intents = WriteIntentReport(
        analysis_id="scope1",
        ticker="AAPL",
        intents=[
            _intent(
                intent_id="is.revenue:F9",
                cell="F9",
                value=260174.0,
                period="FY2019",
            ),
            _intent(
                intent_id="is.revenue:L9",
                cell="L9",
                value=400000.0,
                period="FY2025",
            ),
            _intent(
                intent_id="tax.etr:C10",
                cell="C10",
                value=0.21,
                sheet="Tax",
                period="FY2025",
                metric="Effective Tax Rate",
                cfm_path="tax.effective_tax_rate",
            ),
        ],
        write_count=3,
    )

    nc, nc_fill = CompletionService().plan(
        analysis_id="scope1",
        ticker="AAPL",
        analysis_type="new_company",
        source_workbook_path=scoped_workbook,
        intent_report=intents,
    )
    au, au_fill = CompletionService().plan(
        analysis_id="scope1",
        ticker="AAPL",
        analysis_type="annual_update",
        source_workbook_path=scoped_workbook,
        intent_report=intents,
        target_fiscal_year="FY2025",
    )

    nc_by_id = {e.intent_id: e for e in nc.entries}
    au_by_id = {e.intent_id: e for e in au.entries}

    # Historical blank under new_company → OUT_OF_SCOPE (not auto-fill)
    assert nc_by_id["is.revenue:F9"].decision == CompletionDecision.OUT_OF_SCOPE
    assert nc_by_id["is.revenue:F9"].required_for_mode is False
    assert nc_fill.write_count == 1  # only tax FILL

    # Same cell under annual_update with target FY2025 → still OUT_OF_SCOPE (prior year)
    assert au_by_id["is.revenue:F9"].decision == CompletionDecision.OUT_OF_SCOPE

    # New FY blank under annual_update → FILL
    assert au_by_id["is.revenue:L9"].decision == CompletionDecision.FILL
    assert au_by_id["is.revenue:L9"].required_for_mode is True

    # New FY blank under new_company → OUT_OF_SCOPE (annual statements not in scope)
    assert nc_by_id["is.revenue:L9"].decision == CompletionDecision.OUT_OF_SCOPE

    # Tax in scope for both new_company and annual_update (target year)
    assert nc_by_id["tax.etr:C10"].decision == CompletionDecision.FILL
    assert au_by_id["tax.etr:C10"].decision == CompletionDecision.FILL


def test_new_company_does_not_rewrite_historical(scoped_workbook: Path):
    intents = WriteIntentReport(
        analysis_id="nc",
        ticker="AAPL",
        intents=[
            _intent(
                intent_id="is.revenue:E9",
                cell="E9",
                value=265595.0,
                period="FY2018",
            )
        ],
        write_count=1,
    )
    completion, fill = CompletionService().plan(
        analysis_id="nc",
        ticker="AAPL",
        analysis_type="new_company",
        source_workbook_path=scoped_workbook,
        intent_report=intents,
    )
    assert completion.entries[0].decision == CompletionDecision.OUT_OF_SCOPE
    assert completion.entries[0].workbook_section == WorkbookSection.ANNUAL_INCOME.value
    assert fill.write_count == 0


def test_annual_update_prior_years_out_of_scope(scoped_workbook: Path):
    intents = WriteIntentReport(
        analysis_id="au",
        ticker="AAPL",
        intents=[
            _intent(intent_id="is.revenue:E9", cell="E9", value=265595.0, period="FY2018"),
            _intent(intent_id="is.revenue:L9", cell="L9", value=391035.0, period="FY2025"),
        ],
        write_count=2,
    )
    completion, fill = CompletionService().plan(
        analysis_id="au",
        ticker="AAPL",
        analysis_type="Annual Update",
        source_workbook_path=scoped_workbook,
        intent_report=intents,
        target_fiscal_year="FY2025",
    )
    by_id = {e.intent_id: e for e in completion.entries}
    assert by_id["is.revenue:E9"].decision == CompletionDecision.OUT_OF_SCOPE
    assert by_id["is.revenue:L9"].decision == CompletionDecision.FILL
    assert completion.target_fiscal_year == "FY2025"
    assert fill.write_count == 1


def test_quarterly_populated_preserves_bloomberg(scoped_workbook: Path):
    intents = WriteIntentReport(
        analysis_id="q1",
        ticker="AAPL",
        intents=[
            _intent(
                intent_id="lq.is:C11",
                cell="C11",
                value=50.0,
                sheet="Last Quarter IS Standardized",
                period="LQ",
                metric="Revenue",
                cfm_path="income_statement.revenue",
            ),
            _intent(
                intent_id="is.revenue:E9",
                cell="E9",
                value=265595.0,
                period="FY2018",
            ),
        ],
        write_count=2,
    )
    completion, fill = CompletionService().plan(
        analysis_id="q1",
        ticker="AAPL",
        analysis_type="quarterly_update",
        source_workbook_path=scoped_workbook,
        intent_report=intents,
    )
    by_id = {e.intent_id: e for e in completion.entries}
    assert by_id["is.revenue:E9"].decision == CompletionDecision.OUT_OF_SCOPE
    # C11 Revenue already populated → BLOOMBERG_PRESERVE → ALREADY_PRESENT
    assert by_id["lq.is:C11"].decision == CompletionDecision.ALREADY_PRESENT
    assert completion.sec_quarterly_fallback_required is False
    assert fill.write_count == 0


def test_quarterly_empty_emits_sec_fallback(empty_quarterly_workbook: Path):
    intents = WriteIntentReport(
        analysis_id="q2",
        ticker="AAPL",
        intents=[
            _intent(
                intent_id="lq.is:C9",
                cell="C9",
                value=50.0,
                sheet="Last Quarter IS Standardized",
                period="LQ",
                metric="Revenue",
                cfm_path="income_statement.revenue",
            )
        ],
        write_count=1,
    )
    completion, fill = CompletionService().plan(
        analysis_id="q2",
        ticker="AAPL",
        analysis_type="quarterly_update",
        source_workbook_path=empty_quarterly_workbook,
        intent_report=intents,
    )
    assert completion.sec_quarterly_fallback_required is True
    assert completion.entries[0].decision == CompletionDecision.YAHOO_QUARTERLY_FALLBACK_REQUIRED
    assert fill.write_count == 0
    assert fill.intents[0].decision == IntentDecision.SKIP


def test_classify_and_required_helpers():
    assert (
        classify_workbook_section(sheet="Tax", metric="ETR", cfm_path="tax.etr")
        == WorkbookSection.TAX
    )
    assert is_required_for_mode(
        AnalysisTypeMode.ANNUAL_UPDATE,
        WorkbookSection.ANNUAL_INCOME,
        "FY2025",
        target_fiscal_year="FY2025",
    )
    assert not is_required_for_mode(
        AnalysisTypeMode.ANNUAL_UPDATE,
        WorkbookSection.ANNUAL_INCOME,
        "FY2018",
        target_fiscal_year="FY2025",
    )


def test_assess_quarterly_health_on_empty(empty_quarterly_workbook: Path):
    from openpyxl import load_workbook

    wb = load_workbook(empty_quarterly_workbook)
    try:
        health = assess_quarterly_bloomberg_health(wb)
    finally:
        wb.close()
    assert health["sec_quarterly_fallback_required"] is True
