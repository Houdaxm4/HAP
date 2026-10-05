"""R&D useful life from the 10-K business description (new company only)."""

from __future__ import annotations

from pathlib import Path

from services.new_company_rd_service import NewCompanyRdService, business_life_evidence
from tests.test_new_company_pipeline import FY, YEARS, industrial_workbook


def _filing(business: str) -> str:
    toc = "Item 1. Business 3 Item 1A. Risk Factors 12 Item 2. Properties 20\n"
    body = "Item 1. Business\n" + business + "\nItem 1A. Risk Factors\nOther text."
    return toc + body


def test_pharma_business_text_gives_long_life():
    text = _filing("We run clinical trials for each drug candidate. FDA approval is required. " * 12 + " filler" * 600)
    life, evidence, ranking = business_life_evidence(text)
    assert life == 8
    assert "pharma biotech" in evidence[0]
    assert ranking[0]["group"] == "pharma_biotech"


def test_software_business_text_gives_short_life():
    text = _filing("Our software-as-a-service subscription platform runs in the cloud for developers. " * 12 + " filler" * 600)
    life, _evidence, ranking = business_life_evidence(text)
    assert life == 3
    assert ranking[0]["group"] == "software_internet"


def test_unclear_text_returns_none():
    assert business_life_evidence(_filing("We sell things. " * 400)) is None
    assert business_life_evidence(None) is None
    assert business_life_evidence("short") is None


def test_mixed_business_blends_the_life():
    text = _filing(
        "Our software-as-a-service subscription platform runs in the cloud. " * 8
        + "We run clinical trials for each drug candidate. " * 8
        + " filler" * 600
    )
    life, evidence, _ranking = business_life_evidence(text)
    assert 3 < life < 8
    assert "mixes two activities" in evidence[0]


def test_decision_uses_business_text_over_sic_and_cites_filing(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", rd_by_year={y: 50.0 for y in YEARS})
    svc = NewCompanyRdService()
    text = _filing("Our software-as-a-service subscription platform runs in the cloud for developers. " * 12 + " filler" * 600)
    decision = svc.select_useful_life(
        analysis_id="a",
        ticker="XYZ",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Example Machinery Corp", "sic": "3523"},
        business_text=text,
        business_source="https://www.sec.gov/Archives/edgar/data/1/example.htm",
    )
    assert decision.selected_useful_life == 3
    assert any("business description" in line.lower() or "10-K business section" in line for line in decision.company_evidence)
    assert any("Item 1 business description" in c for c in decision.filing_citations)
    assert decision.confidence >= 0.8


def test_without_business_text_behaviour_is_unchanged(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", rd_by_year={y: 50.0 for y in YEARS})
    decision = NewCompanyRdService().select_useful_life(
        analysis_id="a",
        ticker="XYZ",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Example Machinery Corp", "sic": "3523"},
    )
    assert decision.selected_useful_life == 5
