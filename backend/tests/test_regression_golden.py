"""Golden-case regression: replay saved analyses offline and require unchanged results."""

import pytest

from regression import cases
from regression.compare import diff

CASE_DIRS = cases.list_cases()


def test_diff_tolerates_float_noise_and_reports_changes():
    assert diff({"a": 1.0}, {"a": 1.0000000001}) == []
    assert diff({"a": "HOLD"}, {"a": "WATCH"}) == ["/a: HOLD -> WATCH"]
    assert diff({"a": [1, 2]}, {"a": [1, 3]})
    assert diff({"a": 1}, {}) and diff({}, {"a": 1})


def test_golden_cases_exist():
    assert CASE_DIRS, "no regression cases found"


@pytest.mark.parametrize("case_dir", CASE_DIRS, ids=[c.name for c in CASE_DIRS])
def test_golden_case_unchanged(case_dir):
    result = cases.check_case(case_dir)
    assert result.passed, f"{result.name}: {result.error or result.diffs[:10]}"
