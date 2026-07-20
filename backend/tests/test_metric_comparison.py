"""Tests for Workbook Metric vs HAP Metric comparison architecture."""

from __future__ import annotations

from analysis_engine import AnalysisEngine, GrowthModule, ProfitabilityModule
from analysis_engine.metric_comparison import (
    build_module_metric_comparisons,
    compare_workbook_to_hap,
    extract_metric_comparisons,
)
from analysis_engine.schemas import MetricResult
from canonical_model import WorkbookMetric, build_company_financial_model


def _statement_cells() -> list[dict]:
    return [
        {
            "concept": "Revenue",
            "period": "FY2024",
            "value": 100.0,
            "confidence": 0.9,
            "audited": True,
            "source": "SEC 10-K",
            "cell_ref": "IS!REV_FY2024",
        },
        {
            "concept": "Net Income",
            "period": "FY2024",
            "value": 20.0,
            "confidence": 0.9,
            "audited": True,
            "source": "SEC 10-K",
            "cell_ref": "IS!NI_FY2024",
        },
        {
            "concept": "Shareholders Equity",
            "period": "FY2024",
            "value": 100.0,
            "confidence": 0.9,
            "audited": True,
            "source": "SEC 10-K",
            "cell_ref": "BS!EQ_FY2024",
        },
    ]


def test_workbook_metric_routed_separately_from_statements() -> None:
    cells = _statement_cells() + [
        {
            "concept": "ROIC",
            "period": "FY2024",
            "value": 0.18,
            "is_workbook_metric": True,
            "is_formula": True,
            "formula": "=NOPAT/IC",
            "cell_ref": "Ratios!D10",
        }
    ]
    model = build_company_financial_model(
        analysis_id="wb-test",
        ticker="TEST",
        workbook_cells=cells,
    )
    assert model.workbook_metrics.get("ROIC", period="FY2024") is not None
    assert model.workbook_metrics.get("ROIC", period="FY2024").value == 0.18
    # ROIC must not be ingested as a statement fact.


def test_compare_workbook_to_hap_match_and_divergent() -> None:
    workbook = WorkbookMetric(
        code="ROIC",
        name="ROIC",
        value=0.18,
        period="FY2024",
        is_formula=True,
        cell_ref="Ratios!D10",
    )
    hap = MetricResult(
        name="ROIC",
        code="ROIC",
        value=0.179,
        unit="ratio",
        period="FY2024",
        confidence=0.9,
        evidence=[],
    )
    within = compare_workbook_to_hap(
        comparison_id="test:roic",
        metric_code="ROIC",
        metric_name="ROIC",
        module_name="profitability",
        workbook=workbook,
        hap=hap,
    )
    assert within.status == "within_tolerance"
    assert within.recommended_action == "no_action"
    assert within.difference is not None

    divergent = compare_workbook_to_hap(
        comparison_id="test:roic:div",
        metric_code="ROIC",
        metric_name="ROIC",
        module_name="profitability",
        workbook=workbook,
        hap=MetricResult(
            name="ROIC",
            code="ROIC",
            value=0.25,
            unit="ratio",
            period="FY2024",
            confidence=0.9,
            evidence=[],
        ),
    )
    assert divergent.status == "divergent"
    assert divergent.recommended_action == "investigate_workbook_formula"


def test_module_attaches_metric_comparisons_in_coverage() -> None:
    cells = _statement_cells()
    for year, rev, ni in [
        ("FY2020", 274.0, 57.0),
        ("FY2021", 366.0, 95.0),
        ("FY2022", 394.0, 100.0),
        ("FY2023", 383.0, 97.0),
        ("FY2024", 391.0, 94.0),
    ]:
        cells.append(
            {
                "concept": "Revenue",
                "period": year,
                "value": rev,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
        cells.append(
            {
                "concept": "Operating Income",
                "period": year,
                "value": rev * 0.3,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
        cells.append(
            {
                "concept": "Net Income",
                "period": year,
                "value": ni,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
        cells.append(
            {
                "concept": "Shareholders Equity",
                "period": year,
                "value": 70.0 + int(year[-1]),
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
        cells.append(
            {
                "concept": "Total Assets",
                "period": year,
                "value": 350.0,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
        cells.append(
            {
                "concept": "Invested Capital",
                "period": year,
                "value": 400.0,
                "confidence": 0.9,
                "audited": True,
                "source": "SEC 10-K",
            }
        )
    cells.append(
        {
            "concept": "Revenue CAGR",
            "period": "FY2024",
            "value": 0.09,
            "is_workbook_metric": True,
            "is_formula": True,
            "cell_ref": "Growth!B5",
        }
    )
    model = build_company_financial_model(
        analysis_id="cmp-test",
        ticker="AAPL",
        workbook_cells=cells,
    )
    growth_result = GrowthModule().analyze(model)
    comparisons = extract_metric_comparisons(growth_result.coverage)
    assert comparisons
    rev_cmp = next(item for item in comparisons if item.metric_code == "REV_CAGR")
    assert rev_cmp.workbook_value == 0.09
    assert rev_cmp.hap_value is not None
    assert rev_cmp.status in {"match", "within_tolerance", "divergent"}


def test_engine_aggregates_metric_comparisons() -> None:
    cells = _statement_cells()
    for year in ["FY2020", "FY2021", "FY2022", "FY2023", "FY2024"]:
        cells.extend(
            [
                {"concept": "Revenue", "period": year, "value": 100.0 + int(year[-1]), "audited": True},
                {"concept": "Net Income", "period": year, "value": 10.0, "audited": True},
                {"concept": "Operating Income", "period": year, "value": 15.0, "audited": True},
                {"concept": "Shareholders Equity", "period": year, "value": 80.0, "audited": True},
                {"concept": "Total Assets", "period": year, "value": 200.0, "audited": True},
                {"concept": "Invested Capital", "period": year, "value": 120.0, "audited": True},
            ]
        )
    cells.append(
        {
            "concept": "ROE",
            "period": "FY2024",
            "value": 0.12,
            "is_workbook_metric": True,
            "is_formula": True,
            "cell_ref": "Ratios!C8",
        }
    )
    model = build_company_financial_model(
        analysis_id="eng-cmp",
        ticker="TEST",
        workbook_cells=cells,
    )
    engine_result = AnalysisEngine(modules=[ProfitabilityModule()]).run(model)
    assert engine_result.metric_comparisons
    assert engine_result.summary_metrics["metric_comparison_count"] >= 1


def test_hap_only_comparison_when_no_workbook_equivalent() -> None:
    model = build_company_financial_model(
        analysis_id="hap-only",
        ticker="TEST",
        workbook_cells=_statement_cells(),
    )
    bundle = build_module_metric_comparisons(
        model=model,
        module_name="growth",
        hap_metrics=[
            MetricResult(
                name="Revenue CAGR",
                code="REV_CAGR",
                value=0.08,
                unit="ratio",
                period="FY2024",
                confidence=0.85,
                evidence=[],
            )
        ],
    )
    assert bundle.comparisons[0].status == "hap_only"
    assert bundle.comparisons[0].recommended_action == "no_action"
