from openpyxl import Workbook

from services.rd_layout import insert_lookback_columns, rd_year_columns, shift_references


def _book():
    wb = Workbook()
    inputs = wb.active
    inputs.title = "Inputs"
    for i, col in enumerate("CDE"):
        inputs[f"{col}1"] = f"FY{2016 + i}"
    rd = wb.create_sheet("R&D")
    rd["B1"] = '="FY "&RIGHT(C1,4)-1'
    rd["C1"] = "=Inputs!C1"
    rd["D1"] = "=Inputs!D1"
    rd["B2"] = 10.0
    rd["C2"] = '=IF(Inputs!C103="",0,Inputs!C103)'
    rd["C3"] = "=C2+B2*1/2"
    rd["C4"] = "=(C2+B2)/2"
    ic = wb.create_sheet("IC")
    ic["A1"] = "='R&D'!C3"
    ic["A2"] = "=SUM('R&D'!C3:D3)"
    return wb


def test_references_into_the_block_move_with_it():
    assert shift_references("='R&D'!N3", in_rd_sheet=False, count=3, last_col=14) == "='R&D'!Q3"
    assert shift_references("=B8*2", in_rd_sheet=True, count=3, last_col=14) == "=B8*2"
    assert shift_references("=Inputs!C103", in_rd_sheet=True, count=3, last_col=14) == "=Inputs!C103"


def test_block_shifts_right_and_new_years_are_added_on_the_left():
    wb = _book()
    headers = insert_lookback_columns(wb, 2)
    rd = wb["R&D"]
    assert headers == ["R&D!B1", "R&D!C1"]
    assert rd["B1"].value == '="FY "&RIGHT(C1,4)-1' and rd["C1"].value == '="FY "&RIGHT(D1,4)-1'
    assert rd["D1"].value == '="FY "&RIGHT(E1,4)-1'          # the old pre-window header moved with its neighbours
    assert rd["D2"].value == 10.0 and rd["B2"].value is None
    assert rd["E1"].value == "=Inputs!C1" and rd["E3"].value == "=E2+D2*1/2"
    assert wb["IC"]["A1"].value == "='R&D'!E3" and wb["IC"]["A2"].value == "=SUM('R&D'!E3:F3)"
    cols = rd_year_columns(rd, {"FY2016": 3, "FY2017": 4, "FY2018": 5})
    assert cols == {"FY2016": 5, "FY2017": 6, "FY2018": 7}


def test_nothing_to_shift():
    wb = _book()
    assert insert_lookback_columns(wb, 0) == []
