"""Balance Sheet module tests per FINANCIAL_ANALYSIS_SPEC + SCORING_SYSTEM."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, BalanceSheetModule
from analysis_engine.metric_comparison import extract_metric_comparisons
from canonical_model import build_company_financial_model
from rule_library import evaluate_balance_sheet_rules
from rule_library.balance_sheet import BalanceSheetRuleInputs
from scoring_engine import BALANCE_SHEET_WEIGHTS, score_balance_sheet
from scoring_engine.balance_sheet import BalanceSheetScoreInputs


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
    current_assets: dict[str, float],
    current_liabilities: dict[str, float],
    cash: dict[str, float] | None = None,
    total_debt: dict[str, float] | None = None,
    equity: dict[str, float] | None = None,
    operating_income: dict[str, float] | None = None,
    ebitda: dict[str, float] | None = None,
    interest_expense: dict[str, float] | None = None,
    workbook_metrics: list[dict] | None = None,
    metadata: dict | None = None,
):
    cells: list[dict] = []
    _add_series(cells, "Current Assets", current_assets, "CA")
    _add_series(cells, "Current Liabilities", current_liabilities, "CL")
    if cash:
        _add_series(cells, "Cash", cash, "CASH")
    if total_debt:
        _add_series(cells, "Total Debt", total_debt, "DEBT")
    if equity:
        _add_series(cells, "Shareholders Equity", equity, "EQ")
    if operating_income:
        _add_series(cells, "Operating Income", operating_income, "OI")
    if ebitda:
        _add_series(cells, "EBITDA", ebitda, "EBITDA")
    if interest_expense:
        _add_series(cells, "Interest Expense", interest_expense, "INT")
    if workbook_metrics:
        cells.extend(workbook_metrics)
    return build_company_financial_model(
        analysis_id="bs-test",
        ticker="BAL",
        company="Balance Co",
        workbook_cells=cells,
        metadata=metadata or {},
    )


def _rule_ids(result) -> set[str]:
    return {f.rule_id for f in result.findings if f.rule_id}


def test_balance_sheet_weights() -> None:
    assert BALANCE_SHEET_WEIGHTS["DEBT"] == 0.35
    assert BALANCE_SHEET_WEIGHTS["LIQUIDITY"] == 0.25
    assert BALANCE_SHEET_WEIGHTS["INTEREST_COVERAGE"] == 0.20
    assert BALANCE_SHEET_WEIGHTS["NET_CASH_POSITION"] == 0.10
    assert BALANCE_SHEET_WEIGHTS["WORKING_CAPITAL"] == 0.10
    assert abs(sum(BALANCE_SHEET_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_renormalization() -> None:
    partial = score_balance_sheet(
        BalanceSheetScoreInputs(
            current_ratio=2.2,
            debt_to_ebitda=2.0,
            net_debt=1_000.0,
        )
    )
    assert partial.score is not None
    assert "INTEREST_COVERAGE" not in partial.effective_weights
    assert abs(sum(partial.effective_weights.values()) - 1.0) < 1e-9


def test_excellent_balance_sheet() -> None:
    ca = {p: 200.0 + i * 10 for i, p in enumerate(PERIODS)}
    cl = {p: 80.0 for p in PERIODS}
    cash = {p: 120.0 for p in PERIODS}
    debt = {p: 100.0 - i * 5 for i, p in enumerate(PERIODS)}
    equity = {p: 500.0 for p in PERIODS}
    ebitda = {p: 80.0 for p in PERIODS}
    interest = {p: 5.0 for p in PERIODS}
    oi = {p: 60.0 for p in PERIODS}
    model = _build(
        current_assets=ca,
        current_liabilities=cl,
        cash=cash,
        total_debt=debt,
        equity=equity,
        ebitda=ebitda,
        interest_expense=interest,
        operating_income=oi,
    )
    result = BalanceSheetModule().analyze(model)
    assert result.status == "ok"
    assert result.score is not None and result.score >= 75
    rules = _rule_ids(result)
    assert "BS001" in rules
    assert "BS029" in rules or "BS005" in rules
    assert all(f.evidence for f in result.findings)


def test_weak_liquidity() -> None:
    ca = {p: 70.0 for p in PERIODS}
    cl = {p: 90.0 for p in PERIODS}
    cash = {p: 5.0 for p in PERIODS}
    debt = {p: 200.0 for p in PERIODS}
    equity = {p: 300.0 for p in PERIODS}
    ebitda = {p: 50.0 for p in PERIODS}
    model = _build(
        current_assets=ca,
        current_liabilities=cl,
        cash=cash,
        total_debt=debt,
        equity=equity,
        ebitda=ebitda,
        interest_expense={p: 10.0 for p in PERIODS},
        operating_income={p: 40.0 for p in PERIODS},
    )
    result = BalanceSheetModule().analyze(model)
    assert "BS002" in _rule_ids(result)
    assert any(r.code == "LIQUIDITY_WEAKNESS" for r in result.risks)
    assert result.score is not None and result.score < 65


def test_excessive_leverage() -> None:
    ca = {p: 150.0 for p in PERIODS}
    cl = {p: 60.0 for p in PERIODS}
    debt = {p: 400.0 for p in PERIODS}
    equity = {p: 200.0 for p in PERIODS}
    ebitda = {p: 80.0 for p in PERIODS}
    model = _build(
        current_assets=ca,
        current_liabilities=cl,
        cash={p: 20.0 for p in PERIODS},
        total_debt=debt,
        equity=equity,
        ebitda=ebitda,
        interest_expense={p: 25.0 for p in PERIODS},
        operating_income={p: 50.0 for p in PERIODS},
    )
    result = BalanceSheetModule().analyze(model)
    assert "BS003" in _rule_ids(result)
    assert any(r.code == "EXCESSIVE_LEVERAGE" for r in result.risks)
    assert result.score is not None and result.score < 55


def test_improving_leverage() -> None:
    ca = {p: 180.0 for p in PERIODS}
    cl = {p: 70.0 for p in PERIODS}
    debt = {p: 200.0 - i * 20 for i, p in enumerate(PERIODS)}
    equity = {p: 400.0 + i * 10 for i, p in enumerate(PERIODS)}
    ebitda = {p: 90.0 for p in PERIODS}
    model = _build(
        current_assets=ca,
        current_liabilities=cl,
        cash={p: 80.0 for p in PERIODS},
        total_debt=debt,
        equity=equity,
        ebitda=ebitda,
        interest_expense={p: 8.0 for p in PERIODS},
        operating_income={p: 70.0 for p in PERIODS},
    )
    result = BalanceSheetModule().analyze(model)
    rules = _rule_ids(result)
    assert "BS006" in rules
    assert "BS026" in rules or "BS012" in rules


def test_net_cash_company() -> None:
    ca = {p: 200.0 for p in PERIODS}
    cl = {p: 50.0 for p in PERIODS}
    cash = {p: 150.0 for p in PERIODS}
    debt = {p: 40.0 for p in PERIODS}
    equity = {p: 600.0 for p in PERIODS}
    ebitda = {p: 100.0 for p in PERIODS}
    model = _build(
        current_assets=ca,
        current_liabilities=cl,
        cash=cash,
        total_debt=debt,
        equity=equity,
        ebitda=ebitda,
        interest_expense={p: 2.0 for p in PERIODS},
        operating_income={p: 80.0 for p in PERIODS},
    )
    result = BalanceSheetModule().analyze(model)
    assert "BS005" in _rule_ids(result)
    assert any(o.code == "NET_CASH_POSITION" for o in result.opportunities)
    net_component = next(c for c in result.component_scores if c.code == "NET_CASH_POSITION")
    assert net_component.score is not None and net_component.score >= 90


def test_missing_interest_expense() -> None:
    model = _build(
        current_assets={p: 150.0 for p in PERIODS},
        current_liabilities={p: 60.0 for p in PERIODS},
        cash={p: 40.0 for p in PERIODS},
        total_debt={p: 250.0 for p in PERIODS},
        equity={p: 300.0 for p in PERIODS},
        ebitda={p: 70.0 for p in PERIODS},
        operating_income={p: 55.0 for p in PERIODS},
    )
    result = BalanceSheetModule().analyze(model)
    assert "BS019" in _rule_ids(result)
    assert result.confidence < 0.85
    assert any(adj.action == "request_more_data" for adj in result.analyst_adjustments)


def test_workbook_metric_comparison() -> None:
    model = _build(
        current_assets={p: 200.0 for p in PERIODS},
        current_liabilities={p: 80.0 for p in PERIODS},
        cash={p: 100.0 for p in PERIODS},
        total_debt={p: 120.0 for p in PERIODS},
        equity={p: 500.0 for p in PERIODS},
        ebitda={p: 90.0 for p in PERIODS},
        interest_expense={p: 6.0 for p in PERIODS},
        operating_income={p: 70.0 for p in PERIODS},
        workbook_metrics=[
            {
                "concept": "Current Ratio",
                "period": "FY2024",
                "value": 2.5,
                "is_workbook_metric": True,
                "is_formula": True,
                "cell_ref": "BS!B4",
            },
            {
                "concept": "Debt to EBITDA",
                "period": "FY2024",
                "value": 1.3,
                "is_workbook_metric": True,
                "is_formula": True,
                "cell_ref": "BS!B8",
            },
        ],
    )
    result = BalanceSheetModule().analyze(model)
    comparisons = extract_metric_comparisons(result.coverage)
    assert comparisons
    codes = {c.metric_code for c in comparisons}
    assert "CURRENT_RATIO" in codes
    assert "DEBT_TO_EBITDA" in codes


def test_engine_integration() -> None:
    model = _build(
        current_assets={p: 180.0 for p in PERIODS},
        current_liabilities={p: 70.0 for p in PERIODS},
        cash={p: 90.0 for p in PERIODS},
        total_debt={p: 110.0 for p in PERIODS},
        equity={p: 450.0 for p in PERIODS},
        ebitda={p: 85.0 for p in PERIODS},
        interest_expense={p: 5.0 for p in PERIODS},
        operating_income={p: 65.0 for p in PERIODS},
    )
    engine_result = AnalysisEngine(modules=[BalanceSheetModule()]).run(model)
    bs = engine_result.modules[0]
    assert bs.module_name == "balance_sheet"
    assert bs.score is not None
    assert len(engine_result.metric_comparisons) >= 1


def test_skipped_without_inputs() -> None:
    model = build_company_financial_model(
        analysis_id="empty-bs",
        ticker="NONE",
        workbook_cells=[],
    )
    result = BalanceSheetModule().analyze(model)
    assert result.status == "skipped"


def test_rules_evaluator_unit() -> None:
    hits = evaluate_balance_sheet_rules(
        BalanceSheetRuleInputs(
            current_ratio=0.8,
            debt_to_ebitda=5.0,
            interest_coverage=1.2,
            net_debt=500.0,
            balance_sheet_point_count=5,
            material_debt=True,
            interest_expense_available=True,
            period="FY2024",
        )
    )
    ids = {h.rule.rule_id for h in hits}
    assert "BS002" in ids
    assert "BS003" in ids
    assert "BS018" in ids
