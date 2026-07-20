"""Growth module tests per docs/modules/GROWTH_MODULE_SPEC.md §10."""

from __future__ import annotations

from analysis_engine import GrowthModule
from canonical_model import CompanyFinancialModel, build_company_financial_model
from scoring_engine import GROWTH_WEIGHTS, score_growth
from scoring_engine.growth import GrowthScoreInputs


PERIODS = ["FY2020", "FY2021", "FY2022", "FY2023", "FY2024"]


def _geo(start: float, rate: float, n: int = 5) -> dict[str, float]:
    """n points with constant CAGR ``rate`` over n-1 years."""
    return {PERIODS[i]: start * ((1.0 + rate) ** i) for i in range(n)}


def _cells_from_series(concept: str, series: dict[str, float], prefix: str) -> list[dict]:
    return [
        {
            "concept": concept,
            "period": period,
            "value": value,
            "confidence": 0.9,
            "audited": True,
            "source": "SEC 10-K",
            "cell_ref": f"{prefix}_{period}",
        }
        for period, value in series.items()
    ]


def _build_model(
    *,
    ticker: str,
    revenue: dict[str, float],
    eps: dict[str, float] | None = None,
    fcf: dict[str, float] | None = None,
    operating_income: dict[str, float] | None = None,
    equity: dict[str, float] | None = None,
    metadata: dict | None = None,
) -> CompanyFinancialModel:
    cells: list[dict] = []
    cells.extend(_cells_from_series("Revenue", revenue, "REV"))
    if eps is not None:
        cells.extend(_cells_from_series("Diluted EPS", eps, "EPS"))
    if fcf is not None:
        cells.extend(_cells_from_series("Free Cash Flow", fcf, "FCF"))
    if operating_income is not None:
        cells.extend(_cells_from_series("Operating Income", operating_income, "OI"))
    if equity is not None:
        cells.extend(_cells_from_series("Shareholders Equity", equity, "EQ"))
    return build_company_financial_model(
        analysis_id=f"test-{ticker.lower()}",
        ticker=ticker,
        company=ticker,
        workbook_cells=cells,
        metadata=metadata or {},
    )


def _metric(result, code: str):
    for metric in result.metrics:
        if metric.code == code:
            return metric.value
    return None


def _rule_ids(result) -> set[str]:
    return {finding.rule_id for finding in result.findings if finding.rule_id}


