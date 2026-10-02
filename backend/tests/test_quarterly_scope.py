"""When last-quarter statements are required: New Company with Q1-Q3 only; never for Annual Update."""

from pathlib import Path

import pytest

from services.completion_scope import quarterly_analysis_required

SERVICES = Path(__file__).resolve().parents[1] / "services"


@pytest.mark.parametrize(
    ("analysis_type", "quarter", "expected"),
    [
        ("new_company", 1, True), ("new_company", 2, True), ("new_company", 3, True),
        ("new_company", 4, False), ("new_company", None, False),
        ("New Company", 2, True),
        ("annual_update", 2, False), ("annual", 3, False), ("annual_update", None, False),
        ("quarterly_update", 2, False),  # the quarterly workflow handles its own presentation
    ],
)
def test_rule(analysis_type, quarter, expected):
    assert quarterly_analysis_required(analysis_type, quarter) is expected


def test_annual_update_code_never_touches_quarterly_presentation():
    for name in ("annual_update_runner.py", "annual_output_gate_service.py"):
        source = (SERVICES / name).read_text(encoding="utf-8")
        assert "quarterly_presentation" not in source and "QuarterlyPresentation" not in source, name


def test_new_company_uses_the_shared_rule():
    for name in ("new_company_runner.py", "new_company_output_gate_service.py"):
        assert "quarterly_analysis_required" in (SERVICES / name).read_text(encoding="utf-8"), name
