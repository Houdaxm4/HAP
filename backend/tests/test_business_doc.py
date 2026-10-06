from pathlib import Path

from docx import Document
from openpyxl import Workbook

from services.business_doc_service import BALANCE_AND_CAPITAL, GROWTH_AND_RETURNS, BusinessDocService, year_table
from services.workbook_values import needs_recalculation

BUSINESS_TEXT = (
    "Item 1. Business 1 Item 1A. Risk Factors 9 Item 1B. Unresolved Staff Comments 14 " + "x " * 40 + "Item 1. Business General Acme is a maker of industrial valves for utilities around the world. "
    "Acme was founded in 1920 by two engineers. Acme has plants in four countries on three continents. Acme sells through distributors and directly. "
    "We are organized into two reportable segments. Operations that sell valves to utilities form our Flow segment. "
    "Our customers include large utilities and original equipment manufacturers. Competition The valve industry is highly competitive and fragmented "
    "across many regions. Acme competes on quality, price and delivery time with many regional producers. " + "More about the company. " * 60 +
    "Item 1A. Risk Factors Our results could be adversely affected by raw material prices that we cannot control. " + "More risk text. " * 80 +
    "Item 1B. Unresolved Staff Comments"
)


def _workbook(path: Path) -> Path:
    wb = Workbook()
    ar = wb.active
    ar.title = "All Ratios"
    fm = wb.create_sheet("Final Metrics")
    years = ["FY 2023", "FY 2024", "FY 2025"]
    for ws in (ar, fm):
        for i, y in enumerate(years):
            ws.cell(1, 3 + i).value = y
    rows_ar = {"Revenue": [100.0, 110.0, 120.0], "Net Income": [10.0, 12.0, 14.0], "EPS diluted": [1.0, 1.2, 1.4], "Gross Margin": [0.3, 0.31, 0.32],
               "Operating Margin": [0.1, 0.11, 0.12], "Assets/Liabilities": [2.0, 2.1, 2.2], "Debt/Assets": [0.2, 0.2, 0.19],
               "Interest Coverage Ratio": [8.0, 9.0, 10.0]}
    rows_fm = {"ROCE": [0.1, 0.11, 0.12], "ROIC in - WACC": [-0.01, 0.0, 0.01], "FCF per Share": [1.0, 1.1, 1.2], "TBV per Share": [5.0, 6.0, 7.0],
               "Dividend per Share": [0.5, 0.5, 0.6], "Dividend Yield": [0.01, 0.01, 0.012], "Dividend Payout Ratio": [0.3, 0.3, 0.32]}
    for ws, rows in ((ar, rows_ar), (fm, rows_fm)):
        for r, (label, values) in enumerate(rows.items(), start=3):
            ws.cell(r, 1).value = label
            for i, v in enumerate(values):
                ws.cell(r, 3 + i).value = v
    wb.save(path)
    return path


def test_year_tables_read_the_workbook_rows_by_label(tmp_path: Path):
    labels, rows = year_table(_workbook(tmp_path / "w.xlsx"), GROWTH_AND_RETURNS)
    assert labels == ["FY2023", "FY2024", "FY2025"]
    table = dict(rows)
    assert table["Revenue ($M)"] == ["100.0", "110.0", "120.0"] and table["ROIC - WACC"] == ["-1.0%", "0.0%", "1.0%"]
    _l, balance = year_table(tmp_path / "w.xlsx", BALANCE_AND_CAPITAL)
    assert dict(balance)["Interest coverage"] == ["8.0x", "9.0x", "10.0x"] and dict(balance)["Dividend yield"][2] == "1.2%"


def test_document_has_two_pages_of_content_tables_and_no_ai_claims(tmp_path: Path):
    out = BusinessDocService().produce(
        ticker="ACME", company="Acme Corp", workbook_path=_workbook(tmp_path / "w.xlsx"), output_dir=tmp_path, base_name="2026 FY ACME Business",
        business_text=BUSINESS_TEXT, description="Acme Corp, headquartered in Dayton, Ohio, is a maker of industrial valves.",
    )
    doc = Document(out["path"])
    text = "\n".join(p.text for p in doc.paragraphs)
    assert Path(out["path"]).name == "2026 FY ACME Business.docx" and out["has_10k_text"]
    assert "ACME" in text and "OVERVIEW" in text and "SEGMENTS AND PRODUCTS" in text and "COMPETITION" in text and "FINANCIAL PROFILE" in text
    assert "We are organized into two reportable segments." in text and "raw material prices" in text
    assert len(doc.tables) == 3 and any("Revenue ($M)" in c.text for c in doc.tables[1].columns[0].cells)      # glance, growth and balance tables
    assert text.count("\f") == 0 and "w:br w:type=\"page\"" in doc.element.xml          # exactly one page break: page 2 starts at Financial profile


def test_missing_filing_text_still_gives_a_document_with_the_numbers(tmp_path: Path):
    out = BusinessDocService().produce(ticker="ACME", company="Acme", workbook_path=_workbook(tmp_path / "w.xlsx"), output_dir=tmp_path, base_name="b",
                                       business_text="")
    assert out["has_10k_text"] is False and Path(out["path"]).exists()
    assert BusinessDocService().produce_safe(ticker="X", company="X", workbook_path=tmp_path / "missing.xlsx", output_dir=tmp_path, base_name="c")["path"] is None


def test_recalculation_is_requested_only_when_formulas_have_no_values(tmp_path: Path):
    wb = Workbook()
    wb.active.title = "Final Metrics"
    wb.active["B5"] = "=AVERAGE(C5:L5)"
    wb.save(tmp_path / "formula_only.xlsx")
    assert needs_recalculation(tmp_path / "formula_only.xlsx") is True
    wb2 = Workbook()
    wb2.active.title = "Final Metrics"
    wb2.active["B5"] = 0.1
    wb2.save(tmp_path / "values.xlsx")
    assert needs_recalculation(tmp_path / "values.xlsx") is False
    assert needs_recalculation(_workbook(tmp_path / "other.xlsx")) is False        # no formula in the probe cell
