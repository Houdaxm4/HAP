"""Unit tests for workbook parsing and safe writes."""

from __future__ import annotations

from openpyxl import load_workbook

from models.provenance import CellProvenance
from services.workbook_service import WorkbookService


def test_parse_workbook_structure(sample_workbook):
    service = WorkbookService()
    structure = service.parse_structure(sample_workbook, "prefilled_workbook.xlsx")

    assert "Income Statement" in structure.worksheet_names
    assert structure.formula_count == 1
    assert service.cell_contains_formula(structure, "Income Statement", "B10") is True
    assert service.cell_contains_formula(structure, "Income Statement", "B5") is False


def test_write_values_preserves_formulas(sample_workbook, tmp_path):
    service = WorkbookService()
    destination = tmp_path / "completed_workbook.xlsx"
    provenance = [
        CellProvenance(
            cell_ref="Income Statement!B5",
            worksheet="Income Statement",
            cell="B5",
            concept="Revenue",
            period="FY2024",
            value=1000,
            status="filled",
        ),
        CellProvenance(
            cell_ref="Income Statement!B10",
            worksheet="Income Statement",
            cell="B10",
            concept="Total",
            period="FY2024",
            value=999,
            status="filled",
        ),
    ]

    filled, blank, skipped = service.write_values(sample_workbook, destination, provenance)
    assert filled == 1
    assert skipped == 1
    assert service.get_cell_value(destination, "Income Statement", "B5") == 1000

    workbook = load_workbook(destination, data_only=False)
    try:
        assert workbook["Income Statement"]["B10"].data_type == "f"
    finally:
        workbook.close()
