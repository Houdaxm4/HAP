from services.cost_recast import parse_expense_rows, recast_cost

OLD = ("CONSOLIDATED STATEMENTS OF INCOME (in thousands) OPERATING EXPENSES: Patent administration and licensing 175,741 170,178 154,940 "
       "Development 84,646 74,860 69,698 Selling, general and administrative 48,999 51,289 51,030 Total Operating expenses 303,823 281,089 244,809")
NEW22 = ("CONSOLIDATED STATEMENTS OF INCOME (in thousands) OPERATING EXPENSES: Research and portfolio development 185,202 200,484 204,360 "
         "Licensing 71,419 64,625 50,464 General and administrative 47,377 61,217 48,999 Restructuring activities 3,280 27,877 - "
         "Total Operating expenses 307,278 354,203 303,823")
NEW23 = ("CONSOLIDATED STATEMENTS OF INCOME (in thousands) OPERATING EXPENSES: Research and portfolio development 195,285 185,202 200,484 "
         "Licensing 79,397 71,419 64,625 General and administrative 53,291 47,377 61,217 Restructuring activities - 3,280 27,877 "
         "Total Operating expenses 327,973 307,278 354,203")


def test_parse_rows_handles_dashes_and_labels():
    rows = parse_expense_rows(NEW22)
    assert rows["licensing"] == [71419.0, 64625.0, 50464.0]
    assert rows["restructuring activities"] == [3280.0, 27877.0, 0.0]


def test_recast_uses_latest_definition_and_marks_unrecastable_years():
    workbook = {2020: 170.178, 2021: 175.741, 2022: 71.419, 2023: None}
    filings = {2021: OLD.replace("175,741 170,178 154,940", "175,741 170,178 154,940"), 2022: NEW22, 2023: NEW23}
    result = recast_cost(workbook, filings)
    assert result["label"] == "licensing"
    years = result["years"]
    assert years[2020] == {"value": 50.464, "status": "recast", "source_filing_year": 2022}
    assert years[2021]["value"] == 64.625 and years[2021]["status"] == "recast"
    assert years[2022]["status"] == "matches"
    assert years[2023]["value"] == 79.397 and years[2023]["status"] == "recast"


def test_no_match_means_no_recast():
    assert recast_cost({2022: 999.0}, {2022: NEW22}) == {"label": None, "years": {}}
    assert recast_cost({}, {}) == {"label": None, "years": {}}
