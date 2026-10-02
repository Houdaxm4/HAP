"""Buyback shares: companies that retire repurchased shares, and stray 52-week facts that must not veto the 10-K."""

from services.new_company_buyback_service import NewCompanyBuybackService as S


def fact(val, start, end, form="10-K", fp="FY", fy=2024):
    return {"val": val, "start": start, "end": end, "form": form, "fp": fp, "fy": fy, "accn": "a"}


def facts(**tags):
    return {"facts": {"us-gaap": {tag: {"units": {"shares" if "Shares" in tag else "USD": entries}} for tag, entries in tags.items()}}}


def test_shares_tagged_as_repurchased_and_retired_are_found():
    f = facts(StockRepurchasedAndRetiredDuringPeriodShares=[fact(117_000_000, "2023-07-30", "2024-07-27")])
    value, source = S._annual_share_fact(f, "FY2024")
    assert value == 117.0 and source == "sec_xbrl:StockRepurchasedAndRetiredDuringPeriodShares"


def test_the_10k_figure_leads_over_a_52_week_fact_from_a_10q():
    f = facts(StockRepurchasedAndRetiredDuringPeriodShares=[
        fact(43_000_000, "2023-07-30", "2024-07-27", form="10-Q", fp="Q1", fy=2025),   # stray 52-week fact
        fact(117_000_000, "2023-07-30", "2024-07-27", form="10-K", fp="FY"),
    ])
    assert S._annual_share_fact(f, "FY2024")[0] == 117.0


def test_a_stray_10q_value_does_not_veto_a_10k_figure_that_reconciles():
    f = facts(StockRepurchasedAndRetiredDuringPeriodValue=[
        fact(800_000_000, "2020-07-26", "2021-07-31", form="10-Q", fp="Q2", fy=2022),  # unrelated figure
        fact(2_902_000_000, "2020-07-26", "2021-07-31"),
    ])
    assert S._period_value_reconciles(f, "FY2021", 2877.0)       # 10-K value within tolerance of the cash-flow dollars
    assert not S._period_value_reconciles(f, "FY2021", 9000.0)   # but a real disagreement is still rejected
