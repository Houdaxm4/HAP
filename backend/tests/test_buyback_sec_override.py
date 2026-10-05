"""Bloomberg buyback figures are always replaced by SEC figures (new company: every year; annual update: newest year only)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from models.new_company import BuybackYearResult
from services.new_company_buyback_service import NewCompanyBuybackService


def _workbook(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Income - GAAP"
    ws["A5"] = "Fiscal Year"
    for i, fy in enumerate((2023, 2024, 2025), start=3):
        ws.cell(5, i).value = f"FY{fy}"
    ws["A10"] = "Repurchase of common stock"
    ws["A11"] = "Shares repurchased"
    for col, (dollars, shares) in zip((3, 4, 5), ((100.0, 5.0), (200.0, 8.0), (300.0, 10.0))):
        ws.cell(10, col).value = dollars
        ws.cell(11, col).value = shares
    wb.save(path)
    return path


def _years() -> list[BuybackYearResult]:
    return [
        BuybackYearResult(fiscal_year="FY2023", dollars=104.0, shares=5.2, dollars_source="sec", shares_source="sec"),
        BuybackYearResult(fiscal_year="FY2024", dollars=210.0, shares=8.1, dollars_source="sec", shares_source="sec"),
        BuybackYearResult(fiscal_year="FY2025", dollars=312.0, shares=10.4, dollars_source="sec", shares_source="sec"),
    ]


def test_new_company_overrides_every_year_even_small_differences(tmp_path: Path):
    path = _workbook(tmp_path / "wb.xlsx")
    NewCompanyBuybackService()._write_buyback_schedule(path, _years(), write_policy="new_company", new_fiscal_year=None)
    ws = load_workbook(path)["Income - GAAP"]
    assert [ws.cell(10, c).value for c in (3, 4, 5)] == [104.0, 210.0, 312.0]
    assert [ws.cell(11, c).value for c in (3, 4, 5)] == [5.2, 8.1, 10.4]
    ledger = load_workbook(path)["HAP Adjustments"]
    assert ledger["E5"].value == "SEC override of Bloomberg"
    assert "ADJ-" in ws["C10"].comment.text


def test_annual_update_overrides_only_the_newest_year(tmp_path: Path):
    path = _workbook(tmp_path / "wb.xlsx")
    NewCompanyBuybackService()._write_buyback_schedule(path, _years(), write_policy="annual_update", new_fiscal_year="FY2025")
    ws = load_workbook(path)["Income - GAAP"]
    assert ws["E10"].value == 312.0 and ws["E11"].value == 10.4  # newest year replaced
    assert ws["C10"].value == 100.0 and ws["D10"].value == 200.0  # earlier years copied from the previous file
    assert ws["C11"].value == 5.0 and ws["D11"].value == 8.0


def test_rounding_noise_is_not_an_adjustment(tmp_path: Path):
    path = _workbook(tmp_path / "wb.xlsx")
    years = [BuybackYearResult(fiscal_year="FY2023", dollars=100.0004, shares=5.0, dollars_source="sec", shares_source="sec")]
    NewCompanyBuybackService()._write_buyback_schedule(path, years, write_policy="new_company", new_fiscal_year=None)
    wb = load_workbook(path)
    assert wb["Income - GAAP"]["C10"].value == 100.0
    assert "HAP Adjustments" not in wb.sheetnames
