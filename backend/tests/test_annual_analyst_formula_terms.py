from pathlib import Path

from openpyxl import Workbook, load_workbook

from services.annual_continuity_service import AnnualContinuityService, analyst_extra_terms

BS = "'Balance Sheet - Standardized'"


def _book(path: Path, years: list[int], *, op_assets, op_liabilities) -> Path:
    wb = Workbook()
    bs = wb.active
    bs.title = "Balance Sheet - Standardized"
    for i, y in enumerate(years):
        bs.cell(5, 3 + i, f"{y} A")
        bs.cell(7, 3 + i, f"FY{y}")
    inputs = wb.create_sheet("Inputs")
    for i in range(len(years)):
        col = chr(67 + i)
        inputs.cell(1, 3 + i, f"={BS}!{col}7")
        inputs.cell(81, 3 + i, op_assets(col))
        inputs.cell(84, 3 + i, op_liabilities(col))
    inputs["A81"], inputs["A84"] = "Current operating assets", "Current operating liabilities"
    wb.save(path)
    return path


def _assets_template(col: str) -> str:
    return f'=IF({BS}!{col}11="",0,{BS}!{col}11)+IF({BS}!{col}14="",0,{BS}!{col}14)'


def test_extra_terms_are_the_formula_beyond_the_template_one_and_keep_sheet_names():
    base = f'=IF({BS}!K11="",0,{BS}!K11)'
    assert analyst_extra_terms(base + f"+{BS}!K33", base) == f"+{BS}!K33"
    assert analyst_extra_terms(base.replace("=IF(", "= IF(") + f" - {BS}!K33", base) == f"- {BS}!K33"
    assert analyst_extra_terms(base, base) is None                                    # nothing added
    assert analyst_extra_terms(f"={BS}!K11*2", base) is None                          # a different structure is a template update
    assert analyst_extra_terms("=SUM(K1:K5)*2", "=SUM(K1:K5)") is None                # an operator that is not + or -


def test_the_analysts_added_balance_sheet_lines_are_carried_forward_and_extended_to_the_new_year(tmp_path: Path):
    previous = _book(
        tmp_path / "prev.xlsx", list(range(2016, 2026)),
        op_assets=lambda c: _assets_template(c) + f"+{BS}!{c}33",                       # the analyst added line 33
        op_liabilities=lambda c: f"=IF({BS}!{c}65=\"\",0,{BS}!{c}65)+{BS}!{c}82",         # and line 82
    )
    template = _book(
        tmp_path / "tmpl.xlsx", list(range(2017, 2027)),
        op_assets=_assets_template,
        op_liabilities=lambda c: f"={BS}!{c}65+{BS}!{c}68",                              # a different structure: a deliberate template update
    )
    out = tmp_path / "out.xlsx"
    out.write_bytes(template.read_bytes())
    report = AnnualContinuityService().apply(analysis_id="a", ticker="ZZ", template_path=template, previous_workbook_path=previous, workbook_path=out)
    ws = load_workbook(out)["Inputs"]
    # FY2025 is column K in the new window (2017 starts in C): the added line is carried and its column follows the year
    assert ws["K81"].value.endswith(f"+{BS}!K33") and ws["C81"].value.endswith(f"+{BS}!C33")
    assert ws["L81"].value == _assets_template("L") + f"+{BS}!L33"                      # the new fiscal year (FY2026) gets the analyst's line too
    assert ws["K84"].value == f"={BS}!K65+{BS}!K68"                                       # structure differs: the template formula stays
    assert any("Analyst's added terms" in e.reason for e in report.entries)


def test_without_analyst_additions_nothing_changes(tmp_path: Path):
    previous = _book(tmp_path / "prev.xlsx", list(range(2016, 2026)), op_assets=_assets_template, op_liabilities=lambda c: f"={BS}!{c}65")
    template = _book(tmp_path / "tmpl.xlsx", list(range(2017, 2027)), op_assets=_assets_template, op_liabilities=lambda c: f"={BS}!{c}65")
    out = tmp_path / "out.xlsx"
    out.write_bytes(template.read_bytes())
    AnnualContinuityService().apply(analysis_id="a", ticker="ZZ", template_path=template, previous_workbook_path=previous, workbook_path=out)
    ws = load_workbook(out)["Inputs"]
    assert ws["K81"].value == _assets_template("K") and ws["L81"].value == _assets_template("L") and ws["L84"].value == f"={BS}!L65"


def _leases_book(path: Path, first_year: int, row18) -> Path:
    """A Leases tab as the template lays it out: column c shows the fiscal year held in column c + 1 of the Income tab, and reads Inputs one column to the right."""
    wb = Workbook()
    income = wb.active
    income.title = "Income - GAAP"
    for i in range(10):
        income.cell(7, 3 + i, f"FY{first_year - 1 + i}")
    leases = wb.create_sheet("Leases")
    for c in range(3, 12):
        leases.cell(1, c, f"='Income - GAAP'!{chr(64 + c + 1)}7")
        leases.cell(18, c, row18(c))
    leases["A18"] = "Estimated Long-Term Rate"
    wb.save(path)
    return path


def test_an_analyst_rate_typed_into_a_lease_year_is_not_overwritten_by_the_previous_columns_formula(tmp_path: Path):
    def rate_formula(c: int) -> str:
        return f"=Inputs!{chr(64 + c + 1)}35/Inputs!{chr(64 + c + 1)}27"

    # previous window FY2016..FY2025: the analyst typed 10% from the fifth lease year (FY2021 in column 7) onwards
    previous = _leases_book(tmp_path / "prev.xlsx", 2017, lambda c: rate_formula(c) if c < 6 else 0.1)
    template = _leases_book(tmp_path / "tmpl.xlsx", 2018, rate_formula)
    out = tmp_path / "out.xlsx"
    out.write_bytes(template.read_bytes())
    AnnualContinuityService().apply(analysis_id="a", ticker="ZZ", template_path=template, previous_workbook_path=previous, workbook_path=out)
    ws = load_workbook(out)["Leases"]
    # the previous workbook's FY2020 sits in column 6 (value 10%); in the new window FY2020 is column 5 and must hold the analyst's 10%
    assert ws["E18"].value == 0.1 and ws["F18"].value == 0.1
    assert ws["D18"].value == rate_formula(4)                                         # FY2019 was a formula in the previous workbook: template formula stays
