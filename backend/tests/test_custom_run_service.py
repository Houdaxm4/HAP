"""Unit tests for custom_run parsing."""

from __future__ import annotations

from services.custom_run_service import CustomRunService


def test_parse_custom_run_csv(sample_custom_run_csv):
    mapping = CustomRunService().parse(sample_custom_run_csv, "custom_run_filter.csv")
    assert mapping.entry_count == 3
    assert mapping.entries[0].worksheet == "Income Statement"
    assert mapping.entries[0].cell == "B5"
    assert mapping.entries[0].concept == "Revenue"
    assert mapping.entries[0].period == "FY2024"
    assert mapping.entries[0].xbrl_tag == "Revenues"
