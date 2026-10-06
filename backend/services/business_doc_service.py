"""The 2-page business document for a new company (Word).

What the company does (from the Business and Risk Factors sections of its latest 10-K, see business_content), a five-year financial table and a
valuation snapshot (from the completed workbook). Professional layout: narrow margins, small type, tables for every figure.
Written without an AI model; the text is the company's own wording, shortened. It replaces the old Word analysis report.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from openpyxl import load_workbook

from services.business_content import BusinessContent, extract
from services.email_draft_service import (
    Facts, _find_label_row, _num, _value, _year_columns, change, money_b, money_m, pct, read_facts, usd,
)
from services.email_narrative import new_company_highlights

NAVY = "1F2A44"
BLUE = RGBColor(0x1F, 0x4E, 0x9C)
GREY = RGBColor(0x55, 0x60, 0x7D)
LIGHT = "EEF3FF"


def _shade(cell, fill: str) -> None:
    pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def _borders(table, color: str = "C9D1E3") -> None:
    tbl = table._tbl
    props = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), color)
        borders.append(el)
    props.append(borders)


def _cell_text(cell, text: str, *, bold: bool = False, color: RGBColor | None = None, align=None, size: float = 8.5) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    if align is not None:
        p.alignment = align
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color


def _heading(doc, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = BLUE
    pr = p._p.get_or_add_pPr()
    bottom = OxmlElement("w:pBdr")
    line = OxmlElement("w:bottom")
    line.set(qn("w:val"), "single")
    line.set(qn("w:sz"), "6")
    line.set(qn("w:color"), "1F4E9C")
    bottom.append(line)
    pr.append(bottom)


def _para(doc, text: str, *, size: float = 9, italic: bool = False, after: float = 2) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(0)
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.italic = italic


def _bullets(doc, items: list[str], *, size: float = 9) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(item)
        run.font.size = Pt(size)


def _plain(v):
    return "n/a" if v is None else f"{v:,.1f}"


def _eps(v):
    return "n/a" if v is None else f"{v:,.2f}"


def _times(v):
    return "n/a" if v is None else f"{v:,.1f}x"


def _ratio(v):
    return "n/a" if v is None else f"{v:,.2f}"


GROWTH_AND_RETURNS = [
    ("Revenue ($M)", "All Ratios", "Revenue", _plain),
    ("Net income ($M)", "All Ratios", "Net Income", _plain),
    ("Diluted EPS ($)", "All Ratios", "EPS diluted", _eps),
    ("Gross margin", "All Ratios", "Gross Margin", lambda v: pct(v, 1)),
    ("Operating margin", "All Ratios", "Operating Margin", lambda v: pct(v, 1)),
    ("ROCE", "Final Metrics", "ROCE", lambda v: pct(v, 1)),
    ("ROIC - WACC", "Final Metrics", "ROIC in - WACC", lambda v: pct(v, 1)),
]
BALANCE_AND_CAPITAL = [
    ("Assets / liabilities", "All Ratios", "Assets/Liabilities", _ratio),
    ("Debt / assets", "All Ratios", "Debt/Assets", lambda v: pct(v, 1)),
    ("Interest coverage", "All Ratios", "Interest Coverage Ratio", _times),
    ("Free cash flow / share ($)", "Final Metrics", "FCF per Share", _eps),
    ("TBV / share ($)", "Final Metrics", "TBV per Share", _eps),
    ("Dividend / share ($)", "Final Metrics", "Dividend per Share", _eps),
    ("Dividend yield", "Final Metrics", "Dividend Yield", lambda v: pct(v, 1)),
    ("Payout ratio", "Final Metrics", "Dividend Payout Ratio", lambda v: pct(v, 1)),
]


def year_table(workbook_path: Path, specs, years: int = 10) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(fiscal years, rows of (label, formatted values)) for the last `years` fiscal years; each spec is (label, sheet, row label, formatter)."""
    wb = load_workbook(workbook_path, data_only=True)
    try:
        cols = {name: _year_columns(wb[name]) for name in {sh for _l, sh, _r, _f in specs} if name in wb.sheetnames}
        shared = None
        for c in cols.values():
            shared = set(c) if shared is None else shared & set(c)
        labels = sorted(shared or set())[-years:]
        rows: list[tuple[str, list[str]]] = []
        for label, sheet, row_label, fmt in specs:
            if sheet not in cols:
                continue
            ws = wb[sheet]
            r = _find_label_row(ws, row_label)
            rows.append((label, [fmt(_value(ws, r, cols[sheet][y])) if r else "n/a" for y in labels]))
        return labels, rows
    finally:
        wb.close()


def _facts_table(doc, f: Facts, sheet_fields: Any) -> None:
    cells = [
        ("Price", usd(f.price)),
        ("Market cap", getattr(sheet_fields, "market_cap_text", None) or money_b(f.market_cap_m)),
        ("PE10 percentile", pct(f.pe10_percentile, 1)),
        ("Max entry price", usd(f.max_entry)),
        ("EV margin of safety", pct(f.ev_mos, 1, sign=True)),
        ("Expected return", pct(f.expected_return, 1) + (" (adj.)" if f.expected_return_adjusted else "")),
        ("Graham entry price", usd(f.graham_entry)),
        ("Classified as", getattr(sheet_fields, "classified_as", None) or "n/a"),
    ]
    table = doc.add_table(rows=2, cols=len(cells))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _borders(table)
    for i, (label, value) in enumerate(cells):
        _cell_text(table.cell(0, i), label, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), align=WD_ALIGN_PARAGRAPH.CENTER, size=7.5)
        _shade(table.cell(0, i), NAVY)
        _cell_text(table.cell(1, i), value, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=9)
        _shade(table.cell(1, i), LIGHT)


