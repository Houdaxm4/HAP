"""Expected Return module tests per HAP methodology + SCORING_SYSTEM.md."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, ExpectedReturnModule
from analysis_engine.metric_comparison import extract_metric_comparisons
from canonical_model import build_company_financial_model
from rule_library import EXPECTED_RETURN_RULES, evaluate_expected_return_rules
from scoring_engine import EXPECTED_RETURN_WEIGHTS, score_expected_return
from scoring_engine.expected_return import EXPECTED_RETURN_CONFIDENCE_CAP, ExpectedReturnScoreInputs

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
        "cell_ref": f"ER!{code}",
    }


def _base_financials() -> dict[str, dict[str, float]]:
    revenue = {p: 500.0 + i * 25 for i, p in enumerate(PERIODS)}
    oi = {p: 100.0 + i * 5 for i, p in enumerate(PERIODS)}
    ebitda = {p: 120.0 + i * 5 for i, p in enumerate(PERIODS)}
    ni = {p: 70.0 + i * 3 for i, p in enumerate(PERIODS)}
    eps = {p: 5.0 + i * 0.4 for i, p in enumerate(PERIODS)}
    ocf = {p: 90.0 + i * 4 for i, p in enumerate(PERIODS)}
    capex = {p: -20.0 for p in PERIODS}
    fcf = {p: ocf[p] + capex[p] for p in PERIODS}
    debt = {p: 150.0 for p in PERIODS}
    cash = {p: 50.0 for p in PERIODS}
    dividends = {p: -12.0 - i for i, p in enumerate(PERIODS)}
    buybacks = {p: -8.0 for p in PERIODS}
    return {
        "revenue": revenue,
        "operating_income": oi,
        "ebitda": ebitda,
        "net_income": ni,
        "eps": eps,
        "ocf": ocf,
        "capex": capex,
        "fcf": fcf,
        "debt": debt,
        "cash": cash,
        "dividends": dividends,
        "buybacks": buybacks,
    }


def _build(
    *,
    share_price: float | None = 50.0,
    shares_outstanding: float = 10.0,
    wacc: float = 0.09,
    terminal_growth: float = 0.025,
    workbook_metrics: list[dict] | None = None,
    metadata: dict | None = None,
    financials: dict[str, dict[str, float]] | None = None,
):
    fin = financials or _base_financials()
    cells: list[dict] = []
    _add_series(cells, "Revenue", fin["revenue"], "REV")
    _add_series(cells, "Operating Income", fin["operating_income"], "OI")
    _add_series(cells, "EBITDA", fin["ebitda"], "EBITDA")
    _add_series(cells, "Net Income", fin["net_income"], "NI")
    _add_series(cells, "Diluted EPS", fin["eps"], "EPS")
    _add_series(cells, "Operating Cash Flow", fin["ocf"], "OCF")
    _add_series(cells, "Capital Expenditures", fin["capex"], "CAPEX")
    _add_series(cells, "Free Cash Flow", fin["fcf"], "FCF")
    _add_series(cells, "Total Debt", fin["debt"], "DEBT")
    _add_series(cells, "Cash and Cash Equivalents", fin["cash"], "CASH")
    _add_series(cells, "Dividends Paid", fin["dividends"], "DIV")
    _add_series(cells, "Share Repurchases", fin["buybacks"], "BB")
    if workbook_metrics:
        cells.extend(workbook_metrics)

    market: dict = {"shares_outstanding": shares_outstanding}
    if share_price is not None:
        market["share_price"] = share_price

    meta = {
        "valuation": {
            "peer_ev_to_ebitda": {"p25": 6.0, "median": 8.0, "p75": 10.0},
            "maintenance_capex": 15.0,
        },
    }
    if metadata:
        meta.update(metadata)
        if "valuation" in metadata:
            meta["valuation"] = {**meta.get("valuation", {}), **metadata["valuation"]}

    return build_company_financial_model(
        analysis_id="er-test",
        ticker="ERET",
        company="Expected Return Co",
        workbook_cells=cells,
        market_data=market,
        valuation_inputs={
            "wacc": wacc,
            "terminal_growth_rate": terminal_growth,
            "forecast_years": 5,
        },
        metadata=meta,
    )


def _rule_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings if f.rule_id}


def _metric(result, code: str) -> float | None:
    for metric in result.metrics:
        if metric.code == code:
            return metric.value
    return None


def test_expected_return_weights() -> None:
    assert EXPECTED_RETURN_WEIGHTS["VALUATION_REVERSION"] == 0.30
    assert EXPECTED_RETURN_WEIGHTS["GROWTH_CONTRIBUTION"] == 0.25
    assert abs(sum(EXPECTED_RETURN_WEIGHTS.values()) - 1.0) < 1e-9
    assert len(EXPECTED_RETURN_RULES) == 30


def test_high_expected_return_undervalued() -> None:
    """Low price vs fair value -> high expected return."""
    model = _build(share_price=25.0)
    result = ExpectedReturnModule().analyze(model)
    assert result.status == "ok"
    cagr = _metric(result, "EXPECTED_CAGR")
    assert cagr is not None and cagr > 0.12
    assert result.score is not None and result.score >= 70
    rules = _rule_ids(result)
    assert "ER001" in rules or "ER002" in rules
    assert "ER007" in rules or "ER013" in rules
    assert result.confidence <= EXPECTED_RETURN_CONFIDENCE_CAP
    assert result.coverage.get("assumptions")


def test_moderate_return_fairly_priced() -> None:
    model = _build(share_price=95.0)
    result = ExpectedReturnModule().analyze(model)
    assert result.status == "ok"
    cagr = _metric(result, "EXPECTED_CAGR")
    assert cagr is not None and 0.05 <= cagr <= 0.12
    assert result.score is not None and 45 <= result.score <= 80


def test_poor_return_overvalued() -> None:
    model = _build(share_price=200.0)
    result = ExpectedReturnModule().analyze(model)
    assert result.status == "ok"
    cagr = _metric(result, "EXPECTED_CAGR")
    rules = _rule_ids(result)
    assert cagr is not None and cagr < 0.08
    assert "ER004" in rules or "ER005" in rules or "ER010" in rules
    assert result.score is not None and result.score <= 55


def test_negative_expected_return() -> None:
    model = _build(share_price=350.0)
    result = ExpectedReturnModule().analyze(model)
    cagr = _metric(result, "EXPECTED_CAGR")
    if cagr is not None and cagr < 0:
        assert "ER006" in _rule_ids(result)


def test_workbook_return_mismatch() -> None:
    model = _build(
        share_price=50.0,
        workbook_metrics=[
            _wb_metric("EXPECTED_CAGR", 0.20),
            _wb_metric("EXPECTED_IRR", 0.22),
        ],
    )
    result = ExpectedReturnModule().analyze(model)
    rules = _rule_ids(result)
    assert "ER025" in rules or "ER026" in rules
    comparisons = extract_metric_comparisons(result.coverage)
    assert any(c.status == "divergent" for c in comparisons)


def test_workbook_return_aligned() -> None:
    model = _build(share_price=30.0)
    first = ExpectedReturnModule().analyze(model)
    hap_cagr = _metric(first, "EXPECTED_CAGR")
    assert hap_cagr is not None
    model2 = _build(
        share_price=30.0,
        workbook_metrics=[
            _wb_metric("EXPECTED_CAGR", hap_cagr),
            _wb_metric("EXPECTED_IRR", _metric(first, "EXPECTED_IRR") or hap_cagr),
        ],
    )
    result = ExpectedReturnModule().analyze(model2)
    assert "ER027" in _rule_ids(result)


def test_return_decomposition_metrics() -> None:
    model = _build(share_price=40.0)
    result = ExpectedReturnModule().analyze(model)
    assert _metric(result, "GROWTH_CONTRIBUTION") is not None
    assert _metric(result, "VALUATION_REVERSION") is not None
    assert _metric(result, "DIVIDEND_YIELD") is not None
    assert _metric(result, "BUYBACK_YIELD") is not None
    assert _metric(result, "EXPECTED_IRR") is not None


def test_scenario_returns() -> None:
    model = _build(share_price=45.0)
    result = ExpectedReturnModule().analyze(model)
    scenarios = result.coverage.get("scenarios", {})
    assert "bear" in scenarios
    assert "base" in scenarios
    assert "bull" in scenarios
    assert _metric(result, "SCENARIO_BEAR_EXPECTED_CAGR") is not None
    assert _metric(result, "SCENARIO_BULL_EXPECTED_CAGR") is not None


def test_skipped_without_price_and_valuation() -> None:
    model = build_company_financial_model(
        analysis_id="skip-er",
        ticker="SKIP",
        workbook_cells=[],
    )
    result = ExpectedReturnModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None


def test_deterministic_replay() -> None:
    model = _build(share_price=42.0)
    first = ExpectedReturnModule().analyze(model)
    second = ExpectedReturnModule().analyze(model)
    assert first.score == second.score
    assert first.confidence == second.confidence
    assert {(m.code, m.value) for m in first.metrics} == {(m.code, m.value) for m in second.metrics}
    assert _rule_ids(first) == _rule_ids(second)


def test_scoring_renormalization() -> None:
    partial = score_expected_return(
        ExpectedReturnScoreInputs(
            expected_cagr=0.12,
            valuation_reversion=0.06,
        )
    )
    assert partial.score is not None
    assert "DIVIDEND_YIELD" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_assumption_provenance() -> None:
    model = _build(
        share_price=40.0,
        metadata={
            "expected_return": {
                "sp500_expected_return": 0.085,
                "holding_period_years": 7,
                "assumption_evidence": {
                    "sp500_expected_return": {
                        "source": "macro_overlay",
                        "confidence": 0.80,
                    },
                },
            },
        },
    )
    result = ExpectedReturnModule().analyze(model)
    assumptions = result.coverage.get("assumptions", [])
    assert assumptions
    codes = {a["code"] for a in assumptions}
    assert "FAIR_VALUE_BASE" in codes
    assert "EPS_GROWTH_CONTRIBUTION" in codes or "FCF_GROWTH_CONTRIBUTION" in codes
    assert result.coverage.get("valuation_methods_used") is not None
    assert result.coverage.get("valuation_source") == "hap_valuation_engine"
    sp500 = [a for a in assumptions if a["code"] == "SP500_EXPECTED_RETURN"]
    assert sp500 and sp500[0]["source"]
    assert "confidence" in sp500[0]
    assert "provenance" in sp500[0]


def test_engine_includes_expected_return() -> None:
    model = _build(share_price=40.0)
    engine_result = AnalysisEngine().run(model)
    er = next(m for m in engine_result.modules if m.module_name == "expected_return")
    assert er.status == "ok"
    assert er.score is not None


def test_rule_library_evaluate() -> None:
    from rule_library.expected_return import ExpectedReturnRuleInputs

    hits = evaluate_expected_return_rules(
        ExpectedReturnRuleInputs(expected_cagr=0.16, period="FY2024")
    )
    assert any(h.rule.rule_id == "ER001" for h in hits)
