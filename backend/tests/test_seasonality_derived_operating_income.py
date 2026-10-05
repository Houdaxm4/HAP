"""Seasonality: companies with no operating income line (no OperatingIncomeLoss tag) get it derived from SEC revenue and costs."""

from __future__ import annotations

from services.new_company_seasonality_service import NewCompanySeasonalityService


def _entry(val: float, start: str, end: str) -> dict:
    return {"start": start, "end": end, "val": val, "form": "10-Q", "fp": "Q3", "filed": end}


def _facts(with_operating_income: bool = False, with_rd: bool = True) -> dict:
    nine = ("2024-10-01", "2025-06-30")
    gaap = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [_entry(2_571_800_000, *nine)]}},
        "CostOfGoodsAndServicesSold": {"units": {"USD": [_entry(1_900_000_000, *nine)]}},
        "SellingGeneralAndAdministrativeExpense": {"units": {"USD": [_entry(250_000_000, *nine)]}},
    }
    if with_rd:
        gaap["ResearchAndDevelopmentExpense"] = {"units": {"USD": [_entry(100_000_000, *nine)]}}
    if with_operating_income:
        gaap["OperatingIncomeLoss"] = {"units": {"USD": [_entry(321_800_000, *nine)]}}
    return {"facts": {"us-gaap": gaap}}


def test_operating_income_is_revenue_less_cost_sga_and_rd():
    svc = NewCompanySeasonalityService()
    value = svc._derived_operating_income(_facts(), "FY2025", "9m")
    assert round(value, 3) == round(2571.8 - 1900.0 - 250.0 - 100.0, 3)


def test_not_derived_when_the_company_reports_operating_income():
    svc = NewCompanySeasonalityService()
    assert svc._has_tag(_facts(with_operating_income=True), "OperatingIncomeLoss")
    assert not svc._has_tag(_facts(), "OperatingIncomeLoss")


def test_missing_pieces_give_no_guess():
    svc = NewCompanySeasonalityService()
    facts = _facts()
    del facts["facts"]["us-gaap"]["CostOfGoodsAndServicesSold"]
    assert svc._derived_operating_income(facts, "FY2025", "9m") is None            # no cost of goods sold
    assert svc._derived_operating_income(_facts(), "FY2021", "9m") is None         # no data for that year
    assert svc._derived_operating_income(None, "FY2025", "9m") is None
    # R&D tag exists for the company but not for this period: do not treat it as zero
    partial = _facts()
    partial["facts"]["us-gaap"]["ResearchAndDevelopmentExpense"]["units"]["USD"] = [_entry(90_000_000, "2023-10-01", "2024-06-30")]
    assert svc._derived_operating_income(partial, "FY2025", "9m") is None
    # a company with no R&D tag at all: R&D is zero
    no_rd = _facts(with_rd=False)
    assert round(svc._derived_operating_income(no_rd, "FY2025", "9m"), 3) == round(2571.8 - 1900.0 - 250.0, 3)