def _financial_table(doc, labels: list[str], rows: list[tuple[str, list[str]]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=1 + len(labels))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    first, rest = 1.55, max(0.4, (7.1 - 1.55) / max(1, len(labels)))
    for i, column in enumerate(table.columns):
        for cell in column.cells:
            cell.width = Inches(first if i == 0 else rest)
    _borders(table)
    _cell_text(table.cell(0, 0), "", size=8)
    _shade(table.cell(0, 0), NAVY)
    for j, y in enumerate(labels, start=1):
        _cell_text(table.cell(0, j), y.replace("FY", "FY "), bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), align=WD_ALIGN_PARAGRAPH.RIGHT, size=7.5)
        _shade(table.cell(0, j), NAVY)
    for i, (label, values) in enumerate(rows, start=1):
        _cell_text(table.cell(i, 0), label, bold=True, size=8)
        if i % 2 == 0:
            _shade(table.cell(i, 0), LIGHT)
        for j, v in enumerate(values, start=1):
            _cell_text(table.cell(i, j), v, align=WD_ALIGN_PARAGRAPH.RIGHT, size=8)
            if i % 2 == 0:
                _shade(table.cell(i, j), LIGHT)


class BusinessDocService:
    def produce(
        self,
        *,
        ticker: str,
        company: str,
        workbook_path: Path,
        output_dir: Path,
        base_name: str,
        business_text: str | None = None,
        search_dir: Path | None = None,
        sheet_fields: Any = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        facts = read_facts(workbook_path, ticker=ticker, company=company)
        if business_text is None:
            from services.company_description_service import _fetch_latest_business_text, _latest_cached_business_text

            business_text = _latest_cached_business_text(search_dir or output_dir) or _fetch_latest_business_text(ticker)
        content = extract(business_text or "")
        tables = [year_table(workbook_path, GROWTH_AND_RETURNS), year_table(workbook_path, BALANCE_AND_CAPITAL)]
        doc = self._build(facts, content, tables, company or ticker, ticker, sheet_fields, description)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{base_name}.docx"
        doc.save(path)
        return {"path": str(path), "has_10k_text": bool(business_text), "sections": [k for k, v in vars(content).items() if v]}

    def produce_safe(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.produce(**kwargs)
        except Exception as exc:  # noqa: BLE001 - the document is advisory; it never stops an analysis
            return {"path": None, "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _build(f: Facts, content: BusinessContent, tables, name: str, ticker: str, sheet_fields, description) -> Document:
        doc = Document()
        section = doc.sections[0]
        section.left_margin = section.right_margin = Inches(0.7)
        section.top_margin = Inches(0.55)
        section.bottom_margin = Inches(0.5)
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(9)

        title = doc.add_paragraph()
        title.paragraph_format.space_after = Pt(0)
        run = title.add_run(f"{name}")
        run.bold = True
        run.font.size = Pt(18)
        run.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44)
        run = title.add_run(f"   {ticker}")
        run.font.size = Pt(12)
        run.font.color.rgb = GREY
        sub = doc.add_paragraph()
        sub.paragraph_format.space_after = Pt(4)
        run = sub.add_run(f"Business overview  |  based on the company's latest 10-K  |  {date.today():%B %d, %Y}")
        run.font.size = Pt(8)
        run.font.color.rgb = GREY

        _facts_table(doc, f, sheet_fields)

        _heading(doc, "Overview")
        if description:
            _para(doc, description if description.endswith(".") else description + ".")
        for sentence in content.overview:
            if description and sentence.lower()[:40] in description.lower():
                continue
            _para(doc, sentence)
        if content.segments:
            _heading(doc, "Segments and products")
            _bullets(doc, content.segments)
        if content.customers:
            _heading(doc, "Customers and markets")
            _bullets(doc, content.customers)
        if content.competition:
            _heading(doc, "Competition")
            _para(doc, " ".join(content.competition))
        if content.developments:
            _heading(doc, "Recent developments")
            _bullets(doc, content.developments)

        doc.add_page_break()
        _heading(doc, "Financial profile")
        text = new_company_highlights(f)
        if text:
            _para(doc, text, after=3)
        titles = ("Growth, margins and returns", "Balance sheet and capital returns")
        for title, (labels, rows) in zip(titles, tables):
            if not rows:
                continue
            sub = doc.add_paragraph()
            sub.paragraph_format.space_before = Pt(4)
            sub.paragraph_format.space_after = Pt(1)
            run = sub.add_run(title)
            run.bold = True
            run.font.size = Pt(8.5)
            _financial_table(doc, labels, rows)
        if content.risks:
            _heading(doc, "Key risks (from the 10-K)")
            _bullets(doc, content.risks, size=8.5)
        note = doc.add_paragraph()
        note.paragraph_format.space_before = Pt(5)
        run = note.add_run(
            "Business text is taken from the company's 10-K; figures are from the HAP workbook (fiscal years). ROCE and ROIC - WACC follow the house methodology."
        )
        run.italic = True
        run.font.size = Pt(7.5)
        run.font.color.rgb = GREY
        return doc
