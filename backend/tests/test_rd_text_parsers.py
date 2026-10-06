from services.rd_text_parsers import parse_rd_costs

NOTE = (
    "Total research and development costs, which are classified under selling, general, and administrative expenses, were $5.5 million, "
    "$4.9 million, and $4.1 million for the years ended June 30, 2017, 2016, and 2015, respectively. Warranties The expected cost is recorded."
)


def test_years_named_in_the_sentence_are_matched_in_order():
    assert parse_rd_costs(NOTE, 2017) == {2017: 5.5, 2016: 4.9, 2015: 4.1}


def test_without_years_the_amounts_run_back_from_the_filing_year():
    text = "Research and development expenses were $12.0 million and $10.5 million, respectively."
    assert parse_rd_costs(text, 2020) == {2020: 12.0, 2019: 10.5}


def test_thousands_are_converted_and_bare_dollars_are_ignored():
    assert parse_rd_costs("Research and development costs were $850 thousand in 2018.", 2018) == {2018: 0.85}
    assert parse_rd_costs("Research and development costs were 5,500 in 2018.", 2018) == {}


def test_acquired_in_process_and_percentage_sentences_are_not_expense():
    assert parse_rd_costs("Acquired in-process research and development costs were $20.0 million in 2018.", 2018) == {}
    assert parse_rd_costs("Research and development expenses were approximately 5% of sales, or $9.0 million in 2018.", 2018) == {}


def test_a_year_count_that_does_not_match_the_amounts_is_not_guessed():
    assert parse_rd_costs("Research and development costs were $5.0 million and $4.0 million in fiscal 2018, 2017 and 2016.", 2018) == {}
