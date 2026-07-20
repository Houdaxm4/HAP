"""Capital Allocation module tests per FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, CapitalAllocationModule
from analysis_engine.metric_comparison import extract_metric_comparisons
from canonical_model import build_company_financial_model
from rule_library import evaluate_capital_allocation_rules
from rule_library.capital_allocation import CapitalAllocationRuleInputs
from scoring_engine import CAPITAL_ALLOCATION_WEIGHTS, score_capital_allocation
from scoring_engine.capital_allocation import CapitalAllocationScoreInputs

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


def _build(
    *,
    invested_capital: dict[str, float],
    operating_income: dict[str, float],
    tax_expense: dict[str, float] | None = None,
    revenue: dict[str, float] | None = None,
    fcf: dict[str, float] | None = None,
    dividends: dict[str, float] | None = None,
    buybacks: dict[str, float] | None = None,
    total_debt: dict[str, float] | None = None,
    eps: dict[str, float] | None = None,
    workbook_metrics: list[dict] | None = None,
    metadata: dict | None = None,
    wacc: float = 0.09,
):
    cells: list[dict] = []
    _add_series(cells, "Invested Capital", invested_capital, "IC")
    _add_series(cells, "Operating Income", operating_income, "OI")
    if tax_expense:
        _add_series(cells, "Tax Expense", tax_expense, "TAX")
    if revenue:
        _add_series(cells, "Revenue", revenue, "REV")
    if fcf:
        _add_series(cells, "Free Cash Flow", fcf, "FCF")
    if dividends:
        _add_series(cells, "Dividends Paid", dividends, "DIV")
    if buybacks:
        _add_series(cells, "Share Repurchases", buybacks, "BB")
    if total_debt:
        _add_series(cells, "Total Debt", total_debt, "DEBT")
    if eps:
        _add_series(cells, "Diluted EPS", eps, "EPS")
    if workbook_metrics:
        cells.extend(workbook_metrics)
    return build_company_financial_model(
        analysis_id="ca-test",
        ticker="ALLOC",
        company="Allocation Co",
        workbook_cells=cells,
        valuation_inputs={"wacc": wacc},
        metadata=metadata or {},
    )


def _rule_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings if f.rule_id}


def test_capital_allocation_weights() -> None:
    assert CAPITAL_ALLOCATION_WEIGHTS["ROIC_TREND"] == 0.30
    assert CAPITAL_ALLOCATION_WEIGHTS["SHARE_BUYBACKS"] == 0.20
    assert CAPITAL_ALLOCATION_WEIGHTS["DIVIDEND_POLICY"] == 0.10
    assert CAPITAL_ALLOCATION_WEIGHTS["REINVESTMENT_QUALITY"] == 0.20
    assert CAPITAL_ALLOCATION_WEIGHTS["ACQUISITION_QUALITY"] == 0.20
    assert abs(sum(CAPITAL_ALLOCATION_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_renormalization() -> None:
    partial = score_capital_allocation(
        CapitalAllocationScoreInputs(
            roic_change=0.04,
            share_count_cagr=-0.03,
        )
    )
    assert partial.score is not None
    assert "DIVIDEND_POLICY" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_excellent_capital_allocation() -> None:
    """Improving ROIC, declining share count, sustainable dividends and buybacks."""
    invested = {p: 500.0 - i * 10 for i, p in enumerate(PERIODS)}
    oi = {p: 80.0 + i * 8 for i, p in enumerate(PERIODS)}
    tax = {p: 20.0 for p in PERIODS}
    fcf = {p: 60.0 for p in PERIODS}
    dividends = {p: 10.0 + i * 2 for i, p in enumerate(PERIODS)}
    buybacks = {p: -15.0 for p in PERIODS}
    debt = {p: 100.0 - i * 5 for i, p in enumerate(PERIODS)}
    eps = {p: 4.0 + i * 0.5 for i, p in enumerate(PERIODS)}
    shares = {p: 100.0 - i * 3 for i, p in enumerate(PERIODS)}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        tax_expense=tax,
        revenue={p: 400.0 + i * 20 for i, p in enumerate(PERIODS)},
        fcf=fcf,
        dividends=dividends,
        buybacks=buybacks,
        total_debt=debt,
        eps=eps,
        metadata={
            "share_count_series": shares,
            "buybacks_below_intrinsic": True,
        },
    )
    result = CapitalAllocationModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and result.score >= 70
    rules = _rule_ids(result)
    assert "CA001" in rules
    assert "CA003" in rules
    assert "CA004" in rules
    assert all(f.evidence for f in result.findings)
    assert result.component_scores
    assert {c.code for c in result.component_scores} >= {
        "ROIC_TREND",
        "SHARE_BUYBACKS",
        "DIVIDEND_POLICY",
    }


def test_value_destructive_acquisition() -> None:
    invested = {p: 500.0 + i * 30 for i, p in enumerate(PERIODS)}
    oi = {p: 70.0 - i * 8 for i, p in enumerate(PERIODS)}
    tax = {p: 15.0 for p in PERIODS}
    revenue = {p: 300.0 + i * 50 for i, p in enumerate(PERIODS)}
    fcf = {p: 40.0 for p in PERIODS}
    acq_spend = {p: 80.0 if i >= 2 else 5.0 for i, p in enumerate(PERIODS)}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        tax_expense=tax,
        revenue=revenue,
        fcf=fcf,
        total_debt={p: 120.0 + i * 20 for i, p in enumerate(PERIODS)},
        metadata={"acquisition_spend_by_period": acq_spend},
    )
    result = CapitalAllocationModule().analyze(model)
    assert result.status == "ok"
    rules = _rule_ids(result)
    assert "CA002" in rules or "CA006" in rules
    assert any(r.code in {"VALUE_DESTRUCTIVE_ACQUISITION", "DETERIORATING_REINVESTMENT_RETURNS"} for r in result.risks)
    assert result.score is not None and result.score < 70


def test_debt_funded_buybacks() -> None:
    invested = {p: 400.0 for p in PERIODS}
    oi = {p: 60.0 for p in PERIODS}
    fcf = {p: 50.0 for p in PERIODS}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        fcf=fcf,
        buybacks={p: -20.0 for p in PERIODS},
        total_debt={p: 80.0 + i * 25 for i, p in enumerate(PERIODS)},
        metadata={"share_count_series": {p: 100.0 - i for i, p in enumerate(PERIODS)}},
    )
    result = CapitalAllocationModule().analyze(model)
    assert "CA005" in _rule_ids(result)
    assert any(r.code == "AGGRESSIVE_FINANCIAL_ENGINEERING" for r in result.risks)


def test_unsustainable_dividend() -> None:
    invested = {p: 400.0 for p in PERIODS}
    oi = {p: 50.0 for p in PERIODS}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        fcf={p: 20.0 for p in PERIODS},
        dividends={p: -30.0 for p in PERIODS},
    )
    result = CapitalAllocationModule().analyze(model)
    assert "CA009" in _rule_ids(result)
    assert result.score is not None and result.score < 65


def test_shareholder_dilution() -> None:
    invested = {p: 400.0 for p in PERIODS}
    oi = {p: 55.0 for p in PERIODS}
    shares = {p: 100.0 + i * 8 for i, p in enumerate(PERIODS)}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        metadata={"share_count_series": shares},
    )
    result = CapitalAllocationModule().analyze(model)
    assert "CA007" in _rule_ids(result)


def test_insufficient_history_reduces_confidence() -> None:
    invested = {"FY2023": 400.0, "FY2024": 420.0}
    oi = {"FY2023": 50.0, "FY2024": 55.0}
    model = _build(invested_capital=invested, operating_income=oi)
    result = CapitalAllocationModule().analyze(model)
    assert result.status == "ok"
    assert "CA023" in _rule_ids(result)
    assert result.confidence < 0.75


def test_workbook_metric_comparison() -> None:
    invested = {p: 500.0 for p in PERIODS}
    oi = {p: 80.0 for p in PERIODS}
    workbook = [
        {
            "concept": "ROIC",
            "period": "FY2024",
            "value": 0.14,
            "metric_origin": "workbook",
            "cell_ref": "WB_ROIC",
        }
    ]
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        tax_expense={p: 18.0 for p in PERIODS},
        workbook_metrics=workbook,
    )
    result = CapitalAllocationModule().analyze(model)
    comparisons = extract_metric_comparisons(result.coverage)
    roic_cmp = next((c for c in comparisons if c.metric_code == "ROIC"), None)
    assert roic_cmp is not None
    assert roic_cmp.hap_value is not None
    assert roic_cmp.workbook_value == 0.14


def test_deterministic_scoring() -> None:
    first = score_capital_allocation(
        CapitalAllocationScoreInputs(
            roic_change=0.05,
            share_count_cagr=-0.04,
            buyback_to_fcf=0.25,
            payout_to_fcf=0.35,
            dividend_cagr=0.06,
            reinvestment_rate=0.35,
            roic=0.18,
            wacc=0.09,
            inorganic_share=0.10,
            acquisition_intensity=0.05,
        )
    )
    second = score_capital_allocation(
        CapitalAllocationScoreInputs(
            roic_change=0.05,
            share_count_cagr=-0.04,
            buyback_to_fcf=0.25,
            payout_to_fcf=0.35,
            dividend_cagr=0.06,
            reinvestment_rate=0.35,
            roic=0.18,
            wacc=0.09,
            inorganic_share=0.10,
            acquisition_intensity=0.05,
        )
    )
    assert first.score == second.score
    assert first.score is not None
    assert 0 <= first.score <= 100


def test_rules_emit_evidence() -> None:
    hits = evaluate_capital_allocation_rules(
        CapitalAllocationRuleInputs(
            roic_change=0.05,
            share_count_cagr=-0.04,
            buybacks_below_intrinsic=True,
            period="FY2024",
            history_points=5,
        )
    )
    assert hits
    for hit in hits:
        finding = hit.to_finding()
        assert finding.evidence
        assert finding.rule_id is not None


def test_module_skips_without_inputs() -> None:
    model = build_company_financial_model(
        analysis_id="empty",
        ticker="NONE",
        workbook_cells=[],
    )
    result = CapitalAllocationModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None


def test_engine_includes_capital_allocation() -> None:
    invested = {p: 500.0 for p in PERIODS}
    oi = {p: 80.0 for p in PERIODS}
    model = _build(
        invested_capital=invested,
        operating_income=oi,
        fcf={p: 55.0 for p in PERIODS},
        dividends={p: -12.0 for p in PERIODS},
        metadata={"share_count_series": {p: 100.0 - i for i, p in enumerate(PERIODS)}},
    )
    engine_result = AnalysisEngine().run(model)
    ca = next(m for m in engine_result.modules if m.module_name == "capital_allocation")
    assert ca.status == "ok"
    assert ca.score is not None
    assert ca.module_name == "capital_allocation"
