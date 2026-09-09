"""Focused tests for final investment recommendation synthesis."""

from __future__ import annotations

from services.final_recommendation_service import FinalRecommendationService


def _roic_positive() -> dict:
    return {
        "overall_decision": "MATERIAL_REVIEW",
        "historical_spread_interpretation": "consistently positive value creation",
        "periods": [
            {"roic_minus_wacc": 1.0},
            {"roic_minus_wacc": 0.9},
            {"roic_minus_wacc": 0.8},
        ],
    }


def _roic_negative() -> dict:
    return {
        "overall_decision": "VALIDATED",
        "historical_spread_interpretation": "value destruction",
        "periods": [
            {"roic_minus_wacc": -0.05},
            {"roic_minus_wacc": -0.08},
            {"roic_minus_wacc": -0.04},
        ],
    }


def _val(*, price: float, iv: float, attractiveness: str) -> dict:
    mos = (iv - price) / iv
    entry = iv * 0.75
    return {
        "current_price": price,
        "workbook_intrinsic_value": iv,
        "independent_intrinsic_value": iv,
        "margin_of_safety": mos,
        "required_entry_price": entry,
        "attractiveness": attractiveness,
        "decision": "VALIDATED",
    }


def test_strong_company_expensive_stock_wait_not_buy():
    svc = FinalRecommendationService()
    report = svc.synthesize(
        analysis_id="t1",
        ticker="AAPL",
        valuation=_val(price=306, iv=291, attractiveness="EXPENSIVE"),
        roic=_roic_positive(),
        expected_return={"expected_return_decision": "SOURCE_MISSING", "attractiveness": "indeterminate"},
    )
    assert report.business_quality_score is not None and report.business_quality_score >= 80
    assert report.investment_attractiveness_score is not None
    assert report.investment_attractiveness_score < 60
    assert report.final_recommendation == "WAIT_FOR_BETTER_PRICE"
    assert report.final_recommendation != "BUY"
    assert report.entry_condition is not None
    assert report.entry_condition.required_entry_price == pytest_approx(291 * 0.75)


def pytest_approx(x):
    import pytest

    return pytest.approx(x)


def test_strong_company_with_25pct_mos_buy():
    svc = FinalRecommendationService()
    # IV 200, price 150 → MOS 25%
    report = svc.synthesize(
        analysis_id="t2",
        ticker="TEST",
        valuation=_val(price=150, iv=200, attractiveness="ATTRACTIVE"),
        roic=_roic_positive(),
        expected_return={"expected_return_decision": "VALIDATED", "attractiveness": "attractive"},
    )
    assert report.margin_of_safety == pytest_approx(0.25)
    assert report.final_recommendation in {"BUY", "STRONG_BUY"}
    assert any("margin of safety" in r.lower() for r in report.reasons_for)


def test_weak_company_cheap_not_automatic_buy():
    svc = FinalRecommendationService()
    # Cheap: MOS 40%, but negative ROIC-WACC → weak BQ → AVOID
    report = svc.synthesize(
        analysis_id="t3",
        ticker="WEAK",
        valuation=_val(price=60, iv=100, attractiveness="ATTRACTIVE"),
        roic=_roic_negative(),
    )
    assert report.business_quality_score is not None and report.business_quality_score < 60
    assert report.final_recommendation == "AVOID"
    assert report.final_recommendation != "BUY"


def test_negative_roic_wacc_weighs_against():
    svc = FinalRecommendationService()
    report = svc.synthesize(
        analysis_id="t4",
        ticker="X",
        valuation=_val(price=80, iv=100, attractiveness="WAIT"),
        roic=_roic_negative(),
    )
    assert report.roic_wacc_assessment == "consistently_negative_value_destruction"
    assert any("ROIC" in r and "WACC" in r for r in report.reasons_against + report.key_risks)


def test_unresolved_discrepancy_lowers_confidence():
    svc = FinalRecommendationService()
    base = svc.synthesize(
        analysis_id="t5a",
        ticker="X",
        valuation=_val(price=306, iv=291, attractiveness="EXPENSIVE"),
        roic=_roic_positive(),
        statement_validation={"discrepancy_count": 0},
    )
    heavy = svc.synthesize(
        analysis_id="t5b",
        ticker="X",
        valuation=_val(price=306, iv=291, attractiveness="EXPENSIVE"),
        roic=_roic_positive(),
        statement_validation={"discrepancy_count": 10},
        analyst_review={"material_count": 4},
    )
    assert heavy.confidence < base.confidence


def test_missing_valuation_price_insufficient_data():
    svc = FinalRecommendationService()
    report = svc.synthesize(
        analysis_id="t6",
        ticker="X",
        valuation={"current_price": None, "workbook_intrinsic_value": 291, "attractiveness": "INDETERMINATE"},
        roic=_roic_positive(),
    )
    assert report.final_recommendation == "INSUFFICIENT_DATA"
    assert report.investment_attractiveness_score is None


def test_business_quality_independent_of_price():
    svc = FinalRecommendationService()
    cheap = svc.synthesize(
        analysis_id="t7a",
        ticker="X",
        valuation=_val(price=100, iv=291, attractiveness="ATTRACTIVE"),
        roic=_roic_positive(),
    )
    rich = svc.synthesize(
        analysis_id="t7b",
        ticker="X",
        valuation=_val(price=400, iv=291, attractiveness="EXPENSIVE"),
        roic=_roic_positive(),
    )
    assert cheap.business_quality_score == rich.business_quality_score
    assert cheap.investment_attractiveness_score != rich.investment_attractiveness_score


def test_reasons_trace_to_artifacts():
    svc = FinalRecommendationService()
    report = svc.synthesize(
        analysis_id="t8",
        ticker="AAPL",
        valuation=_val(price=306, iv=291, attractiveness="EXPENSIVE"),
        roic=_roic_positive(),
    )
    assert report.evidence_references
    assert "valuation_validation_report.json" in report.evidence_references
    assert report.reasons_for or report.reasons_against
    assert "price_excluded_from_business_quality" in report.evidence
