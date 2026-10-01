import json

from regression.doc_lint import lint_text
from services.deliverable_text import dedupe, headline_lines, pct_text
from services.annual_deliverables_service import _is_dated
from services.quarterly_deliverables_service import _fmt_num, _is_blank_pair, _is_suspect_identical
from services.quarterly_research_service import _is_boilerplate
from types import SimpleNamespace as NS


def test_headline_uses_final_report_and_flags_engine_difference(tmp_path):
    (tmp_path / "final_recommendation_report.json").write_text(json.dumps({
        "final_recommendation": "WATCH", "business_quality_classification": "AVERAGE_BUSINESS", "valuation_status": "EXPENSIVE"}))
    (tmp_path / "analysis_engine_result.json").write_text(json.dumps({"recommendation": {"recommendation": "AVOID"}}))
    lines = headline_lines(tmp_path)
    assert lines[0] == "Recommendation: WATCH."
    assert "average business" in lines[1] and "AVOID" in lines[2]
    assert headline_lines(tmp_path / "missing") == []


def test_percent_scale_and_dedupe_and_dates():
    assert pct_text(2.4686) == "2.47%" and pct_text(0.0247) == "2.47%" and pct_text(-0.4089) == "-40.89%"
    assert dedupe(["a", "a ", "b"]) == ["a", "b"]
    assert not _is_dated("CRF as-of / current") and _is_dated("fiscal-year-end FY2026")


def test_quarterly_guards():
    assert _is_suspect_identical(NS(compare_value=300.6, baseline_value=300.6))
    assert not _is_suspect_identical(NS(compare_value=300.6, baseline_value=280.0))
    assert _is_blank_pair(NS(compare_value=0, baseline_value=0))
    assert _fmt_num(300.6, money=True) == "$300.6M" and _fmt_num(1112.4, money=True) == "$1,112.4M"
    assert _is_boilerplate("All other trademarks, service marks and/or trade names appearing in this Quarterly Report")
    assert not _is_boilerplate("Revenue rose 12% on licensing growth.")


def test_doc_lint_catches_known_defects():
    bad = ["Valuation looks expensive on this and that today.", "Valuation looks expensive on this and that today.",
           "Current PE10: 38.9 as of CRF as-of / current", "Revenue -0.0% ($300.6M vs. $300.6M)"]
    problems = lint_text(bad, "annual")
    assert len(problems) == 4
    good = ["Recommendation: WATCH.", "Revenue +4.0% ($312.0M vs. $300.0M)"]
    assert lint_text(good, "annual") == []
