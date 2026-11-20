"""A fiscal-year previous file (not the prior quarter): the Q2 data in the Last Quarter BS tab stays, only the I27:I32 carry-over stays blank."""

import datetime as dt
from pathlib import Path

from openpyxl import Workbook, load_workbook

from services.quarterly_model_continuity_service import QuarterlyModelContinuityService

SHEET = "Last Quarter BS Standardized"


def _book(path: Path, c_date: dt.date, d_date: dt.date) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws["C4"], ws["D4"] = c_date, d_date
    ws["A11"], ws["B11"], ws["C11"], ws["D11"] = "Cash", "BS_CASH", 100.0, 90.0
    ws["A12"], ws["B12"], ws["C12"], ws["D12"] = "Assets", "BS_TOT_ASSET", 500.0, 480.0
    wb.save(path)
    return path


def test_fiscal_year_previous_file_never_deletes_the_q2_data(tmp_path: Path):
    previous = _book(tmp_path / "prev_fy.xlsx", dt.date(2025, 12, 31), dt.date(2025, 9, 30))
    current = _book(tmp_path / "cur.xlsx", dt.date(2026, 9, 30), dt.date(2026, 6, 30))          # the template holds Q2 in column D
    QuarterlyModelContinuityService().align_prior_quarter_balance_sheet(previous_workbook_path=previous, workbook_path=current)
    ws = load_workbook(current)[SHEET]
    assert ws["D4"].value == dt.datetime(2026, 6, 30) and ws["D11"].value == 90.0 and ws["D12"].value == 480.0
