"""Enterprise Valuation module tests per ENTERPRISE_VALUATION_MODULE_SPEC.md."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, ValuationModule
from analysis_engine.metric_comparison import extract_metric_comparisons
from canonical_model import build_company_financial_model
from rule_library import VALUATION_RULES, evaluate_valuation_rules
from scoring_engine import VALUATION_WEIGHTS, score_valuation
from scoring_engine.valuation import VALUATION_CONFIDENCE_CAP, ValuationScoreInputs

PERIODS = ["FY2020", "FY2021", "FY2022", "FY2023", "FY2024"]


def _add_series(cells: list[dict], concept: str, series: dict[str, float], prefix: str) -> None:
    for period, value in series.items():
        cells.append(
            {
                "concept": concept,
                "period": period,
                "value": value,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
                "cell_ref": f"{prefix}_{period}",
            }
        )


def _wb_metric(code: str, value: float, *, period: str = "FY2024") -> dict:
    return {
        "concept": code.replace("_", " ").title(),
        "period": period,
        "value": value,
        "is_workbook_metric": True,
        "is_formula": True,
        "cell_ref": f"VAL!{code}",
    }


def _base_financials() -> dict[str, dict[str, float]]:
    revenue = {p: 500.0 + i * 25 for i, p in enumerate(PERIODS)}
    oi = {p: 100.0 + i * 5 for i, p in enumerate(PERIODS)}
    ebitda = {p: 120.0 + i * 5 for i, p in enumerate(PERIODS)}
    ni = {p: 70.0 + i * 3 for i, p in enumerate(PERIODS)}
    ocf = {p: 90.0 + i * 4 for i, p in enumerate(PERIODS)}
    capex = {p: -20.0 for p in PERIODS}
    fcf = {p: ocf[p] + capex[p] for p in PERIODS}
    debt = {p: 150.0 for p in PERIODS}
    cash = {p: 50.0 for p in PERIODS}
    return {
        "revenue": revenue,
        "operating_income": oi,
        "ebitda": ebitda,
        "net_income": ni,
        "ocf": ocf,
        "capex": capex,
        "fcf": fcf,
        "debt": debt,
        "cash": cash,
    }


def _build(
    *,
    share_price: float | None = 50.0,
    shares_outstanding: float = 10.0,
    wacc: float = 0.09,
    terminal_growth: float = 0.025,
    forecast_years: int = 5,
    risk_free_rate: float | None = 0.04,
    workbook_metrics: list[dict] | None = None,
    metadata: dict | None = None,
    valuation_inputs: dict | None = None,
    financials: dict[str, dict[str, float]] | None = None,
):
    fin = financials or _base_financials()
    cells: list[dict] = []
    _add_series(cells, "Revenue", fin["revenue"], "REV")
    _add_series(cells, "Operating Income", fin["operating_income"], "OI")
    _add_series(cells, "EBITDA", fin["ebitda"], "EBITDA")
    _add_series(cells, "Net Income", fin["net_income"], "NI")
    _add_series(cells, "Operating Cash Flow", fin["ocf"], "OCF")
    _add_series(cells, "Capital Expenditures", fin["capex"], "CAPEX")
    _add_series(cells, "Free Cash Flow", fin["fcf"], "FCF")
    _add_series(cells, "Total Debt", fin["debt"], "DEBT")
    _add_series(cells, "Cash and Cash Equivalents", fin["cash"], "CASH")
    if workbook_metrics:
        cells.extend(workbook_metrics)

    vi = {
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth,
        "forecast_years": forecast_years,
    }
    if risk_free_rate is not None:
        vi["risk_free_rate"] = risk_free_rate
    if valuation_inputs:
        vi.update(valuation_inputs)

    market: dict = {"shares_outstanding": shares_outstanding}
    if share_price is not None:
        market["share_price"] = share_price

    return build_company_financial_model(
        analysis_id="val-test",
        ticker="VAL",
        company="Valuation Co",
        workbook_cells=cells,
        market_data=market,
        valuation_inputs=vi,
        metadata=metadata or {},
    )


def _rule_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings if f.rule_id}


def _metric(result, code: str) -> float | None:
    for metric in result.metrics:
        if metric.code == code:
            return metric.value
    return None


def test_valuation_weights() -> None:
    assert VALUATION_WEIGHTS["MARGIN_OF_SAFETY"] == 0.35
    assert VALUATION_WEIGHTS["DCF_REASONABLENESS"] == 0.25
    assert VALUATION_WEIGHTS["MULTIPLE_REASONABLENESS"] == 0.20
    assert VALUATION_WEIGHTS["METHOD_CONVERGENCE"] == 0.10
    assert VALUATION_WEIGHTS["WORKBOOK_ALIGNMENT"] == 0.10
    assert abs(sum(VALUATION_WEIGHTS.values()) - 1.0) < 1e-9
    assert len(VALUATION_RULES) == 38


def test_deeply_undervalued() -> None:
    """Cigar butt industrials — high MOS, discount to peers/history."""
    model = _build(
        share_price=30.0,
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"p25": 6.0, "median": 8.0, "p75": 10.0},
                "historical_ev_to_ebitda": {"FY2020": 7.0, "FY2021": 7.5, "FY2022": 8.0, "FY2023": 8.5, "FY2024": 9.0},
                "gdp_nominal_growth": 0.04,
                "maintenance_capex": 15.0,
                "assumption_evidence": {
                    "wacc": {"source": "analyst_workbook", "confidence": 0.85},
                },
            }
        },
        workbook_metrics=[
            _wb_metric("MARGIN_OF_SAFETY", 0.38),
            _wb_metric("FAIR_VALUE", 48.0),
            _wb_metric("INTRINSIC_VALUE", 48.0),
        ],
    )
    result = ValuationModule().analyze(model)
    assert result.status == "ok"
    mos = _metric(result, "MARGIN_OF_SAFETY")
    assert mos is not None and mos > 0.30
    assert result.score is not None and 65 <= result.score <= 98
    rules = _rule_ids(result)
    assert "VA001" in rules
    assert "VA022" in rules or "VA025" in rules or "VA027" in rules
    assert result.confidence <= VALUATION_CONFIDENCE_CAP
    assert result.coverage.get("assumptions")
    assert len(result.coverage["assumptions"]) >= 3
    for finding in result.findings:
        assert finding.evidence


def test_fairly_valued_steady_compounder() -> None:
    model = _build(
        share_price=118.0,
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"p25": 8.0, "median": 9.0, "p75": 10.0},
                "historical_ev_to_ebitda": {"FY2024": 9.0},
                "maintenance_capex": 15.0,
            }
        },
    )
    result = ValuationModule().analyze(model)
    assert result.status == "ok"
    mos = _metric(result, "MARGIN_OF_SAFETY")
    assert mos is not None and 0.0 <= mos < 0.15
    assert result.score is not None and 50 <= result.score <= 80


def test_expensive_quality_compounder() -> None:
    model = _build(
        share_price=250.0,
        wacc=0.08,
        terminal_growth=0.04,
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"p25": 8.0, "median": 10.0, "p75": 12.0},
                "historical_ev_to_ebitda": {"FY2024": 9.0},
                "maintenance_capex": 15.0,
            }
        },
    )
    result = ValuationModule().analyze(model)
    assert result.status == "ok"
    rules = _rule_ids(result)
    assert "VA004" in rules or "VA021" in rules
    assert result.score is not None and result.score <= 55


def test_distressed_turnaround() -> None:
    fin = _base_financials()
    for p in PERIODS:
        fin["fcf"][p] = -25.0 - PERIODS.index(p) * 5
        fin["ocf"][p] = 10.0
        fin["capex"][p] = -35.0
        fin["ebitda"][p] = 5.0
    model = _build(
        share_price=80.0,
        financials=fin,
        metadata={
            "valuation": {
                "turnaround_plan": True,
                "maintenance_capex": 10.0,
            }
        },
    )
    result = ValuationModule().analyze(model)
    assert result.status == "ok"
    rules = _rule_ids(result)
    assert "VA016" in rules or "VA037" in rules or "VA018" in rules or "VA004" in rules


def test_cyclical_peak() -> None:
    fin = _base_financials()
    margins = [0.10, 0.11, 0.12, 0.13, 0.22]
    for i, p in enumerate(PERIODS):
        fin["operating_income"][p] = fin["revenue"][p] * margins[i]
        fin["ebitda"][p] = fin["operating_income"][p] * 1.2
    model = _build(
        metadata={
            "valuation": {
                "cyclicality_flag": True,
                "peer_ev_to_ebitda": {"median": 9.0},
                "maintenance_capex": 15.0,
            }
        },
        financials=fin,
    )
    result = ValuationModule().analyze(model)
    assert "VA036" in _rule_ids(result)
    adj_codes = {a.rationale_code for a in result.analyst_adjustments}
    assert "NORMALIZE_CYCLICAL_EARNINGS" in adj_codes or result.analyst_adjustments


def test_workbook_mismatch() -> None:
    model = _build(
        share_price=40.0,
        wacc=0.10,
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"median": 8.0},
                "maintenance_capex": 15.0,
            }
        },
        workbook_metrics=[
            _wb_metric("INTRINSIC_VALUE", 80.0),
            _wb_metric("MARGIN_OF_SAFETY", 0.50),
            _wb_metric("WACC", 0.08),
            _wb_metric("FAIR_VALUE", 80.0),
        ],
    )
    result = ValuationModule().analyze(model)
    rules = _rule_ids(result)
    assert "VA030" in rules or "VA031" in rules or "VA032" in rules
    comparisons = extract_metric_comparisons(result.coverage)
    assert any(c.status == "divergent" for c in comparisons)
    adj_actions = {a.action for a in result.analyst_adjustments}
    assert "reconcile_inputs" in adj_actions or "review_assumption" in adj_actions


def test_terminal_dominated_dcf() -> None:
    model = _build(
        wacc=0.09,
        terminal_growth=0.045,
        forecast_years=3,
        metadata={
            "valuation": {
                "forecast_revenue_growth": [0.01, 0.01, 0.01],
                "maintenance_capex": 15.0,
            }
        },
    )
    result = ValuationModule().analyze(model)
    terminal_share = _metric(result, "DCF_TERMINAL_VALUE_SHARE")
    rules = _rule_ids(result)
    if terminal_share is not None and terminal_share > 0.75:
        assert "VA014" in rules
    assert "VA015" in rules


def test_single_method_missing_price() -> None:
    fin = _base_financials()
    cells: list[dict] = []
    _add_series(cells, "EBITDA", fin["ebitda"], "EBITDA")
    _add_series(cells, "Free Cash Flow", fin["fcf"], "FCF")
    _add_series(cells, "Total Debt", fin["debt"], "DEBT")
    _add_series(cells, "Cash and Cash Equivalents", fin["cash"], "CASH")
    model = build_company_financial_model(
        analysis_id="single-method",
        ticker="ONE",
        workbook_cells=cells,
        market_data={"shares_outstanding": 10.0},
        valuation_inputs={},
        metadata={"valuation": {"peer_ev_to_ebitda": {"median": 8.0}}},
    )
    result = ValuationModule().analyze(model)
    assert result.status == "ok"
    assert result.score is None
    assert result.coverage.get("method_count") == 1
    assert "VA020" in _rule_ids(result)
    assert result.confidence <= 0.70
    mos_component = next(c for c in result.component_scores if c.code == "MARGIN_OF_SAFETY")
    assert not mos_component.available


def test_deterministic_replay() -> None:
    model = _build(
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"median": 8.0},
                "maintenance_capex": 15.0,
            }
        },
    )
    first = ValuationModule().analyze(model)
    second = ValuationModule().analyze(model)
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert {(m.code, m.value) for m in first.metrics} == {(m.code, m.value) for m in second.metrics}
    assert _rule_ids(first) == _rule_ids(second)


def test_skipped_module() -> None:
    model = build_company_financial_model(
        analysis_id="skip",
        ticker="SKIP",
        workbook_cells=[],
    )
    result = ValuationModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None
    assert result.confidence == 0.0


def test_scoring_components_renormalize() -> None:
    partial = score_valuation(
        ValuationScoreInputs(
            margin_of_safety=0.20,
            method_spread=0.10,
        )
    )
    assert partial.score is not None
    assert "DCF_REASONABLENESS" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_assumption_records_in_coverage() -> None:
    model = _build(
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"median": 8.0},
                "gdp_nominal_growth": 0.04,
                "maintenance_capex": 15.0,
                "assumption_evidence": {
                    "wacc": {"source": "analyst_model", "source_document": "WACC sheet", "confidence": 0.88},
                },
            }
        },
    )
    result = ValuationModule().analyze(model)
    assumptions = result.coverage.get("assumptions", [])
    assert assumptions
    wacc_records = [a for a in assumptions if a["code"] == "WACC"]
    assert wacc_records
    assert wacc_records[0]["source"]
    assert "confidence" in wacc_records[0]
    assert "provenance" in wacc_records[0]


def test_scenario_outputs() -> None:
    model = _build(
        metadata={
            "valuation": {
                "peer_ev_to_ebitda": {"p25": 6.0, "median": 8.0, "p75": 10.0},
                "maintenance_capex": 15.0,
            }
        },
    )
    result = ValuationModule().analyze(model)
    scenarios = result.coverage.get("scenarios", {})
    assert "bear" in scenarios
    assert "base" in scenarios
    assert "bull" in scenarios
    assert _metric(result, "SCENARIO_BEAR_VALUE_PER_SHARE") is not None
    assert _metric(result, "SCENARIO_BULL_VALUE_PER_SHARE") is not None
    assert _metric(result, "FAIR_VALUE_LOW") is not None
    assert _metric(result, "FAIR_VALUE_HIGH") is not None


def test_engine_includes_valuation_module() -> None:
    model = _build(
        metadata={"valuation": {"peer_ev_to_ebitda": {"median": 8.0}, "maintenance_capex": 15.0}},
    )
    engine_result = AnalysisEngine().run(model)
    val = next(m for m in engine_result.modules if m.module_name == "valuation")
    assert val.status == "ok"
    assert val.score is not None


def test_rule_library_evaluate() -> None:
    hits = evaluate_valuation_rules(
        __import__("rule_library.valuation", fromlist=["ValuationRuleInputs"]).ValuationRuleInputs(
            margin_of_safety=0.35,
            period="FY2024",
        )
    )
    assert any(h.rule.rule_id == "VA001" for h in hits)
