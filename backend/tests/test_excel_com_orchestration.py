"""Fixture tests for Excel COM orchestration.

Mock only the COM import/dispatch boundary. Formula preservation and cached-value
validation still run against the real workbook. These tests do not certify a company.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from services.excel_recalc_service import (
    EXCEL_COM_METHOD,
    ExcelRecalcService,
    genuine_excel_com_recalc,
)


def _formula_workbook(path: Path) -> Path:
    wb = Workbook()
    er = wb.active
    er.title = "Expected Returns & Buybacks"
    er["A2"] = 100
    er["C14"] = 160
    er["D14"] = 180
    er["E14"] = "=(C14/A2)^(1/10)-1"
    er["F14"] = "=(D14/A2)^(1/10)-1"
    ev = wb.create_sheet("Enterprise Value")
    for addr, val in {
        "B6": 0.1,
        "C6": 0.01,
        "B20": 50,
        "B27": 0.3,
        "B32": 40,
        "B42": 100,
        "B47": 0.12,
        "B48": 55,
    }.items():
        ev[addr] = val
    wb.save(path)
    wb.close()
    return path


def test_unmocked_recalc_is_unavailable_without_win32com(tmp_path: Path):
    if importlib.util.find_spec("win32com") is not None:
        pytest.skip("win32com is installed; genuine COM path is for Windows certification")
    path = _formula_workbook(tmp_path / "wb.xlsx")
    report = ExcelRecalcService().recalculate(analysis_id="t", ticker="ZZ", workbook_path=path)
    assert report.status == "UNAVAILABLE"
    assert report.com_invoked is False
    assert report.method == "none"
    assert not genuine_excel_com_recalc(report)
    assert "WORKBOOK_RECALCULATION_INCOMPLETE" in report.summary


def test_mocked_com_boundary_invokes_calculate_full_rebuild_and_still_validates(tmp_path: Path):
    path = _formula_workbook(tmp_path / "wb.xlsx")
    excel = MagicMock()
    workbook = MagicMock()
    excel.Workbooks.Open.return_value = workbook
    client = MagicMock()
    client.DispatchEx.return_value = excel
    pythoncom = MagicMock()

    with patch("services.excel_recalc_service.load_excel_com", return_value=(client, pythoncom)):
        report = ExcelRecalcService().recalculate(analysis_id="t", ticker="ZZ", workbook_path=path)

    client.DispatchEx.assert_called_once_with("Excel.Application")
    excel.CalculateFullRebuild.assert_called_once()
    workbook.Save.assert_called()
    assert excel.Workbooks.Open.call_count == 2
    assert report.com_invoked is True
    assert report.method == EXCEL_COM_METHOD
    # Mocked COM does not write Excel caches; validation must still fail those formula cells.
    assert report.status == "FAILED"
    assert any("E14" in c or "F14" in c for c in report.missing_cached_values)
    assert not genuine_excel_com_recalc(report)


def test_forged_ok_report_is_not_genuine():
    from services.excel_recalc_service import ExcelRecalcReport

    forged = ExcelRecalcReport(
        analysis_id="t",
        ticker="ZZ",
        status="ok",
        method="none",
        workbook_path="x.xlsx",
        com_invoked=False,
    )
    assert not genuine_excel_com_recalc(forged)
    also_forged = ExcelRecalcReport(
        analysis_id="t",
        ticker="ZZ",
        status="ok",
        method=EXCEL_COM_METHOD,
        workbook_path="x.xlsx",
        com_invoked=False,
    )
    assert not genuine_excel_com_recalc(also_forged)
