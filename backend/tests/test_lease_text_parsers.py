from services.lease_text_parsers import parse_operating_lease_commitments

NOTE_2018 = (
    "11. COMMITMENTS The Company leases certain property and equipment under agreements with initial terms ranging from one to sixty years. "
    "Rental expense related to continuing operations for the years ended June 30, 2018, 2017, and 2016 was approximately $10.2 million, "
    "$8.0 million and $6.6 million, respectively. 57 The gross minimum annual rental commitments under non-cancelable operating leases, "
    "principally real-estate at June 30, 2018: (in thousands) Lease Sublease Net obligation 2019 10,202 329 9,873 2020 8,704 336 8,368 "
    "2021 7,923 346 7,577 2022 7,095 356 6,739 2023 7,204 367 6,837 Thereafter 15,995 2,670 13,325 12. CONTINGENCIES From time to time"
)


def test_gross_commitments_become_the_five_years_and_thereafter():
    out = parse_operating_lease_commitments(NOTE_2018)
    assert (out["year_1"], out["year_2"], out["year_3"], out["year_4"], out["year_5"], out["thereafter"]) == (10.202, 8.704, 7.923, 7.095, 7.204, 15.995)
    assert out["total_undiscounted"] == 57.123
    assert out["lease_cost"] == 10.2                 # rental expense of the filing's own year


def test_dollar_signs_in_the_first_row_are_fine():
    text = ("The gross minimum annual rental commitments under non-cancelable operating leases at June 30, 2017: (in thousands) Lease Sublease "
            "2018 $ 8,393 $ 303 2019 8,303 328 2020 5,744 333 2021 5,022 338 2022 5,566 344 Thereafter 12,637 2,762")
    out = parse_operating_lease_commitments(text)
    assert out["year_1"] == 8.393 and out["year_5"] == 5.566 and out["thereafter"] == 12.637


def test_no_table_or_unknown_units_gives_nothing():
    assert parse_operating_lease_commitments("The Company leases offices under operating leases.") == {}
    no_units = NOTE_2018.replace("(in thousands)", "")
    assert parse_operating_lease_commitments(no_units) == {}
    broken = NOTE_2018.replace("2021 7,923 346 7,577", "")      # a missing year: the schedule is not guessed
    assert parse_operating_lease_commitments(broken) == {}