def test_growth_weights_match_scoring_system() -> None:
    assert GROWTH_WEIGHTS["REVENUE_CAGR"] == 0.30
    assert GROWTH_WEIGHTS["EPS_CAGR"] == 0.25
    assert GROWTH_WEIGHTS["FCF_CAGR"] == 0.25
    assert GROWTH_WEIGHTS["GROWTH_STABILITY"] == 0.10
    assert GROWTH_WEIGHTS["ORGANIC_GROWTH"] == 0.10
    assert abs(sum(GROWTH_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_growth_deterministic_and_renormalizes() -> None:
    first = score_growth(
        GrowthScoreInputs(
            revenue_cagr=0.12,
            eps_cagr=0.15,
            fcf_cagr=0.14,
            growth_stability=0.85,
            organic_cagr=0.11,
            organic_data_available=True,
        )
    )
    second = score_growth(
        GrowthScoreInputs(
            revenue_cagr=0.12,
            eps_cagr=0.15,
            fcf_cagr=0.14,
            growth_stability=0.85,
            organic_cagr=0.11,
            organic_data_available=True,
        )
    )
    assert first.score == second.score
    assert first.score is not None and 80 <= first.score <= 92
    assert abs(sum(first.effective_weights.values()) - 1.0) < 1e-9

    partial = score_growth(
        GrowthScoreInputs(revenue_cagr=0.12, growth_stability=0.8, organic_data_available=False)
    )
    assert partial.score is not None
    assert "EPS_CAGR" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_compounder_co_excellent_growth() -> None:
    shares = {period: 100.0 - i * 0.5 for i, period in enumerate(PERIODS)}
    organic = _geo(100.0, 0.11)
    model = _build_model(
        ticker="CMPD",
        revenue=_geo(100.0, 0.12),
        eps=_geo(2.0, 0.15),
        fcf=_geo(20.0, 0.14),
        operating_income=_geo(25.0, 0.13),
        equity=_geo(50.0, 0.10),
        metadata={
            "share_count_series": shares,
            "organic_revenue_series": organic,
        },
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and 80 <= result.score <= 92
    assert result.score == GrowthModule().analyze(model).score
    assert abs(sum(result.coverage["effective_weights"].values()) - 1.0) < 1e-9
    rules = _rule_ids(result)
    assert rules & {"GR001", "GR002"}
    assert "GR004" in rules
    assert "GR014" in rules
    assert "GR019" in rules
    assert "GR031" in rules
    assert all(finding.evidence for finding in result.findings)
    assert not any(
        "buy" in (finding.summary or "").lower() or "sell" in (finding.summary or "").lower()
        for finding in result.findings
    )


def test_mature_industrial_average_growth() -> None:
    model = _build_model(
        ticker="MATR",
        revenue=_geo(200.0, 0.04),
        eps=_geo(3.0, 0.05),
        fcf=_geo(15.0, 0.04),
        equity=_geo(80.0, 0.03),
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and 55 <= result.score <= 70
    # 4% is above default 3% inflation → GR003 should not fire
    assert "GR003" not in _rule_ids(result)


def test_fading_retailer_deteriorating_growth() -> None:
    # Decelerating path: early growth then decline → negative acceleration
    revenue = {
        "FY2020": 100.0,
        "FY2021": 108.0,
        "FY2022": 110.0,
        "FY2023": 100.0,
        "FY2024": 78.0,
    }
    model = _build_model(
        ticker="FADE",
        revenue=revenue,
        eps=_geo(5.0, -0.10),
        fcf=_geo(10.0, -0.08),
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and 15 <= result.score <= 40
    rules = _rule_ids(result)
    assert "GR013" in rules
    assert "GR009" in rules
    assert "GR022" in rules
    risk_codes = {risk.code for risk in result.risks}
    assert "STRUCTURAL_REVENUE_DECLINE" in risk_codes
    assert "GROWTH_DECELERATION" in risk_codes


def test_blitzscale_hypergrowth() -> None:
    # Lumpy hypergrowth (high volatility) with deepening cash burn; no EPS.
    model = _build_model(
        ticker="BLITZ",
        revenue={
            "FY2020": 10.0,
            "FY2021": 22.0,
            "FY2022": 28.0,
            "FY2023": 55.0,
            "FY2024": 80.0,
        },
        fcf={
            "FY2020": -5.0,
            "FY2021": -8.0,
            "FY2022": -12.0,
            "FY2023": -18.0,
            "FY2024": -25.0,
        },
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and 45 <= result.score <= 70
    rules = _rule_ids(result)
    assert "GR001" in rules
    assert "GR025" in rules
    assert "GR011" in rules
    fcf_component = next(c for c in result.component_scores if c.code == "FCF_CAGR")
    assert fcf_component.score is not None and fcf_component.score <= 35


def test_serial_acquirer_acquisition_driven() -> None:
    revenue = _geo(100.0, 0.18)
    organic = _geo(100.0, -0.02)  # organic decline
    # Force inorganic share high via acquired overlay
    acquired = {
        period: revenue[period] - organic[period] for period in PERIODS
    }
    model = _build_model(
        ticker="ACQ",
        revenue=revenue,
        eps=_geo(1.0, 0.05),
        fcf=_geo(12.0, 0.01),
        metadata={
            "organic_revenue_series": organic,
            "acquired_revenue_by_period": acquired,
            "acquisition_primary_growth": True,
        },
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and 50 <= result.score <= 75
    rules = _rule_ids(result)
    assert "GR007" in rules
    assert "GR032" in rules
    actions = {adj.action for adj in result.analyst_adjustments}
    assert "normalize_acquisition_growth" in actions
    assert "separate_organic_growth" in actions
    organic_component = next(c for c in result.component_scores if c.code == "ORGANIC_GROWTH")
    assert organic_component.available
    assert organic_component.score is not None
    rev_component = next(c for c in result.component_scores if c.code == "REVENUE_CAGR")
    assert rev_component.score is not None
    assert organic_component.score < rev_component.score


def test_legacy_hardware_declining() -> None:
    shares = {period: 100.0 + i * 3.0 for i, period in enumerate(PERIODS)}
    model = _build_model(
        ticker="LEGACY",
        revenue=_geo(100.0, -0.12),
        eps=_geo(2.0, -0.15),
        fcf={
            "FY2020": 5.0,
            "FY2021": -2.0,
            "FY2022": -4.0,
            "FY2023": 1.0,
            "FY2024": -6.0,
        },
        metadata={"share_count_series": shares},
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and result.score < 35
    rules = _rule_ids(result)
    assert "GR013" in rules
    assert "GR006" in rules


def test_insufficient_history() -> None:
    model = _build_model(
        ticker="SHORT",
        revenue={"FY2023": 100.0, "FY2024": 110.0},
    )
    result = GrowthModule().analyze(model)
    assert result.status == "ok"
    assert "GR030" in _rule_ids(result)
    assert any(risk.code == "INSUFFICIENT_HISTORY" for risk in result.risks)
    assert any(adj.action == "request_more_data" for adj in result.analyst_adjustments)


def test_skipped_without_revenue() -> None:
    model = build_company_financial_model(
        analysis_id="test-empty",
        ticker="NONE",
        workbook_cells=[],
    )
    result = GrowthModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None


def test_covid_base_effect_and_findings_have_evidence() -> None:
    revenue = {
        "FY2020": 100.0,
        "FY2021": 50.0,  # -50% YoY in 2021
        "FY2022": 55.0,
        "FY2023": 60.0,
        "FY2024": 66.0,
    }
    model = _build_model(
        ticker="COVID",
        revenue=revenue,
        eps=_geo(1.0, 0.05),
        fcf=_geo(8.0, 0.04),
        metadata={"normalize_covid": True},
    )
    result = GrowthModule().analyze(model)
    assert "GR026" in _rule_ids(result)
    assert all(finding.evidence for finding in result.findings)
    assert any(adj.action == "normalize_covid_effects" for adj in result.analyst_adjustments)


def test_dilution_trap_gr017() -> None:
    revenue = _geo(100.0, 0.08)
    shares = {period: 100.0 * ((1.12) ** i) for i, period in enumerate(PERIODS)}
    model = _build_model(
        ticker="DILUTE",
        revenue=revenue,
        eps=_geo(1.0, 0.02),
        fcf=_geo(10.0, 0.03),
        metadata={"share_count_series": shares},
    )
    result = GrowthModule().analyze(model)
    assert "GR017" in _rule_ids(result)
    assert any(adj.action == "use_per_share_growth" for adj in result.analyst_adjustments)
