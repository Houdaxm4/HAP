"""Buyback shares from footnote sentences (companies that do not publish the Item 5 repurchase table)."""

from __future__ import annotations

from services.new_company_buyback_service import choose_sentence_shares, parse_repurchase_sentences


def test_sentence_in_thousands_is_scaled_to_millions():
    out = parse_repurchase_sentences("During fiscal year 2025, we repurchased 864 shares of our common stock for $ 170,083 under the 2024 Authorization.")
    assert out == {2025: [(0.864, 170.083)]}


def test_other_phrasings_are_read():
    text = (
        "During the fiscal year ended September 30, 2016, we purchased 2,635 shares of our common stock for $125,000 under the plan. "
        "We utilized $ 71,197 to repurchase 1,027 shares of our common stock in fiscal year 201 7 under the 2016 Authorization."
    )
    out = parse_repurchase_sentences(text)
    assert out[2016] == [(2.635, 125.0)] and out[2017] == [(1.027, 71.197)]


def test_written_out_units_and_implausible_prices():
    out = parse_repurchase_sentences("In fiscal 2024, we repurchased 1.5 million shares of our common stock for $300 million.")
    assert out == {2024: [(1.5, 300.0)]}
    # 50,000 thousand shares for $12 million is $0.24 a share: not a real repurchase, so it is skipped
    assert parse_repurchase_sentences("In fiscal 2024, we repurchased 50,000 shares of our common stock for $ 12,000.") == {}


def test_two_programs_in_one_year_are_summed_only_when_they_reconcile():
    pairs = [(0.233, 26.742), (3.89, 446.042)]
    assert round(choose_sentence_shares(pairs, 485.3), 3) == 4.123      # both programs add up to the cash-flow dollars
    assert choose_sentence_shares(pairs, 26.7) == 0.233                 # a single sentence matches on its own
    assert choose_sentence_shares(pairs, 900.0) is None                 # nothing reconciles: never guess


def test_cash_figure_versus_total_figure_picks_the_one_matching_cash_flow():
    pairs = [(0.294, 33.344), (0.404, 45.86)]
    assert choose_sentence_shares(pairs, 33.344) == 0.294
    assert choose_sentence_shares(pairs, 45.9) == 0.404
    assert choose_sentence_shares([], 10.0) is None and choose_sentence_shares(pairs, None) is None
