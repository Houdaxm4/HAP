"""Tests for scoring engine, rule library, and profitability module contract."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, ProfitabilityModule
from canonical_model import CompanyFinancialModel, build_company_financial_model
from rule_library import evaluate_profitability_rules
from scoring_engine import PROFITABILITY_WEIGHTS, score_profitability
from scoring_engine.components import score_roic
from scoring_engine.profitability import ProfitabilityScoreInputs


def _sample_cells() -> list[dict]:
    cells: list[dict] = []
    revenue = {
        "FY2020": 274_515_000_000,
        "FY2021": 365_817_000_000,
        "FY2022": 394_328_000_000,
        "FY2023": 383_285_000_000,
        "FY2024": 391_035_000_000,
    }
    net_income = {
        "FY2020": 57_411_000_000,
        "FY2021": 94_680_000_000,
        "FY2022": 99_803_000_000,
        "FY2023": 96_995_000_000,
        "FY2024": 93_736_000_000,
    }
    operating_income = {
        "FY2020": 66_288_000_000,
        "FY2021": 108_949_000_000,
        "FY2022": 119_437_000_000,
        "FY2023": 114_301_000_000,
        "FY2024": 123_216_000_000,
    }
    equity = {
        "FY2020": 65_339_000_000,
        "FY2021": 63_090_000_000,
        "FY2022": 50_672_000_000,
        "FY2023": 62_146_000_000,
        "FY2024": 74_000_000_000,
    }
    assets = {
        "FY2020": 323_888_000_000,
        "FY2021": 351_002_000_000,
        "FY2022": 352_755_000_000,
        "FY2023": 352_583_000_000,
        "FY2024": 364_980_000_000,
    }
    invested = {
        "FY2020": 400_000_000_000,
        "FY2021": 420_000_000_000,
        "FY2022": 450_000_000_000,
        "FY2023": 480_000_000_000,
        "FY2024": 500_000_000_000,
    }
    tax = {
        "FY2020": 9_680_000_000,
        "FY2021": 14_527_000_000,
        "FY2022": 19_300_000_000,
        "FY2023": 16_750_000_000,
        "FY2024": 24_000_000_000,
    }
    ocf = {
        "FY2020": 80_674_000_000,
        "FY2021": 104_038_000_000,
        "FY2022": 122_151_000_000,
        "FY2023": 110_543_000_000,
        "FY2024": 118_254_000_000,
    }
    fcf = {
        "FY2020": 73_365_000_000,
        "FY2021": 92_953_000_000,
        "FY2022": 111_443_000_000,
        "FY2023": 99_584_000_000,
        "FY2024": 108_807_000_000,
    }
    current_assets = {
        "FY2020": 143_713_000_000,
        "FY2021": 162_209_000_000,
        "FY2022": 176_164_000_000,
        "FY2023": 143_566_000_000,
        "FY2024": 152_987_000_000,
    }
    current_liabilities = {
        "FY2020": 105_392_000_000,
        "FY2021": 125_481_000_000,
        "FY2022": 153_982_000_000,
        "FY2023": 133_973_000_000,
        "FY2024": 141_112_000_000,
    }
    cash = {
        "FY2020": 38_016_000_000,
        "FY2021": 34_940_000_000,
        "FY2022": 23_646_000_000,
        "FY2023": 29_965_000_000,
        "FY2024": 29_943_000_000,
    }
    total_debt = {
        "FY2020": 112_436_000_000,
        "FY2021": 124_719_000_000,
        "FY2022": 120_069_000_000,
        "FY2023": 111_088_000_000,
        "FY2024": 106_629_000_000,
    }

    def add(concept: str, series: dict[str, float], prefix: str) -> None:
        for period, value in series.items():
            cells.append(
                {
                    "concept": concept,
                    "period": period,
                    "value": value,
                    "confidence": 0.9,
                    "audited": True,
                    "source": "SEC 10-K",
                    "filing_type": "10-K",
                    "cell_ref": f"{prefix}_{period}",
                }
            )

    add("Revenue", revenue, "REV")
    add("Net Income", net_income, "NI")
    add("Operating Income", operating_income, "OI")
    add("Shareholders Equity", equity, "EQ")
    add("Total Assets", assets, "TA")
    add("Invested Capital", invested, "IC")
    add("Tax Expense", tax, "TAX")
    add("Operating Cash Flow", ocf, "OCF")
    add("Free Cash Flow", fcf, "FCF")
    add("Current Assets", current_assets, "CA")
    add("Current Liabilities", current_liabilities, "CL")
    add("Cash", cash, "CASH")
    add("Total Debt", total_debt, "DEBT")
    dividends = {
        "FY2020": -14_081_000_000,
        "FY2021": -14_467_000_000,
        "FY2022": -14_841_000_000,
        "FY2023": -15_025_000_000,
        "FY2024": -15_234_000_000,
    }
    buybacks = {
        "FY2020": -72_516_000_000,
        "FY2021": -85_971_000_000,
        "FY2022": -89_402_000_000,
        "FY2023": -77_550_000_000,
        "FY2024": -94_949_000_000,
    }
    add("Dividends Paid", dividends, "DIV")
    add("Share Repurchases", buybacks, "BB")
    cells.append({"concept": "WACC", "period": "FY2024", "value": 0.09, "cell_ref": "WACC"})
    return cells


def test_profitability_weights_match_scoring_system() -> None:
    assert PROFITABILITY_WEIGHTS["ROIC"] == 0.40
    assert PROFITABILITY_WEIGHTS["OPERATING_MARGIN"] == 0.20
    assert PROFITABILITY_WEIGHTS["NET_MARGIN"] == 0.15
    assert PROFITABILITY_WEIGHTS["ROE"] == 0.10
    assert PROFITABILITY_WEIGHTS["ROA"] == 0.05
    assert PROFITABILITY_WEIGHTS["MARGIN_STABILITY"] == 0.10
    assert abs(sum(PROFITABILITY_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_roic_caps_below_wacc() -> None:
    assert score_roic(0.08, wacc=0.09) <= 39.0
    assert score_roic(0.22) >= 95.0


def test_score_profitability_deterministic() -> None:
    first = score_profitability(
        ProfitabilityScoreInputs(
            roic=0.18,
            operating_margin=0.30,
            net_margin=0.24,
            roe=0.25,
            roa=0.25,
            margin_stability=0.9,
            wacc=0.09,
        )
    )
    second = score_profitability(
        ProfitabilityScoreInputs(
            roic=0.18,
            operating_margin=0.30,
            net_margin=0.24,
            roe=0.25,
            roa=0.25,
            margin_stability=0.9,
            wacc=0.09,
        )
    )
    assert first.score == second.score
    assert first.score is not None
    assert 80 <= first.score <= 100


def test_pr_rules_trigger_expected_findings() -> None:
    hits = evaluate_profitability_rules(
        roic=0.22,
        roe=0.25,
        roa_series=None,
        roic_series=None,
        operating_margin_series=None,
        net_margin_series=None,
        wacc=0.09,
        period="FY2024",
    )
    rule_ids = {hit.rule.rule_id for hit in hits}
    assert "PR001" in rule_ids
    assert "PR009" in rule_ids
    for hit in hits:
        finding = hit.to_finding()
        assert finding.evidence
        assert finding.rule_id is not None


def test_profitability_module_emits_spec_contract() -> None:
    model = build_company_financial_model(
        analysis_id="a1",
        ticker="AAPL",
        workbook_cells=_sample_cells(),
        valuation_inputs={"wacc": 0.09},
    )
    result = ProfitabilityModule().analyze(model)

    assert result.module_name == "profitability"
    assert result.status == "ok"
    assert result.score is not None
    assert 0 <= result.score <= 100
    assert 0 <= result.confidence <= 1
    assert result.metrics
    assert result.findings
    assert result.component_scores
    assert {c.code for c in result.component_scores} >= {
        "ROIC",
        "OPERATING_MARGIN",
        "NET_MARGIN",
        "ROE",
        "ROA",
        "MARGIN_STABILITY",
    }
    dumped = result.model_dump()
    for key in (
        "module_name",
        "score",
        "confidence",
        "metrics",
        "findings",
        "risks",
        "opportunities",
        "evidence",
        "analyst_adjustments",
        "status",
    ):
        assert key in dumped
    assert "report" not in dumped
    assert "narrative" not in dumped
    for finding in result.findings:
        assert finding.evidence


def test_engine_runs_scored_profitability() -> None:
    model = build_company_financial_model(
        analysis_id="a1",
        ticker="AAPL",
        workbook_cells=_sample_cells(),
        valuation_inputs={"wacc": 0.09},
    )
    engine_result = AnalysisEngine().run(model)
    profitability = next(m for m in engine_result.modules if m.module_name == "profitability")
    growth = next(m for m in engine_result.modules if m.module_name == "growth")
    assert profitability.score is not None
    assert growth.score is not None
    cash_flow = next(m for m in engine_result.modules if m.module_name == "cash_flow")
    assert cash_flow.score is not None
    balance_sheet = next(m for m in engine_result.modules if m.module_name == "balance_sheet")
    assert balance_sheet.score is not None
    capital_allocation = next(
        m for m in engine_result.modules if m.module_name == "capital_allocation"
    )
    assert capital_allocation.score is not None
    assert engine_result.summary_metrics["scored_module_count"] == 5


def test_profitability_skips_without_inputs() -> None:
    model = CompanyFinancialModel(analysis_id="a2", ticker="TEST")
    result = ProfitabilityModule().analyze(model)
    assert result.status == "skipped"
    assert result.score is None
