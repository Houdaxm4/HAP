"""Cash Flow module tests per FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, CashFlowModule
from analysis_engine.metric_comparison import extract_metric_comparisons
from canonical_model import build_company_financial_model
from rule_library import evaluate_cash_flow_rules
from rule_library.cash_flow import CashFlowRuleInputs
from scoring_engine import CASH_FLOW_WEIGHTS, score_cash_flow
from scoring_engine.cash_flow import CashFlowScoreInputs
from scoring_engine.components import score_cash_conversion, score_fcf_margin


PERIODS = ["FY2020", "FY2021", "FY2022", "FY2023", "FY2024"]


def _geo(start: float, rate: float, n: int = 5) -> dict[str, float]:
    return {PERIODS[i]: start * ((1.0 + rate) ** i) for i in range(n)}


def _cells(
    *,
    revenue: dict[str, float],
    net_income: dict[str, float],
    ocf: dict[str, float],
    capex: dict[str, float] | None = None,
    fcf: dict[str, float] | None = None,
    workbook_metrics: list[dict] | None = None,
    metadata: dict | None = None,
) -> list[dict]:
    cells: list[dict] = []
    for concept, series, prefix in [
        ("Revenue", revenue, "REV"),
        ("Net Income", net_income, "NI"),
        ("Operating Cash Flow", ocf, "OCF"),
    ]:
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
    if capex is not None:
        for period, value in capex.items():
            cells.append(
                {
                    "concept": "Capital Expenditures",
                    "period": period,
                    "value": value,
                    "confidence": 0.9,
                    "audited": True,
                    "source": "SEC 10-K",
                    "cell_ref": f"CAPEX_{period}",
                }
            )
    if fcf is not None:
        for period, value in fcf.items():
            cells.append(
                {
                    "concept": "Free Cash Flow",
                    "period": period,
                    "value": value,
                    "confidence": 0.9,
                    "audited": True,
                    "source": "SEC 10-K",
                    "cell_ref": f"FCF_{period}",
                }
            )
    if workbook_metrics:
        cells.extend(workbook_metrics)
    return cells


def _build(**kwargs):
    return build_company_financial_model(
        analysis_id="cf-test",
        ticker="CFLOW",
        company="Cash Flow Co",
        workbook_cells=_cells(**kwargs),
        metadata=kwargs.get("metadata") or {},
    )


def _rule_ids(result) -> set[str]:
    return {finding.rule_id for finding in result.findings if finding.rule_id}


def test_cash_flow_weights_match_scoring_system() -> None:
    assert CASH_FLOW_WEIGHTS["FREE_CASH_FLOW"] == 0.30
    assert CASH_FLOW_WEIGHTS["CASH_CONVERSION"] == 0.30
    assert CASH_FLOW_WEIGHTS["OWNER_EARNINGS"] == 0.20
    assert CASH_FLOW_WEIGHTS["FCF_STABILITY"] == 0.20
    assert abs(sum(CASH_FLOW_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_cash_flow_deterministic_and_renormalizes() -> None:
    full = score_cash_flow(
        CashFlowScoreInputs(
            fcf_margin=0.12,
            cash_conversion=1.05,
            owner_earnings_margin=0.10,
            fcf_stability=0.85,
            latest_fcf=50.0,
        )
    )
    again = score_cash_flow(
        CashFlowScoreInputs(
            fcf_margin=0.12,
            cash_conversion=1.05,
            owner_earnings_margin=0.10,
            fcf_stability=0.85,
            latest_fcf=50.0,
        )
    )
    assert full.score == again.score
    assert full.score is not None and 70 <= full.score <= 95
    assert abs(sum(full.effective_weights.values()) - 1.0) < 1e-9

    partial = score_cash_flow(
        CashFlowScoreInputs(fcf_margin=0.10, cash_conversion=0.95, latest_fcf=20.0)
    )
    assert partial.score is not None
    assert "OWNER_EARNINGS" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_component_mappers_align_with_cf_rules() -> None:
    assert score_cash_conversion(1.05) >= 85
    assert score_cash_conversion(0.65) <= 55
    assert score_fcf_margin(0.15, latest_fcf=10.0) >= 80
    assert score_fcf_margin(0.05, latest_fcf=-5.0) <= 30


def test_excellent_cash_generator() -> None:
    revenue = _geo(100.0, 0.08)
    ni = {p: revenue[p] * 0.15 for p in PERIODS}
    ocf = {p: ni[p] * 1.15 for p in PERIODS}
    fcf = {p: ocf[p] - 10.0 for p in PERIODS}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, fcf=fcf)
    result = CashFlowModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and result.score >= 70
    rules = _rule_ids(result)
    assert "CF001" in rules
    assert "CF002" in rules
    assert all(finding.evidence for finding in result.findings)


def test_weak_cash_conversion() -> None:
    revenue = _geo(100.0, 0.04)
    ni = {p: revenue[p] * 0.12 for p in PERIODS}
    ocf = {p: ni[p] * 0.55 for p in PERIODS}
    fcf = {p: ocf[p] - 8.0 for p in PERIODS}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, fcf=fcf)
    result = CashFlowModule().analyze(model)
    assert result.status == "ok"
    assert "CF003" in _rule_ids(result)
    assert any(risk.code == "POOR_CASH_CONVERSION" for risk in result.risks)
    assert any(adj.action == "review_assumption" for adj in result.analyst_adjustments)


def test_persistent_cash_burn() -> None:
    revenue = _geo(100.0, 0.02)
    ni = {p: revenue[p] * 0.05 for p in PERIODS}
    ocf = {p: 5.0 for p in PERIODS}
    fcf = {"FY2022": -5.0, "FY2023": -8.0, "FY2024": -12.0, "FY2020": 2.0, "FY2021": 1.0}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, fcf=fcf)
    result = CashFlowModule().analyze(model)
    assert "CF004" in _rule_ids(result)
    assert any(risk.code == "PERSISTENT_CASH_BURN" for risk in result.risks)
    assert result.score is not None and result.score < 60


def test_owner_earnings_increasing_cf005() -> None:
    revenue = _geo(100.0, 0.06)
    ni = {p: revenue[p] * 0.10 for p in PERIODS}
    ocf = {p: 20.0 + i * 5.0 for i, p in enumerate(PERIODS)}
    capex = {p: -8.0 for p in PERIODS}
    model = _build(
        revenue=revenue,
        net_income=ni,
        ocf=ocf,
        capex=capex,
        metadata={"maintenance_capex_by_period": {p: 5.0 for p in PERIODS}},
    )
    result = CashFlowModule().analyze(model)
    assert "CF005" in _rule_ids(result)
    assert any(opp.code == "STRONG_OWNER_EARNINGS" for opp in result.opportunities)


def test_capex_rising_revenue_stagnant_cf006() -> None:
    revenue = {p: 100.0 for p in PERIODS}
    ni = {p: 10.0 for p in PERIODS}
    ocf = {p: 15.0 for p in PERIODS}
    capex = {p: -(10.0 + i * 4.0) for i, p in enumerate(PERIODS)}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, capex=capex)
    result = CashFlowModule().analyze(model)
    assert "CF006" in _rule_ids(result)
    assert any(risk.code == "HIGH_CAPEX_DEPENDENCY" for risk in result.risks)


def test_derives_fcf_when_missing() -> None:
    revenue = _geo(100.0, 0.05)
    ni = {p: revenue[p] * 0.10 for p in PERIODS}
    ocf = {p: 25.0 for p in PERIODS}
    capex = {p: -10.0 for p in PERIODS}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, capex=capex)
    result = CashFlowModule().analyze(model)
    assert result.status == "ok"
    assert result.coverage.get("fcf_derived") is True
    assert result.score is not None


def test_workbook_metric_comparisons_attached() -> None:
    revenue = _geo(100.0, 0.08)
    ni = {p: revenue[p] * 0.12 for p in PERIODS}
    ocf = {p: ni[p] * 1.10 for p in PERIODS}
    fcf = {p: ocf[p] - 10.0 for p in PERIODS}
    model = _build(
        revenue=revenue,
        net_income=ni,
        ocf=ocf,
        fcf=fcf,
        workbook_metrics=[
            {
                "concept": "Cash Conversion",
                "period": "FY2024",
                "value": 1.08,
                "is_workbook_metric": True,
                "is_formula": True,
                "cell_ref": "CF!B4",
            },
            {
                "concept": "FCF Margin",
                "period": "FY2024",
                "value": 0.11,
                "is_workbook_metric": True,
                "is_formula": True,
                "cell_ref": "CF!B6",
            },
        ],
    )
    result = CashFlowModule().analyze(model)
    comparisons = extract_metric_comparisons(result.coverage)
    assert comparisons
    codes = {item.metric_code for item in comparisons}
    assert "CASH_CONVERSION" in codes
    assert "FCF_MARGIN" in codes
    for item in comparisons:
        if item.workbook_value is not None and item.hap_value is not None:
            assert item.difference is not None
            assert item.tolerance is not None
            assert item.status
            assert item.recommended_action


def test_skipped_without_cash_flow_inputs() -> None:
    model = build_company_financial_model(
        analysis_id="empty-cf",
        ticker="NONE",
        workbook_cells=[
            {
                "concept": "Revenue",
                "period": "FY2024",
                "value": 100.0,
                "audited": True,
            }
        ],
    )
    result = CashFlowModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None


def test_cf_rules_evaluator_unit() -> None:
    hits = evaluate_cash_flow_rules(
        CashFlowRuleInputs(
            cash_conversion=0.65,
            fcf_by_period={"FY2022": -1.0, "FY2023": -2.0, "FY2024": -3.0},
            owner_earnings_by_period={
                "FY2020": 5.0,
                "FY2021": 8.0,
                "FY2022": 10.0,
                "FY2023": 12.0,
                "FY2024": 15.0,
            },
            capex_cagr=0.10,
            revenue_cagr=0.01,
            latest_fcf=-3.0,
            period="FY2024",
        )
    )
    rule_ids = {hit.rule.rule_id for hit in hits}
    assert "CF003" in rule_ids
    assert "CF004" in rule_ids
    assert "CF005" in rule_ids
    assert "CF006" in rule_ids


def test_engine_includes_cash_flow_score() -> None:
    revenue = _geo(100.0, 0.07)
    ni = {p: revenue[p] * 0.12 for p in PERIODS}
    ocf = {p: ni[p] * 1.12 for p in PERIODS}
    fcf = {p: ocf[p] - 9.0 for p in PERIODS}
    model = _build(revenue=revenue, net_income=ni, ocf=ocf, fcf=fcf)
    engine_result = AnalysisEngine(modules=[CashFlowModule()]).run(model)
    cf = engine_result.modules[0]
    assert cf.module_name == "cash_flow"
    assert cf.score is not None
    assert len(engine_result.metric_comparisons) >= 1
