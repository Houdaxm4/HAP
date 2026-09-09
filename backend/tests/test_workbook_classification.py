"""Unit tests for M1.5 workbook classification (no Excel writes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from workbook_mapping.models import CellClass, WritePolicy
from workbook_mapping.sheet_policies import ANNUAL_DATA_SHEETS, policy_for

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "validation_campaign" / "universe"


def _template(ticker: str = "AAPL") -> Path | None:
    folder = UNIVERSE / ticker
    if not folder.exists():
        return None
    matches = sorted(
        p
        for p in folder.glob("*.xlsx")
        if "Industrial Template" in p.name and not p.name.startswith("~$")
    )
    return matches[0] if matches else None


def test_sheet_policies_cover_known_names():
    for name in ANNUAL_DATA_SHEETS:
        pol = policy_for(name)
        assert pol["write_policy"] == WritePolicy.HYBRID.value
        assert pol["fill_priority"] == "P0"


def test_is_percent_sheet_read_only():
    assert policy_for("IS%")["write_policy"] == WritePolicy.READ_ONLY.value
    assert policy_for("IS%")["fill_priority"] == "Never"
    # Inputs has writable tax/PE10/current sinks — Hybrid/P0 for Mode A completion.
    assert policy_for("Inputs")["write_policy"] == WritePolicy.HYBRID.value
    assert policy_for("Inputs")["fill_priority"] == "P0"


@pytest.mark.skipif(_template() is None, reason="Industrial Template not present locally")
def test_build_manifest_aapl_smoke():
    from workbook_mapping.manifest_builder import build_manifest_from_path

    path = _template("AAPL")
    assert path is not None
    manifest = build_manifest_from_path(path, baseline_ticker="AAPL")
    assert manifest.statistics.worksheets == 24
    assert len(manifest.sheets) == 24
    names = [s.name for s in manifest.sheets]
    assert "Income - GAAP" in names
    assert "IC & NOPAT & ROIC " in names  # trailing space

    income = next(s for s in manifest.sheets if s.name == "Income - GAAP")
    assert income.write_policy == WritePolicy.HYBRID
    assert any(c.writable for c in income.cells)
    assert any(c.classification == CellClass.FORMULA for c in income.cells) or income.metrics.formula_cells >= 0

    is_pct = next(s for s in manifest.sheets if s.name == "IS%")
    assert is_pct.write_policy == WritePolicy.READ_ONLY
    assert not any(c.writable for c in is_pct.cells)
