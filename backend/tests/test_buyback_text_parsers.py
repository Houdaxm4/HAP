from services.buyback_text_parsers import (
    parse_annual_shares_narrative,
    parse_equity_statement_repurchases,
    parse_multi_year_repurchases,
)
from services.new_company_buyback_service import choose_sentence_shares

ATR_NOTE = (
    "In 2025, 2024 and 2023, we repurchased approximately 2.7 million, 433 thousand and 399 thousand shares, respectively, of our "
    "outstanding common stock at a total cost of $ 365.0 million, $ 68.6 million and $ 47.6 million, respectively. As of December 31, 2025, "
    "there was $ 97.7 million of authorized share repurchases available. During the fourth quarter of 2025, we repurchased approximately "
    "1.5 million shares for approximately $175.0 million."
)


def test_multi_year_sentence_gives_every_year_with_its_own_dollars():
    out = parse_multi_year_repurchases(ATR_NOTE)
    assert out[2025] == [(2.7, 365.0)] and out[2024] == [(0.433, 68.6)] and out[2023] == [(0.399, 47.6)]
    assert set(out) == {2023, 2024, 2025}                 # the fourth-quarter sentence is not an annual figure


def test_two_year_sentence_without_dollars_still_gives_shares():
    text = "During 2022 and 2021, we repurchased 860 thousand and 615 thousand shares, respectively, all of which were returned to treasury stock."
    assert parse_multi_year_repurchases(text) == {2022: [(0.86, None)], 2021: [(0.615, None)]}


def test_annual_summary_sentences_use_the_filings_own_year():
    assert parse_annual_shares_narrative("Timken also repurchased 779,300 common shares during the year.", 2025) == {2025: [(0.7793, None)]}
    assert parse_annual_shares_narrative("Timken also repurchased half a million common shares during the year.", 2024) == {2024: [(0.5, None)]}
    assert parse_annual_shares_narrative("The Company repurchased 3.25 million common shares, or over 4 percent of its outstanding common shares, and", 2022) == {2022: [(3.25, None)]}
    assert parse_annual_shares_narrative("The Company also repurchased 1.1 million shares of common stock in 2020.", 2020) == {2020: [(1.1, None)]}
    assert parse_annual_shares_narrative(
        "The increase in treasury shares was primarily due to the Company's purchase of 3.1 million of its common shares for $101.0 million , "
        "partially offset by shares issued for stock compensation plans during 2016 .", 2016) == {2016: [(3.1, 101.0)]}


def test_authorizations_and_programs_are_not_annual_repurchases():
    text = ("The Company may repurchase up to 10 million common shares during the year. "
            "Since inception the Company repurchased 5 million common shares during the year.")
    assert parse_annual_shares_narrative(text, 2025) == {}
    assert parse_annual_shares_narrative("The Company repurchased 2 million shares in 2019.", 2025) == {}      # another year


EQUITY = (
    "(in thousands, except as specified) Stock Capital Earnings (Loss) Shares Amount Equity "
    "Balance, June 30, 2016 $ 41,976 $ 52,374 $ 678,002 $ (117,975 ) 15,310 $ (284,418 ) $ 369,959 "
    "Stock issued for employee stock option plans (614 ) (78 ) 1,462 848 Treasury stock acquired 90 (7,806 ) (7,806 ) "
    "Net Income 46,545 46,545 Balance, June 30, 2017 $ 41,976 $ 56,783 15,322 $ (290,762 ) $ 408,664 "
    "Treasury stock acquired 27 (2,652 ) (2,652 ) Net Income 36,604 Balance, June 30, 2018 $ 41,976 15,279"
)


def test_equity_statement_row_gives_shares_and_dollars_for_each_year():
    out = parse_equity_statement_repurchases(EQUITY)
    assert out == {2017: [(0.09, 7.806)], 2018: [(0.027, 2.652)]}


def test_every_candidate_is_checked_against_the_cash_flow_dollars():
    candidates = parse_multi_year_repurchases(ATR_NOTE)[2025]
    assert choose_sentence_shares(candidates, 363.0) == 2.7           # within 6% of the cash flow
    assert choose_sentence_shares(candidates, 150.0) is None          # does not reconcile: never used
