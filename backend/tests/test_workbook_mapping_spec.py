"""Tests for M2 explicit mapping specification."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "workbook_mapping" / "Workbook_Manifest.json"


@pytest.mark.skipif(not MANIFEST.exists(), reason="Workbook_Manifest.json missing")
def test_mapping_spec_builds_and_explains_all_writable_cells():
    from workbook_mapping.mapping_builder import build_mapping_specification

    spec = build_mapping_specification(MANIFEST)
    assert spec.coverage.unexplained_writable_cells == 0
    assert spec.coverage.mapped_cfm_metrics >= 20
    assert len(spec.mappings) >= 20
    # No mapping targets non-writable classifications — validated during build
    sheets = {m.sheet for m in spec.mappings}
    assert "Income - GAAP" in sheets
    assert "IS%" not in sheets


@pytest.mark.skipif(not MANIFEST.exists(), reason="Workbook_Manifest.json missing")
def test_diluted_eps_not_scaled():
    from workbook_mapping.explicit_mappings import explicit_mappings

    eps = next(m for m in explicit_mappings() if m.cfm_path == "income_statement.diluted_eps")
    assert eps.transformation is None
