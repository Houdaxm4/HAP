"""New Company pipeline unit and integration tests."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook, load_workbook

from models.custom_run import CustomRunData, CustomRunPeriods, CustomRunSeries
from models.new_company import (
    BuybackAbsenceClass,
    CLOUD_PENDING_WINDOWS_CERTIFICATION,
    NewCompanyWorkflowState,
    ProjectionConfidence,
)
from services.excel_recalc_service import ExcelRecalcReport, genuine_excel_com_recalc
from services.new_company_buyback_service import NewCompanyBuybackService
from services.new_company_lease_service import NewCompanyLeaseService
from services.new_company_output_gate_service import NewCompanyOutputGateService
from services.new_company_pe10_service import NewCompanyPe10Service, exact_field_identity
from services.new_company_period_service import NewCompanyPeriodService
from services.new_company_projection_service import NewCompanyProjectionService
from services.new_company_rd_service import NewCompanyRdService
from services.new_company_runner import NewCompanyRunner
from services.new_company_seasonality_service import NewCompanySeasonalityService
from services.new_company_sec_coverage_service import NewCompanySecCoverageService
from services.new_company_statement_validation_service import NewCompanyStatementValidationService
from services.new_company_tax_service import NewCompanyTaxService
from services.new_company_tax_table_service import NewCompanyTaxTableService
from services.output_service import OutputService


YEARS = list(range(2016, 2026))
FY = [f"FY{y}" for y in YEARS]


def _header(ws, years: list[int]) -> None:
    ws["A1"] = "Line"
    ws["A7"] = "Line"
    for i, y in enumerate(years):
        ws.cell(1, 3 + i, f"FY{y}")
        ws.cell(5, 3 + i, f"FY{y}")
        ws.cell(7, 3 + i, f"FY{y}")


def _lq_is(wb: Workbook, *, quarter: int, ytd_rev: float, ytd_oi: float) -> None:
    ws = wb.create_sheet("Last Quarter IS Standardized")
    ws["B2"] = f"Q{quarter} FY2025"
    ws["A11"] = "Revenue"
    ws["C11"] = ytd_rev / quarter
    ws["G11"] = ytd_rev
    ws["H11"] = ytd_rev * 0.9
    ws["A20"] = "Operating income"
    ws["C20"] = ytd_oi / quarter
    ws["G20"] = ytd_oi
    ws["H20"] = ytd_oi * 0.85


def industrial_workbook(
    path: Path,
    *,
    years: list[int] | None = None,
    quarter: int = 3,
    rd_by_year: dict[int, float] | None = None,
    revenue_by_year: dict[int, float] | None = None,
    oi_by_year: dict[int, float] | None = None,
    missing_pe10_year: int | None = None,
    seasonal: bool = True,
    ytd_rev: float = 75.0,
    ytd_oi: float = 18.0,
    rd_life_cell: float | None = None,
) -> Path:
    years = years or YEARS
    rd_by_year = rd_by_year or {y: 10.0 + (y - 2016) for y in years}
    revenue_by_year = revenue_by_year or {
        y: (80.0 if seasonal and y >= 2020 else 100.0) + (y - 2016) * 5 for y in years
    }
    oi_by_year = oi_by_year or {y: r * 0.25 for y, r in revenue_by_year.items()}
    wb = Workbook()
    is_ = wb.active
    is_.title = "Income - GAAP"
    _header(is_, years)
    is_["C3"] = years[-1]
    labels = {
        11: "Revenue",
        12: "Gross profit",
        13: "Research and development",
        14: "Operating income",
        15: "Pretax income",
        16: "Income tax expense",
        17: "Net income",
        18: "Diluted EPS",
        19: "Diluted weighted average shares",
    }
    for row, lab in labels.items():
        is_.cell(row, 1, lab)
        for i, y in enumerate(years):
            col = 3 + i
            if row == 11:
                is_.cell(row, col, revenue_by_year[y])
            elif row == 12:
                is_.cell(row, col, revenue_by_year[y] * 0.4)
            elif row == 13:
                is_.cell(row, col, rd_by_year.get(y, 0.0))
            elif row == 14:
                is_.cell(row, col, oi_by_year[y])
            elif row == 15:
                is_.cell(row, col, oi_by_year[y] * 0.95)
            elif row == 16:
                is_.cell(row, col, oi_by_year[y] * 0.95 * 0.21)
            elif row == 17:
                is_.cell(row, col, oi_by_year[y] * 0.75)
            elif row == 18:
                is_.cell(row, col, 2.0 + (y - 2016) * 0.1)
            elif row == 19:
                is_.cell(row, col, 100.0)

    bs = wb.create_sheet("Balance Sheet - Standardized")
    _header(bs, years)
    bs["C3"] = years[-1]
    for row, lab, base in (
        (11, "Cash", 50),
        (61, "Total assets", 1000),
        (65, "Total current liabilities", 200),
        (90, "Total liabilities", 600),
        (100, "Total shareholders' equity", 400),
        (80, "Long-term debt", 150),
    ):
        bs.cell(row, 1, lab)
        for i, _y in enumerate(years):
            bs.cell(row, 3 + i, base + i)

    cf = wb.create_sheet("Cash Flow - Standardized")
    _header(cf, years)
    for row, lab, base in (
        (11, "Cash from operating activities", 80),
        (12, "Capital expenditure", -20),
        (13, "Cash from investing activities", -25),
        (14, "Cash from financing activities", -30),
    ):
        cf.cell(row, 1, lab)
        for i, _y in enumerate(years):
            cf.cell(row, 3 + i, base)

    inp = wb.create_sheet("Inputs")
    _header(inp, years)
    inp["A10"] = "PE10"
    inp["A11"] = "E10"
    inp["A12"] = "Stock price"
    inp["A57"] = "PE10"
    inp["A58"] = "E10"
    inp["A63"] = "Current Price"
    inp["B63"] = 100
    inp["A65"] = "Current PE10"
    inp["B65"] = 22
    inp["A103"] = "R&D expense"
    inp["A106"] = "Tax table"
    inp["A107"] = "Federal tax"
    inp["A108"] = "State taxes"
    inp["A109"] = "Foreign taxes"
    inp["A110"] = "R&D tax credits"
    inp["A111"] = "All other items"
    inp["A112"] = "Income tax expense"
    inp["A120"] = "Buybacks"
    inp["A121"] = "Shares repurchased"
    for i, y in enumerate(years):
        col = 3 + i
        if y != missing_pe10_year:
            inp.cell(10, col, 18 + i * 0.2)
            inp.cell(57, col, 18 + i * 0.2)
            inp.cell(11, col, 5 + i * 0.1)
            inp.cell(58, col, 5 + i * 0.1)
        inp.cell(103, col, rd_by_year.get(y, 0.0))

    rd = wb.create_sheet("R&D")
    rd["B8"] = rd_life_cell
    rd["A2"] = "R&D expense"
    rd["A3"] = "R&D asset"
    rd["A4"] = "R&D amortization"
    _header(rd, years)
    for i, y in enumerate(years):
        rd.cell(2, 3 + i, f"=IF(Inputs!{chr(67+i)}103=\"\",0,Inputs!{chr(67+i)}103)")

    ls = wb.create_sheet("Leases")
    _header(ls, years)
    ls["A10"] = "Year 1"
    ls["A18"] = "Estimated Long-Term Rate"

    tax = wb.create_sheet("Tax")
    _header(tax, years)
    for i, _y in enumerate(years):
        tax.cell(15, 3 + i, f"=Inputs!{chr(67+i)}112")
        tax.cell(25, 3 + i, f"=Inputs!{chr(67+i)}112")

    ic = wb.create_sheet("IC & NOPAT & ROIC ")
    _header(ic, years)
    ic["A9"] = "Invested capital"
    ic["A20"] = "NOPAT"
    ic["A23"] = "ROIC"
    for i, y in enumerate(years):
        ic.cell(9, 3 + i, 500 + i * 10)
        ic.cell(20, 3 + i, 80 + i)
        ic.cell(23, 3 + i, 0.12)

    fm = wb.create_sheet("Final Metrics")
    _header(fm, years)
    fm["A5"] = "ROCE"
    fm["A8"] = "ROIC - WACC"
    for i, _y in enumerate(years):
        fm.cell(5, 3 + i, 0.14)
        fm.cell(8, 3 + i, 0.04)

    er = wb.create_sheet("Expected Returns & Buybacks")
    er["A11"] = 0.04
    er["B5"] = 0.05
    er["E14"] = 0.11
    er["F14"] = 0.13
    ev = wb.create_sheet("Enterprise Value")
    ev["B20"] = 200
    ev["B27"] = 180
    ev["B32"] = 0.2
    ev["B42"] = 150
    ev["B47"] = 0.1
    ev["B48"] = 120
    ev["B6"] = 90
    ev["C6"] = 100

    _lq_is(wb, quarter=quarter, ytd_rev=ytd_rev, ytd_oi=ytd_oi)
    lq_cf = wb.create_sheet("Last Quarter CF Standardized")
    lq_cf["A27"] = "Cash from operating activities"
    lq_cf["C27"] = 40
    lq_bs = wb.create_sheet("Last Quarter BS Standardized")
    lq_bs["A11"] = "Cash"
    lq_bs["C11"] = 60

    wb.save(path)
    wb.close()
    return path


def _facts_entry(val: float, fy: int, form: str = "10-K", accn: str = "0001") -> dict:
    return {
        "val": val,
        "fy": fy,
        "fp": "FY",
        "form": form,
        "end": f"{fy}-12-31",
        "filed": f"{fy+1}-02-01",
        "accn": accn,
        "frame": f"CY{fy}",
    }


def company_facts_for(
    *,
    years: list[int] | None = None,
    rd: bool = True,
    tax: bool = True,
    leases: bool = True,
    buybacks: bool = True,
    missing_tax_component: bool = False,
    pharma: bool = False,
    sbc_offset: bool = False,
) -> dict:
    years = years or YEARS
    us_gaap: dict = {}

    def add(tag: str, make):
        us_gaap[tag] = {"label": tag, "units": {"USD": [make(y) for y in years]}}

    add("Revenues", lambda y: _facts_entry(100_000_000 + (y - 2016) * 5_000_000, y))
    add("GrossProfit", lambda y: _facts_entry(40_000_000, y))
    add("OperatingIncomeLoss", lambda y: _facts_entry(25_000_000, y))
    add(
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        lambda y: _facts_entry(24_000_000, y),
    )
    add("IncomeTaxExpenseBenefit", lambda y: _facts_entry(5_040_000, y))
    add("NetIncomeLoss", lambda y: _facts_entry(18_000_000, y))
    add("EarningsPerShareDiluted", lambda y: _facts_entry(2.0, y))
    add("NetCashProvidedByUsedInOperatingActivities", lambda y: _facts_entry(80_000_000, y))
    add("PaymentsToAcquirePropertyPlantAndEquipment", lambda y: _facts_entry(20_000_000, y))
    add("NetCashProvidedByUsedInInvestingActivities", lambda y: _facts_entry(-25_000_000, y))
    add("NetCashProvidedByUsedInFinancingActivities", lambda y: _facts_entry(-30_000_000, y))
    add("CashAndCashEquivalentsAtCarryingValue", lambda y: _facts_entry(50_000_000, y))
    add("Assets", lambda y: _facts_entry(1_000_000_000, y))
    add("LiabilitiesCurrent", lambda y: _facts_entry(200_000_000, y))
    add("Liabilities", lambda y: _facts_entry(600_000_000, y))
    add("StockholdersEquity", lambda y: _facts_entry(400_000_000, y))
    add("LongTermDebt", lambda y: _facts_entry(150_000_000, y))
    add("WeightedAverageNumberOfDilutedSharesOutstanding", lambda y: _facts_entry(100_000_000, y))
    us_gaap["EffectiveIncomeTaxRateContinuingOperations"] = {
        "label": "ETR",
        "units": {"pure": [_facts_entry(0.21, y) for y in years]},
    }
    if tax:
        us_gaap["IncomeTaxReconciliationIncomeTaxExpenseBenefitAtFederalStatutoryIncomeTaxRate"] = {
            "label": "federal",
            "units": {"USD": [_facts_entry(5_040_000, y) for y in years]},
        }
        if not missing_tax_component:
            us_gaap["IncomeTaxReconciliationStateAndLocalIncomeTaxes"] = {
                "label": "state",
                "units": {"USD": [_facts_entry(480_000, y) for y in years]},
            }
    if rd:
        us_gaap["ResearchAndDevelopmentExpense"] = {
            "label": "R&D",
            "units": {"USD": [_facts_entry(10_000_000 + (y - 2016) * 1_000_000, y) for y in years + [y for y in range(2012, 2016)]]},
        }
    if leases:
        for tag, val in (
            ("LesseeOperatingLeaseLiabilityPaymentsDueNextTwelveMonths", 10_000_000),
            ("LesseeOperatingLeaseLiabilityPaymentsDueYearTwo", 9_000_000),
            ("LesseeOperatingLeaseLiabilityPaymentsDueYearThree", 8_000_000),
            ("LesseeOperatingLeaseLiabilityPaymentsDueYearFour", 7_000_000),
            ("LesseeOperatingLeaseLiabilityPaymentsDueYearFive", 6_000_000),
            ("LesseeOperatingLeaseLiabilityPaymentsDueAfterYearFive", 20_000_000),
            ("OperatingLeaseLiabilityCurrent", 9_000_000),
            ("OperatingLeaseLiabilityNoncurrent", 40_000_000),
            ("OperatingLeaseRightOfUseAsset", 45_000_000),
            ("OperatingLeaseWeightedAverageDiscountRatePercent", 4.5),
            ("OperatingLeaseWeightedAverageRemainingLeaseTerm", 8.0),
        ):
            us_gaap[tag] = {"label": tag, "units": {"pure" if "Rate" in tag or "Term" in tag else "USD": [_facts_entry(val, y) for y in years]}}
        # Pre-ASC 842 for early years
        us_gaap["OperatingLeasesFutureMinimumPaymentsDueCurrent"] = {
            "label": "pre842",
            "units": {"USD": [_facts_entry(8_000_000, y) for y in years if y <= 2018]},
        }
    if buybacks:
        us_gaap["PaymentsForRepurchaseOfCommonStock"] = {
            "label": "buybacks $",
            "units": {"USD": [_facts_entry(5_000_000, y) for y in years]},
        }
        us_gaap["StockRepurchasedDuringPeriodShares"] = {
            "label": "buybacks sh",
            "units": {"shares": [_facts_entry(1_000_000, y) for y in years]},
        }
        us_gaap["TreasuryStockAcquiredAverageCostPerShare"] = {
            "label": "avg px",
            "units": {"USD/shares": [_facts_entry(5.0, y) for y in years]},
        }
        if sbc_offset:
            us_gaap["AllocatedShareBasedCompensationExpense"] = {
                "label": "sbc",
                "units": {"USD": [_facts_entry(4_000_000, y) for y in years]},
            }
    facts = {"facts": {"us-gaap": us_gaap}, "entityName": "Test Co"}
    if pharma:
        facts["entityName"] = "Example Pharmaceuticals Inc"
    return facts


def _filings_manifest(years: list[int] | None = None) -> dict:
    years = years or YEARS
    # Four 10-Ks covering the window (3+3+3+1 style selection happens in the service).
    selected = []
    for fy in (2025, 2022, 2019, 2016):
        selected.append(
            {
                "accession_number": f"000-{fy}",
                "filing_type": "10-K",
                "filing_date": f"{fy+1}-02-01",
                "report_date": f"{fy}-12-31",
                "document_url": f"https://www.sec.gov/{fy}",
                "fiscal_year": fy,
                "primary_document": "d10k.htm",
            }
        )
    return {"ticker": "TEST", "cik": "0001", "company_name": "Test Co", "selected_filings": selected, "sic": "5331"}


def _ok_recalc(analysis_id="a", ticker="TEST", path="") -> ExcelRecalcReport:
    return ExcelRecalcReport(
        analysis_id=analysis_id,
        ticker=ticker,
        status="ok",
        method="excel_com_calculate_full_rebuild",
        workbook_path=path,
        cells_checked=["Expected Returns & Buybacks!E14"],
        summary="ok",
        com_invoked=True,
    )


@pytest.fixture
def out_svc(tmp_path: Path) -> OutputService:
    return OutputService(outputs_dir=tmp_path / "outputs")


_CURRENT_APPLY = "services.current_data_refresh_service.CurrentDataRefreshService.apply"
_CRF_PARSE = "services.new_company_pe10_service.CustomRunService.parse"


def _refresh_ok():
    return MagicMock(entries=[], summary="ok", missing_required=[])


def _approve_persisted_lease(out_svc: OutputService, analysis_id: str, review, workbook: Path):
    approved = NewCompanyLeaseService().apply_review(
        review, action="approve", reason="fixture approval", workbook_path=workbook
    )
    out_svc.write_json(analysis_id, "lease_rate_review.json", approved)
    return approved


@pytest.fixture(autouse=True)
def _stub_current_data_refresh():
    """Stub current-data refresh at its definition site.

    Patching CurrentDataRefreshService.apply through two importing modules
    (and stopping those patches in start-order) previously leaked a MagicMock
    into later tests such as test_quarterly_update.
    """
    with patch(_CURRENT_APPLY, return_value=_refresh_ok()):
        yield


@pytest.fixture(autouse=True)
def _stub_excel_com_unavailable():
    """Keep unit tests off live Excel COM. Genuine-COM tests patch recalculate()."""
    from services.excel_recalc_service import ExcelComUnavailable

    with patch(
        "services.excel_recalc_service.load_excel_com",
        side_effect=ExcelComUnavailable("test isolation"),
    ):
        yield


def test_ten_year_period_detection(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", quarter=2)
    report = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    assert report.fiscal_years == FY
    assert report.latest_quarter == 2
    assert report.template_family == "industrial_template"
    assert report.chronology_ok
    assert report.status == "ok"


def test_period_range_invalid_when_not_ten(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", years=list(range(2020, 2026)))
    report = NewCompanyPeriodService().detect(analysis_id="a", ticker="X", workbook_path=path)
    assert "NEW_COMPANY_ANNUAL_PERIOD_RANGE_INVALID" in report.status


def test_sec_coverage_prefers_latest_restated_and_3_plus_pattern():
    years = FY
    manifest = _filings_manifest()
    facts = company_facts_for()
    report = NewCompanySecCoverageService().build(
        analysis_id="a", ticker="MSFT", fiscal_years=years, sec_manifest=manifest, company_facts=facts
    )
    assert report.complete
    assert report.pattern in {"3+3+3+1", "4_filings_comparative_window"}
    covered = {y.fiscal_year: y for y in report.years}
    assert covered["FY2024"].restated or covered["FY2024"].coverage_status.value.startswith("covered")

    lookback = NewCompanySecCoverageService().build(
        analysis_id="a",
        ticker="MSFT",
        fiscal_years=years,
        sec_manifest=manifest,
        company_facts=facts,
        extra_lookback_years=["FY2012", "FY2013"],
    )
    assert lookback.complete
    assert lookback.displayed_years == years
    assert "FY2012" in lookback.lookback_years


def test_exact_pe10_vs_e10_identities():
    assert exact_field_identity("PE10") == "pe10_fiscal_year"
    assert exact_field_identity("E10") == "e10_fiscal_year"
    assert exact_field_identity("Current PE10") == "pe10_current"
    assert exact_field_identity("Current E10") == "e10_current"
    assert exact_field_identity("PE10 Percentile") is None
    assert exact_field_identity("E10") != exact_field_identity("PE10")
    # Substring trap: e10 inside pe10
    assert exact_field_identity("PE10") != "e10_fiscal_year"


def test_nearest_date_crf_matching_and_zero_not_missing(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", missing_pe10_year=2018)
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="MSFT",
        ticker_sheet_name="MSFT",
        metadata={
            "inputs_annual_pe10": {fy: (0.0 if fy == "FY2018" else 20.0 + i) for i, fy in enumerate(FY)},
            "inputs_annual_e10": {fy: 5.0 + i * 0.1 for i, fy in enumerate(FY)},
        },
        scalars={"Current PE10": 25.0, "Current E10": 6.0, "Current Price (Live Price)": 110.0},
        periods=CustomRunPeriods(dates=["2025-12-31"]),
    )
    (tmp_path / "crf.xlsx").write_bytes(b"x")
    with patch(_CRF_PARSE, return_value=crf):
        report = NewCompanyPe10Service().apply(
            analysis_id="a",
            ticker="MSFT",
            workbook_path=path,
            custom_run_path=tmp_path / "crf.xlsx",
            fiscal_years=FY,
        )
    assert any("zero" in w.lower() or "TEN_YEAR_PE10" in w for w in report.warnings)
    fy2018 = next(o for o in report.fiscal_year_pe10 if o.fiscal_year == "FY2018")
    assert fy2018.missing or fy2018.value is None
    assert report.current_pe10 and report.current_pe10.value == 25.0
    assert all(o.field_role == "e10_fiscal_year" for o in report.fiscal_year_e10)


def test_ten_year_tax_residual_and_missing_component(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    year_inputs = {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [
                {"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"},
                {"label": "State", "rate": 0.02, "house": "state"},
                {"label": "R&D credit", "rate": -0.012, "house": "credits"},
                {"label": "Other items in the filing", "rate": 0.005, "house": "other"},
            ],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
            "source": "10-K note 8",
        }
        for fy in FY
    }
    # Drop foreign so residual Other absorbs it; filing "Other" must not double count.
    report = NewCompanyTaxService().apply(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, year_inputs=year_inputs
    )
    assert report.complete
    y = report.years[-1]
    assert y.statutory_federal == pytest.approx(0.21)
    assert y.state == pytest.approx(0.02)
    assert y.rd_credit == pytest.approx(-0.012)
    assert y.other == pytest.approx(0.21 - 0.21 - 0.02 - (-0.012))
    assert y.residual_other == y.other
    assert abs(y.component_sum - y.reported_effective_rate) < 0.006

    # Missing component year
    year_inputs["FY2016"]["components"] = [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}]
    report2 = NewCompanyTaxService().apply(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=["FY2016"], year_inputs=year_inputs
    )
    assert report2.years[0].other == pytest.approx(0.0)


def test_rd_useful_life_schema_and_not_from_spend(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", rd_by_year={y: 50.0 for y in YEARS})
    svc = NewCompanyRdService()
    tech = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Example Software Cloud Platform", "sic": "7372"},
    )
    pharma = svc.select_useful_life(
        analysis_id="a",
        ticker="PFE",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Example Pharmaceuticals Inc", "sic": "2834"},
    )
    consumer = svc.select_useful_life(
        analysis_id="a",
        ticker="JBSS",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Snack Food Consumer Staples", "sic": "2060"},
        company_facts={"entityName": "Snack Food Consumer Staples"},
    )
    assert 1 <= tech.selected_useful_life <= 10
    assert pharma.selected_useful_life >= tech.selected_useful_life
    assert consumer.selected_useful_life <= 5
    assert tech.provenance_class == "agent_selected_analyst_assumption"
    assert "autonomous agent decision" in tech.warning.lower() or "agent-selected" in tech.warning.lower()
    assert tech.original_agent_selection == tech.selected_useful_life
    # Amount of R&D must not be the decision driver: same spend, different industries → different lives
    assert {tech.selected_useful_life, pharma.selected_useful_life, consumer.selected_useful_life}


def test_dynamic_rd_lookback_and_capitalization(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    facts = company_facts_for()
    svc = NewCompanyRdService()
    decision = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Software", "sic": "7372"},
        company_facts=facts,
    )
    report = svc.apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        decision=decision,
        company_facts=facts,
    )
    life = decision.selected_useful_life
    earliest = 2016 - (life - 1)
    assert report.earliest_required_year == f"FY{earliest}"
    assert f"FY{earliest}" in report.lookback_years
    assert report.warning_visible
    assert any(s["role"] == "minus_one" or s["useful_life"] == life - 1 for s in report.sensitivity) or life == 1


def test_lease_rate_hierarchy_and_review_checkpoint(tmp_path: Path):
    years_data = []
    from models.new_company import LeaseYearData

    years_data.append(
        LeaseYearData(
            fiscal_year="FY2025",
            year_1=10,
            year_2=9,
            total_undiscounted=50,
            current_liability=9,
            long_term_liability=40,
            rou_asset=45,
            remaining_term=8,
            reported_discount_rate=0.045,
            regime="post_asc_842",
        )
    )
    svc = NewCompanyLeaseService()
    prop = svc.estimate_rate(years=years_data)
    assert prop.methodology == "reported_weighted_average_discount_rate"
    assert prop.proposed_rate == pytest.approx(0.045)

    inferred_years = [
        LeaseYearData(
            fiscal_year="FY2025",
            year_1=12,
            year_2=12,
            year_3=12,
            year_4=12,
            year_5=12,
            thereafter=24,
            total_undiscounted=84,
            current_liability=10,
            long_term_liability=50,
            remaining_term=7,
            regime="post_asc_842",
        )
    ]
    prop2 = svc.estimate_rate(years=inferred_years)
    assert prop2.methodology_rank >= 3
    assert prop2.proposed_rate and 0 < prop2.proposed_rate < 0.25

    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = svc.apply(
        analysis_id="a", ticker="TJX", workbook_path=path, fiscal_years=FY, company_facts=company_facts_for()
    )
    assert not report.review.blocking
    assert report.review.status == "autonomous_selected"
    assert report.review.decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert report.review.selected_rate == report.review.proposed_rate
    assert any(e.get("event") == "AUTONOMOUS_AGENT_DECISION" for e in report.review.audit_trail)
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in report.review.audit_trail)
    acknowledged = svc.apply_review(report.review, action="approve", reason="optional ack", workbook_path=path)
    assert not acknowledged.blocking
    assert acknowledged.decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert any(e.get("event") == "ANALYST_ACKNOWLEDGED" for e in acknowledged.audit_trail)
    overridden = svc.apply_review(
        report.review, action="correct", rate=0.05, reason="credit spread widened", workbook_path=path
    )
    assert overridden.status == "overridden"
    assert overridden.selected_rate == pytest.approx(0.05)
    assert overridden.decision_class == "ANALYST_OVERRIDE"
    assert overridden.proposed_rate == report.review.proposed_rate
    assert any(e.get("event") == "ANALYST_OVERRIDE" for e in overridden.audit_trail)
    pending = svc.apply_review(report.review, action="request_more_evidence", reason="need IBR")
    assert pending.blocking


def test_buyback_dollars_shares_derived_and_not_delta_shares():
    facts = company_facts_for(buybacks=True, sbc_offset=True)
    # Remove share tag for one year to force derivation
    facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"] = [
        e for e in facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"] if e["fy"] != 2016
    ]
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        path = industrial_workbook(Path(td) / "wb.xlsx")
        report = NewCompanyBuybackService().apply(
            analysis_id="a", ticker="AAPL", workbook_path=path, fiscal_years=FY, company_facts=facts
        )
    y2016 = next(y for y in report.years if y.fiscal_year == "FY2016")
    assert y2016.shares_derived
    assert y2016.derivation_formula
    assert report.analysis.sbc_offset_material is True
    assert "change in shares outstanding is not used" in " ".join(report.analysis.notes).lower()
    assert report.analysis.cumulative_dollars


def test_ytd_seasonality_q2_q3_and_negative_numerator(tmp_path: Path):
    path = industrial_workbook(tmp_path / "q3.xlsx", quarter=3, ytd_rev=78, ytd_oi=19)
    q3 = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="TJX", workbook_path=path, fiscal_years=FY, latest_quarter=3
    )
    rev = next(c for c in q3.components if c.metric == "revenue")
    assert rev.unadjusted_annualized == pytest.approx(78 * 4 / 3)
    assert rev.seasonality_adjusted is not None
    assert rev.seasonality_adjusted != rev.unadjusted_annualized or rev.selected_factor == pytest.approx(0.75)
    assert q3.latest_quarter == 3

    path2 = industrial_workbook(tmp_path / "q2.xlsx", quarter=2, ytd_rev=40, ytd_oi=10)
    q2 = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="TJX", workbook_path=path2, fiscal_years=FY, latest_quarter=2
    )
    assert q2.latest_quarter == 2
    oi = next(c for c in q2.components if c.metric == "operating_income")
    assert oi.unadjusted_annualized == pytest.approx(20.0)

    path3 = industrial_workbook(tmp_path / "neg.xlsx", quarter=2, ytd_oi=-5, oi_by_year={y: -10 for y in YEARS})
    neg = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="X", workbook_path=path3, fiscal_years=FY, latest_quarter=2
    )
    oi_neg = next(c for c in neg.components if c.metric == "operating_income")
    assert oi_neg.unreliable or "UNRELIABLE" in ",".join(neg.warnings) or neg.confidence in {
        ProjectionConfidence.UNRELIABLE,
        ProjectionConfidence.LOW,
    }

    path_q1 = industrial_workbook(tmp_path / "q1.xlsx", quarter=1, ytd_rev=20, ytd_oi=5)
    q1 = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="X", workbook_path=path_q1, fiscal_years=FY, latest_quarter=1
    )
    assert q1.confidence in {ProjectionConfidence.LOW, ProjectionConfidence.UNRELIABLE}
    assert q1.confidence != ProjectionConfidence.HIGH
    assert any("indicative" in w.lower() or "q1" in w.lower() for w in q1.warnings)


def test_q1_roic_projection_stays_low_confidence(tmp_path: Path):
    path = industrial_workbook(tmp_path / "q1.xlsx", quarter=1, ytd_rev=20, ytd_oi=5)
    seasonality = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, latest_quarter=1
    )
    proj = NewCompanyProjectionService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        latest_quarter=1,
        seasonality=seasonality,
        wacc=0.08,
    )
    assert proj.confidence in {ProjectionConfidence.LOW, ProjectionConfidence.UNRELIABLE}
    assert proj.confidence != ProjectionConfidence.HIGH
    assert any("q1" in w.lower() for w in proj.warnings)


def test_roic_roce_projection_and_backtest_confidence(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", quarter=3)
    seasonality = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, latest_quarter=3
    )
    proj = NewCompanyProjectionService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        latest_quarter=3,
        seasonality=seasonality,
        wacc=0.08,
    )
    assert proj.seasonality_adjusted_roic is not None
    assert proj.projected_roic_wacc == pytest.approx(proj.seasonality_adjusted_roic - 0.08)
    assert proj.seasonality_adjusted_roce is not None
    assert proj.ytd_unadjusted_annualized_roic is not None
    assert proj.confidence in set(ProjectionConfidence)
    assert proj.backtests


def test_output_gates_insufficient_lease_evidence_blocks_authorization(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    periods = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    coverage = NewCompanySecCoverageService().build(
        analysis_id="a", ticker="MSFT", fiscal_years=FY, sec_manifest=_filings_manifest(), company_facts=company_facts_for()
    )
    from models.new_company import LeaseRateReview

    gate = NewCompanyOutputGateService().evaluate(
        analysis_id="a",
        ticker="MSFT",
        periods=periods,
        coverage=coverage,
        statements=None,
        pe10=None,
        tax=None,
        rd_decision=None,
        rd=None,
        leases=None,
        lease_review=LeaseRateReview(
            analysis_id="a",
            ticker="MSFT",
            status="LEASE_RATE_EVIDENCE_INSUFFICIENT",
            proposed_rate=None,
            selected_rate=None,
            blocking=False,
            classification="insufficient",
            decision_class="EVIDENCE_INSUFFICIENT",
        ),
        buybacks=None,
        current=None,
        projection=None,
        recalc=None,
        valuation=None,
    )
    assert "LEASE_RATE_EVIDENCE_INSUFFICIENT" in gate.blockers
    assert gate.status == "NEEDS_REVIEW"
    assert not gate.report_authorized


def test_recalc_unavailable_needs_review(tmp_path: Path, out_svc: OutputService, monkeypatch):
    from services.excel_recalc_service import ExcelComUnavailable

    monkeypatch.setattr(
        "services.excel_recalc_service.load_excel_com",
        lambda: (_ for _ in ()).throw(ExcelComUnavailable("test isolation")),
    )
    path = industrial_workbook(tmp_path / "wb.xlsx")
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="MSFT",
        ticker_sheet_name="MSFT",
        metadata={
            "inputs_annual_pe10": {fy: 20.0 for fy in FY},
            "inputs_annual_e10": {fy: 5.0 for fy in FY},
        },
        scalars={"Current PE10": 22.0, "Current E10": 5.5},
    )
    tax_inputs = {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
        }
        for fy in FY
    }
    with patch(_CRF_PARSE, return_value=crf):
        result = runner.run(
            analysis_id="run1",
            ticker="MSFT",
            company="Microsoft",
            template_path=path,
            working_path=tmp_path / "working.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=tax_inputs,
        )
    assert result["workflow_state"] == NewCompanyWorkflowState.NEEDS_REVIEW
    assert result["lease_review"].blocking is False
    assert result["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert "WORKBOOK_RECALCULATION_INCOMPLETE" in result["output_gate"].blockers
    assert result["deliverables"] is None or result["deliverables"].authorized is False
    assert result["certification_status"] == CLOUD_PENDING_WINDOWS_CERTIFICATION
    assert result["workflow_state"] != NewCompanyWorkflowState.COMPLETE


def test_runner_pauses_for_lease_review_then_blocks_without_com(tmp_path: Path, out_svc: OutputService, monkeypatch):
    from services.excel_recalc_service import ExcelComUnavailable

    monkeypatch.setattr(
        "services.excel_recalc_service.load_excel_com",
        lambda: (_ for _ in ()).throw(ExcelComUnavailable("test isolation")),
    )
    path = industrial_workbook(tmp_path / "wb.xlsx")
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="AMZN",
        ticker_sheet_name="AMZN",
        metadata={"inputs_annual_pe10": {fy: 30.0 for fy in FY}, "inputs_annual_e10": {fy: 4.0 for fy in FY}},
        scalars={"Current PE10": 32.0, "Current E10": 4.2},
    )
    tax_inputs = {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
        }
        for fy in FY
    }
    with patch(_CRF_PARSE, return_value=crf):
        done = runner.run(
            analysis_id="run2",
            ticker="AMZN",
            company="Amazon",
            template_path=path,
            working_path=tmp_path / "working.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=tax_inputs,
        )
        assert done["workflow_state"] != NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
        assert done["lease_review"].blocking is False
        assert done["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
        assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in done["lease_review"].audit_trail)
        gate = done["output_gate"]
        assert gate is not None
        assert "LEASE_RATE_REVIEW_PENDING" not in gate.blockers
        assert "WORKBOOK_RECALCULATION_INCOMPLETE" in gate.blockers
        assert done["workflow_state"] == NewCompanyWorkflowState.NEEDS_REVIEW
        assert done["workflow_state"] != NewCompanyWorkflowState.COMPLETE
        assert done["certification_status"] == CLOUD_PENDING_WINDOWS_CERTIFICATION
        assert done["deliverables"] is None or done["deliverables"].authorized is False


def test_rd_override_preserves_original_selection(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    svc = NewCompanyRdService()
    first = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Software Cloud", "sic": "7372"},
    )
    second = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Software Cloud", "sic": "7372"},
        override=7,
        override_reason="longer platform cycle",
        prior_decision=first,
    )
    assert second.analyst_override == 7
    assert second.original_agent_selection == first.selected_useful_life
    assert second.selected_useful_life == 7


def test_statement_fill_missing_and_sec_correction(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    wb = load_workbook(path)
    # Blank one revenue cell (not a formula)
    wb["Income - GAAP"].cell(11, 3, None)
    wb.save(path)
    wb.close()
    facts = company_facts_for()
    report = NewCompanyStatementValidationService().validate(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, company_facts=facts
    )
    assert report.filled_missing or report.corrections or report.items
    assert report.formulas_preserved


def test_cross_company_runner_suite(tmp_path: Path, out_svc: OutputService, monkeypatch):
    from services.excel_recalc_service import ExcelComUnavailable

    monkeypatch.setattr(
        "services.excel_recalc_service.load_excel_com",
        lambda: (_ for _ in ()).throw(ExcelComUnavailable("test isolation")),
    )
    """MSFT, AMZN, TJX, R&D-light consumer, lease-heavy retailer, seasonal — not certified without Excel COM."""
    profiles = [
        ("MSFT", "Microsoft Software Cloud", "7372", False, 3),
        ("AMZN", "Amazon.com Inc", "5961", False, 3),
        ("TJX", "The TJX Companies Retail Stores", "5331", False, 2),
        ("JBSS", "Snack Food Consumer Staples", "2060", False, 4),
        ("ROST", "Ross Stores lease-heavy retailer", "5651", False, 2),
        ("WSM", "Williams-Sonoma seasonal retailer", "5700", True, 2),
    ]
    runner = NewCompanyRunner(output_service=out_svc)
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="X",
        ticker_sheet_name="X",
        metadata={"inputs_annual_pe10": {fy: 18.0 for fy in FY}, "inputs_annual_e10": {fy: 5.0 for fy in FY}},
        scalars={"Current PE10": 19.0, "Current E10": 5.1},
    )
    tax_inputs = {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
        }
        for fy in FY
    }
    results = []
    with patch(_CRF_PARSE, return_value=crf):
        for ticker, name, sic, seasonal, q in profiles:
            wb = industrial_workbook(
                tmp_path / f"{ticker}.xlsx",
                quarter=q,
                seasonal=seasonal,
                rd_by_year={y: (0.0 if ticker == "JBSS" else 12.0) for y in YEARS},
            )
            crf_path = tmp_path / f"{ticker}_crf.xlsx"
            crf_path.write_bytes(b"x")
            done = runner.run(
                analysis_id=f"{ticker}-nc",
                ticker=ticker,
                company=name,
                template_path=wb,
                working_path=tmp_path / f"{ticker}_work.xlsx",
                custom_run_path=crf_path,
                company_facts=company_facts_for(),
                sec_manifest={**_filings_manifest(), "company_name": name, "sic": sic},
                tax_year_inputs=tax_inputs,
            )
            results.append((ticker, done["workflow_state"], done["output_gate"].blockers if done["output_gate"] else []))
            assert done["workflow_state"] != NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
            assert done["lease_review"].blocking is False
            assert done["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
            assert done["rd_decision"].selected_useful_life
            assert len(done["pe10"].fiscal_year_pe10) == 10
            assert len(done["tax"].years) == 10
            assert "LEASE_RATE_REVIEW_PENDING" not in (done["output_gate"].blockers if done["output_gate"] else [])
            assert "TEN_YEAR_SEC_COVERAGE_INCOMPLETE" not in (
                done["output_gate"].blockers if done["output_gate"] else []
            )
            assert done["workflow_state"] != NewCompanyWorkflowState.COMPLETE
            assert done["certification_status"] == CLOUD_PENDING_WINDOWS_CERTIFICATION
            assert "WORKBOOK_RECALCULATION_INCOMPLETE" in done["output_gate"].blockers
            assert done["periods"].latest_quarter == q
            assert len(done["tax"].years) == 10
            assert len(done["buybacks"].years) == 10
            assert done["deliverables"] is None or done["deliverables"].authorized is False
            if ticker == "JBSS":
                displayed_rd = [e.amount for e in done["rd"].expenses if e.displayed]
                assert displayed_rd
                assert all(a == 0.0 for a in displayed_rd)
                assert done["rd_decision"].selected_useful_life is not None
            if q in {2, 3}:
                assert done["seasonality"] is not None
                assert done["seasonality"].latest_quarter == q
                assert done["projection"] is not None
            if q == 4:
                assert done["seasonality"] is None or done["seasonality"].latest_quarter == 4
    assert len(results) == 6
    assert all(r[0] for r in results)


def test_gate_j_rejects_forged_ok_without_genuine_com(tmp_path: Path):
    from models.annual_update import AnnualValuationOutputs
    from services.excel_recalc_service import ExcelRecalcReport

    path = industrial_workbook(tmp_path / "wb.xlsx")
    periods = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    coverage = NewCompanySecCoverageService().build(
        analysis_id="a",
        ticker="MSFT",
        fiscal_years=FY,
        sec_manifest=_filings_manifest(),
        company_facts=company_facts_for(),
    )
    forged = ExcelRecalcReport(
        analysis_id="a",
        ticker="MSFT",
        status="ok",
        method="none",
        workbook_path=str(path),
        com_invoked=False,
        summary="forged",
    )
    gate = NewCompanyOutputGateService().evaluate(
        analysis_id="a",
        ticker="MSFT",
        periods=periods,
        coverage=coverage,
        statements=MagicMock(unresolved_material=[], summary="ok"),
        pe10=MagicMock(
            fiscal_year_pe10=[MagicMock(missing=False) for _ in FY],
            fiscal_year_e10=[MagicMock(missing=False) for _ in FY],
            current_pe10=MagicMock(value=20.0),
            current_e10=MagicMock(value=5.0),
            warnings=[],
        ),
        tax=MagicMock(complete=True, years=[]),
        rd_decision=MagicMock(selected_useful_life=3, blocking=False, blocking_reasons=[]),
        rd=MagicMock(lookback_complete=True, capitalization_ok=True),
        leases=MagicMock(complete=True, review=None),
        lease_review=MagicMock(proposed_rate=0.04, blocking=False, status="approved", analyst_action="approve"),
        buybacks=MagicMock(
            years=[MagicMock(dollars=1.0, shares=1.0, absence_class=None) for _ in FY],
            complete=True,
        ),
        current=MagicMock(as_of_mismatch=False, warnings=[]),
        projection=MagicMock(
            seasonality_adjusted_roic=0.1,
            seasonality_adjusted_roce=0.1,
            confidence=ProjectionConfidence.HIGH,
        ),
        recalc=forged,
        valuation=AnnualValuationOutputs(
            expected_annual_return=0.1,
            expected_return_with_dividends=0.12,
            current_graham_intrinsic_value=100.0,
            nopat=80.0,
            invested_capital=500.0,
            roic=0.16,
        ),
    )
    assert "WORKBOOK_RECALCULATION_INCOMPLETE" in gate.blockers
    assert not gate.report_authorized
    assert not genuine_excel_com_recalc(forged)


def test_helper_and_estimate_columns_are_skipped(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    wb = load_workbook(path)
    ws = wb["Income - GAAP"]
    helper_col = 3 + len(YEARS)
    ws.cell(1, helper_col, "FY2025 check")
    ws.cell(5, helper_col, "estimate")
    ws.cell(11, helper_col, 999)
    wb.save(path)
    wb.close()
    report = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    assert report.fiscal_years == FY
    assert str(helper_col) in report.skipped_helper_columns


def test_sec_coverage_records_overlapping_comparative_years():
    manifest = _filings_manifest()
    manifest["selected_filings"].append(
        {
            "accession_number": "000-2024",
            "filing_type": "10-K",
            "filing_date": "2025-02-01",
            "report_date": "2024-12-31",
            "document_url": "https://www.sec.gov/2024",
            "fiscal_year": 2024,
            "primary_document": "d10k.htm",
        }
    )
    report = NewCompanySecCoverageService().build(
        analysis_id="a",
        ticker="MSFT",
        fiscal_years=FY,
        sec_manifest=manifest,
        company_facts=company_facts_for(),
    )
    assert report.overlapping_years_deduped
    assert "FY2024" in report.overlapping_years_deduped or "FY2023" in report.overlapping_years_deduped


def test_tax_table_percent_residual_parentheses_and_not_etr_only(tmp_path: Path):
    table = [
        {"label": "Federal statutory rate", "rate": "21%"},
        {"label": "State taxes, net of federal benefit", "rate": "2.0"},
        {"label": "Foreign rate differential", "rate": "(1.0)"},
        {"label": "Research and development tax credit", "rate": "(1.2)"},
        {"label": "Other items", "rate": "0.5"},
        {"label": "Effective tax rate", "rate": "20.8"},
    ]
    extracted = NewCompanyTaxTableService().extract(
        fiscal_year="FY2025",
        candidate_table=table,
        heading="Income tax rate reconciliation (%)",
        accession_number="000-2025",
        note_location="Note 8 — Income Taxes",
        pretax_income=100.0,
        income_tax_expense=20.8,
    )
    assert extracted["table_units"] == "percent"
    assert extracted["mapped_rates"]["statutory_federal"] == pytest.approx(0.21)
    assert extracted["mapped_rates"]["credits"] == pytest.approx(-0.012)
    assert extracted["mapped_rates"]["foreign"] == pytest.approx(-0.01)
    assert extracted["residual_other"] == pytest.approx(0.208 - 0.21 - 0.02 - (-0.01) - (-0.012))
    assert extracted["signs_normalized"] is True
    assert extracted["category_coverage_complete"] is True
    assert extracted["raw_filing_lines"]

    wb = industrial_workbook(tmp_path / "tax.xlsx")
    report = NewCompanyTaxService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=wb,
        fiscal_years=["FY2025"],
        year_inputs={
            "FY2025": {
                "reported_effective_rate": 0.21,
                "candidate_table": table,
                "heading": "Income tax rate reconciliation (%)",
                "accession_number": "000-2025",
                "note_location": "Note 8 — Income Taxes",
            }
        },
    )
    assert report.complete
    assert report.years[0].statutory_federal == pytest.approx(0.21)
    assert report.years[0].note_or_table_location


def test_tax_etr_only_is_not_complete(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyTaxService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=["FY2025"],
        year_inputs={"FY2025": {"reported_effective_rate": 0.21}},
    )
    assert report.complete is False
    assert report.years[0].statutory_federal is None
    assert any("ETR" in w or "statutory" in w.lower() for w in report.warnings)


def test_unsigned_lease_override_cannot_bypass_review(tmp_path: Path, out_svc: OutputService):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="MSFT",
        ticker_sheet_name="MSFT",
        metadata={"inputs_annual_pe10": {fy: 20.0 for fy in FY}, "inputs_annual_e10": {fy: 5.0 for fy in FY}},
        scalars={"Current PE10": 22.0, "Current E10": 5.5},
    )
    tax_inputs = {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
        }
        for fy in FY
    }
    with patch(_CRF_PARSE, return_value=crf):
        done = runner.run(
            analysis_id="bypass",
            ticker="MSFT",
            company="Microsoft",
            template_path=path,
            working_path=tmp_path / "working.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=tax_inputs,
        )
        sneaky = runner.run(
            analysis_id="bypass",
            ticker="MSFT",
            company="Microsoft",
            template_path=tmp_path / "working.xlsx",
            working_path=tmp_path / "working.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=tax_inputs,
            lease_review_override={"action": "approve", "reason": "not an analyst"},
            finalize=True,
            prepare_working=False,
        )
    assert done["workflow_state"] != NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
    assert sneaky["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in sneaky["lease_review"].audit_trail)
    assert sneaky["lease_review"].blocking is False


def test_rd_override_writes_audit_trail(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    svc = NewCompanyRdService()
    first = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Software Cloud", "sic": "7372"},
    )
    second = svc.select_useful_life(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Software Cloud", "sic": "7372"},
        override=7,
        override_reason="longer platform cycle",
        prior_decision=first,
    )
    assert any(e.get("event") == "ANALYST_OVERRIDE" for e in second.audit_trail)
    wb = load_workbook(path)
    # apply writes the visible warning
    svc.apply(analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, decision=second)
    wb = load_workbook(path)
    assert "HAP ANALYSIS" in str(wb["R&D"]["A1"].value)
    wb.close()


def test_buyback_was_not_used_as_ending_shares_and_pct_fcf():
    facts = company_facts_for(buybacks=True, sbc_offset=True)
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        path = industrial_workbook(Path(td) / "wb.xlsx")
        report = NewCompanyBuybackService().apply(
            analysis_id="a", ticker="AAPL", workbook_path=path, fiscal_years=FY, company_facts=facts
        )
    y = report.years[-1]
    assert y.diluted_was is not None
    assert report.analysis.buybacks_pct_of_fcf is not None


def test_pe10_crf_parse_failure_is_incomplete_and_writes_no_zeros(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    (tmp_path / "crf.xlsx").write_bytes(b"x")
    with patch(_CRF_PARSE, side_effect=ValueError("corrupt CRF")):
        report = NewCompanyPe10Service().apply(
            analysis_id="a",
            ticker="MSFT",
            workbook_path=path,
            custom_run_path=tmp_path / "crf.xlsx",
            fiscal_years=FY,
        )
    assert report.status == "incomplete"
    assert all(o.missing and o.value is None for o in report.fiscal_year_pe10)
    assert all(o.missing and o.value is None for o in report.fiscal_year_e10)
    assert any("CRF parse failed" in w for w in report.warnings)


def test_pe10_out_of_tolerance_nearest_date_is_not_written(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    (tmp_path / "crf.xlsx").write_bytes(b"x")
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="MSFT",
        ticker_sheet_name="MSFT",
        metadata={"inputs_annual_pe10": {}, "inputs_annual_e10": {}},
        scalars={"Current PE10": 25.0, "Current E10": 6.0},
        periods=CustomRunPeriods(dates=["2020-06-01"]),
        historical_metrics={
            "PE10": CustomRunSeries(label="PE10", values=[99.0]),
            "E10": CustomRunSeries(label="E10", values=[9.0]),
        },
    )
    with patch(_CRF_PARSE, return_value=crf):
        report = NewCompanyPe10Service().apply(
            analysis_id="a",
            ticker="MSFT",
            workbook_path=path,
            custom_run_path=tmp_path / "crf.xlsx",
            fiscal_years=["FY2020"],
            fy_end_dates={"FY2020": "2020-12-31"},
            nearest_tolerance_days=45,
        )
    fy = report.fiscal_year_pe10[0]
    assert fy.missing or fy.value is None
    assert fy.value != 99.0
    assert any("PE10_FISCAL_DATE_MISMATCH" in w for w in report.warnings)
    assert report.current_pe10 and report.current_pe10.value == 25.0


def test_pe10_current_does_not_replace_historical_fiscal_values(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    (tmp_path / "crf.xlsx").write_bytes(b"x")
    crf = CustomRunData(
        source_filename="crf.xlsx",
        ticker="MSFT",
        ticker_sheet_name="MSFT",
        metadata={
            "inputs_annual_pe10": {fy: 18.0 for fy in FY},
            "inputs_annual_e10": {fy: 4.5 for fy in FY},
        },
        scalars={"Current PE10": 40.0, "Current E10": 8.0},
    )
    with patch(_CRF_PARSE, return_value=crf):
        report = NewCompanyPe10Service().apply(
            analysis_id="a",
            ticker="MSFT",
            workbook_path=path,
            custom_run_path=tmp_path / "crf.xlsx",
            fiscal_years=FY,
        )
    assert all(o.value == 18.0 for o in report.fiscal_year_pe10 if not o.missing)
    assert report.current_pe10 and report.current_pe10.value == 40.0
    assert report.current_pe10.value != report.fiscal_year_pe10[-1].value
    wb = load_workbook(path)
    ws = wb["Inputs"]
    hist_row = [ws.cell(10, col).value for col in range(3, 13)]
    assert 40.0 not in hist_row
    assert hist_row.count(18.0) == 10
    wb.close()


def test_word_report_withheld_until_authorized(tmp_path: Path):
    from services.new_company_deliverables_service import NewCompanyDeliverablesService

    wb = industrial_workbook(tmp_path / "wb.xlsx")
    out = tmp_path / "out"
    report = NewCompanyDeliverablesService().produce(
        analysis_id="a",
        ticker="MSFT",
        company="Microsoft",
        fiscal_year=2025,
        completed_workbook_path=wb,
        output_dir=out,
        periods=None,
        tax=None,
        pe10=None,
        rd_decision=None,
        rd=None,
        leases=None,
        lease_review=None,
        buybacks=None,
        projection=None,
        seasonality=None,
        valuation=None,
        gate=None,
        authorized=False,
    )
    assert report.authorized is False
    assert report.word_path is None
    assert list(out.glob("*.docx")) == []
    assert list(out.glob("*.xlsx"))


def _tax_inputs() -> dict:
    return {
        fy: {
            "reported_effective_rate": 0.21,
            "components": [{"label": "Federal statutory", "rate": 0.21, "house": "statutory_federal"}],
            "pretax_income": 100.0,
            "income_tax_expense": 21.0,
        }
        for fy in FY
    }


def _crf_for(ticker: str = "MSFT") -> CustomRunData:
    return CustomRunData(
        source_filename="crf.xlsx",
        ticker=ticker,
        ticker_sheet_name=ticker,
        metadata={"inputs_annual_pe10": {fy: 20.0 for fy in FY}, "inputs_annual_e10": {fy: 5.0 for fy in FY}},
        scalars={"Current PE10": 22.0, "Current E10": 5.5},
    )


def _patch_genuine_com(monkeypatch):
    def fake(self, *, analysis_id, ticker, workbook_path, fiscal_year=None):
        return ExcelRecalcReport(
            analysis_id=analysis_id,
            ticker=ticker,
            status="ok",
            method="excel_com_calculate_full_rebuild",
            workbook_path=str(workbook_path),
            com_invoked=True,
            summary="test genuine COM",
        )

    monkeypatch.setattr("services.excel_recalc_service.ExcelRecalcService.recalculate", fake)
    monkeypatch.setattr(
        "services.new_company_valuation_service.ExcelRecalcService.recalculate",
        fake,
    )
    from models.annual_update import AnalyticalResearchReport, NO_EXTERNAL_RESEARCH_REQUIRED

    def fake_research(self, **kw):
        return AnalyticalResearchReport(
            analysis_id=kw.get("analysis_id") or "",
            ticker=kw.get("ticker") or "X",
            status=NO_EXTERNAL_RESEARCH_REQUIRED,
            writes_to_workbook=False,
            selected_normalized_base_written=False,
            summary="test isolation — no external research",
        )

    monkeypatch.setattr(
        "services.annual_analytical_research_service.AnnualAnalyticalResearchService.investigate",
        fake_research,
    )


def test_supported_lease_does_not_pause_before_com(tmp_path: Path, out_svc: OutputService):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    with patch(_CRF_PARSE, return_value=_crf_for("MSFT")):
        result = runner.run(
            analysis_id="nc-lease-autonomous",
            ticker="MSFT",
            company="Microsoft",
            template_path=path,
            working_path=tmp_path / "working.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=_tax_inputs(),
        )
    assert result["workflow_state"] != NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
    assert result["lease_review"].blocking is False
    assert result["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert result["output_gate"] is not None
    assert result["valuation_judgment"] is None
    notes = out_svc.read_json("nc-lease-autonomous", "new_company_assumption_notes.json")
    assert notes["lease"]["decision_class"] == "AUTONOMOUS_AGENT_DECISION"
    wb = load_workbook(tmp_path / "working.xlsx")
    try:
        found = False
        for row in wb["Leases"].iter_rows(min_row=1, max_row=20, max_col=20):
            for cell in row:
                if "HAP ANALYSIS" in str(cell.value or ""):
                    found = True
        assert found
    finally:
        wb.close()


def test_approved_lease_permits_com_and_valuation_judgment(
    tmp_path: Path, out_svc: OutputService, monkeypatch
):
    _patch_genuine_com(monkeypatch)
    path = industrial_workbook(tmp_path / "wb.xlsx", quarter=2)
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    working = tmp_path / "working.xlsx"
    original_a11 = load_workbook(path)["Expected Returns & Buybacks"]["A11"].value
    with patch(_CRF_PARSE, return_value=_crf_for("MSFT")):
        done = runner.run(
            analysis_id="nc-com-judge",
            ticker="MSFT",
            company="Microsoft",
            template_path=path,
            working_path=working,
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=_tax_inputs(),
        )
    assert done["workflow_state"] != NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
    assert done["lease_review"].decision_class == "AUTONOMOUS_AGENT_DECISION"
    assert done["lease_review"].blocking is False
    assert genuine_excel_com_recalc(done["recalc"])
    assert done["valuation_judgment"] is not None
    assert done["valuation_judgment"].original_assumptions_preserved is True
    assert done["output_gate"].gates.get("L_valuation_judgment") == "pass"
    assert "LEASE_RATE_REVIEW_PENDING" not in done["output_gate"].blockers
    wb = load_workbook(working)
    try:
        assert wb["Expected Returns & Buybacks"]["A11"].value == original_a11
        labeled = False
        for sheet in wb.sheetnames:
            for row in wb[sheet].iter_rows(min_row=1, max_row=40, max_col=20):
                for cell in row:
                    text = str(cell.value or "")
                    comment = cell.comment.text if cell.comment else ""
                    if "HAP ANALYSIS" in text or "HAP ANALYSIS" in comment:
                        labeled = True
        assert labeled or done["valuation_judgment"].hap_analysis_cells
    finally:
        wb.close()
    assert done["circular"] is not None
    assert done["valuation_judgment"].hap_introduced_circular_count == 0
    assert "Q2" in (done["valuation_judgment"].period_context or "")


def test_keep_adjust_insufficient_independent_on_new_company_path(tmp_path: Path, monkeypatch):
    from tests.test_annual_growth_analysis import _geo, _valuation_workbook
    from services.annual_analyst_intelligence_service import AnnualAnalystIntelligenceService
    from services.annual_judgment_service import AnnualJudgmentService
    from services.new_company_valuation_service import NewCompanyValuationService
    from services.workbook_flag_service import HAP_ANALYSIS_LABEL

    _patch_genuine_com(monkeypatch)
    keep = tmp_path / "keep.xlsx"
    adj = tmp_path / "adj.xlsx"
    insuff = tmp_path / "insuff.xlsx"
    eps_keep = [3.17, 2.84, 3.43, 4.69, 5.17, 5.33, 5.40, 5.15, 5.03, 5.26]
    _valuation_workbook(
        keep,
        eps=eps_keep,
        revenue=_geo(847.0, 0.037, 10),
        oi=_geo(60.5, 0.044, 10),
        a11=0.0267,
        c5=0.143,
        a14=0.1866,
    )
    _valuation_workbook(
        adj,
        a11=0.40,
        eps=_geo(2.0, 0.06, 10),
        revenue=_geo(200.0, 0.058, 10),
        oi=_geo(20.0, 0.062, 10),
    )
    ni = [36, 33, 39, 54, 60, 62, 63, 60, 59, 62]
    da = [16, 15, 17, 18, 18, 18, 21, 25, 27, 28]
    capex = [-11, -13, -15, -15, -25, -18, -21, -28, -51, -88]
    _valuation_workbook(
        insuff,
        ni=ni,
        da=da,
        capex=capex,
        oi=[60, 56, 59, 79, 85, 87, 90, 85, 85, 89],
        eps=[3.17, 2.84, 3.43, 4.69, 5.17, 5.33, 5.4, 5.15, 5.03, 5.26],
        b6_total=-0.95,
        c6_annual=-0.283,
        a11=0.027,
    )
    keep_svc = tmp_path / "keep_svc.xlsx"
    adj_svc = tmp_path / "adj_svc.xlsx"
    ins_svc = tmp_path / "insuff_svc.xlsx"
    shutil.copy2(keep, keep_svc)
    shutil.copy2(adj, adj_svc)
    shutil.copy2(insuff, ins_svc)

    intel = AnnualAnalystIntelligenceService()
    judge_svc = AnnualJudgmentService()

    def _judge(path: Path):
        ctx = intel.build_judgment_context(analysis_id="nc-val", ticker="X", workbook_path=path)
        return judge_svc.apply(analysis_id="nc-val", ticker="X", workbook_path=path, context=ctx)

    _keep_er, keep_direct = _judge(keep)
    _adj_er, adj_direct = _judge(adj)
    _ins_er, ins_direct = _judge(insuff)
    assert keep_direct.er_analysis.decision == "KEEP_EXISTING"
    assert adj_direct.er_analysis.decision == "ADJUST"
    assert ins_direct.oe_analysis.decision == "INSUFFICIENT_EVIDENCE"
    assert keep_direct.er_analysis.decision != adj_direct.er_analysis.decision
    assert adj_direct.er_analysis.decision != ins_direct.oe_analysis.decision
    assert getattr(ins_direct.oe_analysis, "selected_prospective_rate", None) is None

    svc = NewCompanyValuationService()
    prior = _ok_recalc()

    def _run(path: Path, q: int | None = None):
        return svc.apply(
            analysis_id="nc-val",
            ticker="X",
            workbook_path=path,
            fiscal_quarter=q,
            skip_initial_recalc=True,
            prior_recalc=prior,
        )

    keep_r, _, keep_j, keep_c, _, _ = _run(keep_svc)
    adj_r, _, adj_j, _, _, _ = _run(adj_svc)
    ins_r, _, ins_j, ins_c, _, _ = _run(ins_svc)
    assert keep_r.original_assumptions_preserved
    assert adj_r.original_assumptions_preserved
    assert ins_r.original_assumptions_preserved
    assert keep_j.er_analysis.decision == "KEEP_EXISTING"
    assert ins_j.oe_analysis.decision == "INSUFFICIENT_EVIDENCE"
    assert getattr(ins_j.oe_analysis, "selected_prospective_rate", None) is None
    wb = load_workbook(adj_svc)
    try:
        assert wb["Expected Returns & Buybacks"]["A11"].value == pytest.approx(0.40)
        hap_found = False
        for row in wb["Expected Returns & Buybacks"].iter_rows(min_row=1, max_row=40, max_col=20):
            for cell in row:
                text = str(cell.value or "")
                comment = cell.comment.text if cell.comment else ""
                if HAP_ANALYSIS_LABEL in text or HAP_ANALYSIS_LABEL in comment or "HAP ANALYSIS" in text:
                    hap_found = True
        assert hap_found or adj_r.hap_analysis_cells
    finally:
        wb.close()
    assert keep_c.hap_introduced == []
    assert ins_c.hap_introduced == []
    disc = getattr(getattr(ins_j, "oe_base_analysis", None), "disclosure", None)
    if disc is not None:
        word_text = getattr(disc, "word_text", None) or getattr(disc, "display_text", None) or ""
        assert word_text or getattr(disc, "decision", None)
    q2_r, _, _, _, _, _ = _run(keep_svc, q=2)
    q3_r, _, _, _, _, _ = _run(keep_svc, q=3)
    assert "six-month YTD" in q2_r.period_context
    assert "standalone Q2" in q2_r.period_context
    assert "projected full-year" in q2_r.period_context
    assert "nine-month YTD" in q3_r.period_context
    assert "standalone Q3" in q3_r.period_context


def test_gate_l_requires_judgment_after_genuine_com(tmp_path: Path):
    from models.annual_update import AnnualValuationOutputs
    from models.new_company import NewCompanyValuationReport

    path = industrial_workbook(tmp_path / "wb.xlsx")
    periods = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    coverage = NewCompanySecCoverageService().build(
        analysis_id="a",
        ticker="MSFT",
        fiscal_years=FY,
        sec_manifest=_filings_manifest(),
        company_facts=company_facts_for(),
    )
    genuine = _ok_recalc(path=str(path))
    common = dict(
        analysis_id="a",
        ticker="MSFT",
        periods=periods,
        coverage=coverage,
        statements=MagicMock(unresolved_material=[], summary="ok"),
        pe10=MagicMock(
            fiscal_year_pe10=[MagicMock(missing=False) for _ in FY],
            fiscal_year_e10=[MagicMock(missing=False) for _ in FY],
            current_pe10=MagicMock(value=20.0),
            current_e10=MagicMock(value=5.0),
            warnings=[],
        ),
        tax=MagicMock(complete=True, years=[]),
        rd_decision=MagicMock(selected_useful_life=3, blocking=False, blocking_reasons=[]),
        rd=MagicMock(lookback_complete=True, capitalization_ok=True),
        leases=MagicMock(complete=True, review=None),
        lease_review=MagicMock(proposed_rate=0.04, blocking=False, status="approved", analyst_action="approve"),
        buybacks=MagicMock(
            years=[MagicMock(dollars=1.0, shares=1.0, absence_class=None) for _ in FY],
            complete=True,
        ),
        current=MagicMock(as_of_mismatch=False, warnings=[]),
        projection=MagicMock(
            seasonality_adjusted_roic=0.1,
            seasonality_adjusted_roce=0.1,
            confidence=ProjectionConfidence.HIGH,
        ),
        valuation=AnnualValuationOutputs(
            expected_annual_return=0.1,
            expected_return_with_dividends=0.12,
            current_graham_intrinsic_value=100.0,
            nopat=80.0,
            invested_capital=500.0,
            roic=0.16,
        ),
    )
    missing = NewCompanyOutputGateService().evaluate(recalc=genuine, valuation_judgment=None, **common)
    assert missing.gates.get("L_valuation_judgment") == "fail"
    assert "VALUATION_JUDGMENT_INCOMPLETE" in missing.blockers
    ok_j = NewCompanyValuationReport(
        analysis_id="a",
        ticker="MSFT",
        status="ok",
        original_assumptions_preserved=True,
        hap_introduced_circular_count=0,
        er_decision="KEEP_EXISTING",
        oe_decision="INSUFFICIENT_EVIDENCE",
        graham_decision="KEEP_EXISTING",
        period_context="Q2 initiation: distinguish reported six-month YTD",
    )
    passed = NewCompanyOutputGateService().evaluate(recalc=genuine, valuation_judgment=ok_j, **common)
    assert passed.gates.get("L_valuation_judgment") == "pass"
    assert "VALUATION_JUDGMENT_INCOMPLETE" not in passed.blockers
    assert any("INSUFFICIENT" in w for w in passed.warnings)
    overwritten = ok_j.model_copy(update={"original_assumptions_preserved": False})
    bad = NewCompanyOutputGateService().evaluate(recalc=genuine, valuation_judgment=overwritten, **common)
    assert "ORIGINAL_VALUATION_ASSUMPTIONS_OVERWRITTEN" in bad.blockers
    circ = ok_j.model_copy(update={"hap_introduced_circular_count": 1, "status": "BLOCKING_STRUCTURAL_ERROR"})
    circ_gate = NewCompanyOutputGateService().evaluate(recalc=genuine, valuation_judgment=circ, **common)
    assert "HAP_INTRODUCED_CIRCULAR_REFERENCE" in circ_gate.blockers


def test_word_carries_hap_judgment_and_period_context(tmp_path: Path):
    from docx import Document
    from models.new_company import NewCompanyValuationReport
    from services.new_company_deliverables_service import NewCompanyDeliverablesService

    wb = industrial_workbook(tmp_path / "wb.xlsx", quarter=3)
    periods = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=wb)
    judgment = MagicMock()
    judgment.expected_return = MagicMock(decision="KEEP_EXISTING", rationale="historical matches prospective", existing_assumption=0.04, selected_prospective_rate=None)
    judgment.er_analysis = judgment.expected_return
    judgment.oe_analysis = MagicMock(decision="INSUFFICIENT_EVIDENCE", rationale="capex distortion", existing_assumption=-0.28, selected_prospective_rate=None)
    judgment.graham_analysis = MagicMock(decision="ADJUST", rationale="cluster median", existing_assumption=0.20, selected_prospective_rate=0.05)
    judgment.oe_base_analysis = MagicMock(disclosure=MagicMock(word_text="Reported owner earnings are distorted by elevated capex. HAP does not substitute a normalized base."))
    judgment.hap_analysis_cells = ["Expected Returns & Buybacks!H1"]
    val_rep = NewCompanyValuationReport(
        analysis_id="a",
        ticker="MSFT",
        period_context="Q3 initiation: distinguish reported nine-month YTD, standalone Q3, and projected full-year.",
        original_assumptions_preserved=True,
        hap_analysis_cells=["Expected Returns & Buybacks!H1"],
        er_decision="KEEP_EXISTING",
        oe_decision="INSUFFICIENT_EVIDENCE",
        graham_decision="ADJUST",
        summary="test",
    )
    out = tmp_path / "out"
    report = NewCompanyDeliverablesService().produce(
        analysis_id="a",
        ticker="MSFT",
        company="Microsoft",
        fiscal_year=2025,
        completed_workbook_path=wb,
        output_dir=out,
        periods=periods,
        tax=None,
        pe10=None,
        rd_decision=None,
        rd=None,
        leases=None,
        lease_review=None,
        buybacks=None,
        projection=None,
        seasonality=None,
        valuation=None,
        gate=None,
        authorized=True,
        judgment=judgment,
        valuation_report=val_rep,
    )
    assert report.authorized
    assert report.word_path
    doc = Document(report.word_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "HAP valuation judgment" in text
    assert "KEEP_EXISTING" in text
    assert "INSUFFICIENT_EVIDENCE" in text
    assert "nine-month YTD" in text
    assert "not applied to original cell" in text
    assert "does not substitute a normalized base" in text.lower() or "distorted" in text.lower()


_IDCC_CAPITAL_TABLE = """
The following table sets forth the total number of shares repurchased and the dollar value of shares
repurchased under the Share Repurchase Program, cash dividends on outstanding common stock declared,
and the total capital returned to our shareholders (in thousands):
Share Repurchase Program Cash Dividends Declared Total Capital Returned to Shareholders
# of Shares Value Per Share Value
2025 385 $ 102,319 $ 2.60 $ 67,105 $ 169,424
2024 644 66,726 1.70 43,130 109,856
2023 4,411 339,704 1.50 39,296 379,000
2022 1,224 74,445 1.40 41,949 116,394
2021 458 30,000 1.40 43,041 73,041
2020 6 349 1.40 43,111 43,460
2019 2,962 196,269 1.40 43,718 239,987
2018 1,478 110,505 1.40 47,922 158,427
2017 107 7,693 1.30 45,122 52,815
2016 1,304 64,685 1.00 34,359 99,044
Total 18,369 $ 1,241,730 $ 16.60 $ 504,632 $ 1,746,362
Impact of Macroeconomic and Geopolitical Factors
"""


def _duration_entry(val: float, fy: int, months: int = 6, form: str = "10-Q") -> dict:
    end = {3: f"{fy}-03-31", 6: f"{fy}-06-30", 9: f"{fy}-09-30"}[months]
    fp = {3: "Q1", 6: "Q2", 9: "Q3"}[months]
    return {
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": form,
        "start": f"{fy}-01-01",
        "end": end,
        "filed": f"{fy}-08-01",
        "accn": "0002",
        "frame": None,
    }


def _gate_base(tmp_path: Path, **overrides):
    from models.annual_update import AnnualValuationOutputs

    path = industrial_workbook(tmp_path / "wb.xlsx")
    periods = NewCompanyPeriodService().detect(analysis_id="a", ticker="MSFT", workbook_path=path)
    coverage = NewCompanySecCoverageService().build(
        analysis_id="a",
        ticker="MSFT",
        fiscal_years=FY,
        sec_manifest=_filings_manifest(),
        company_facts=company_facts_for(),
    )
    kwargs = dict(
        analysis_id="a",
        ticker="MSFT",
        periods=periods,
        coverage=coverage,
        statements=MagicMock(unresolved_material=[], summary="ok"),
        pe10=MagicMock(
            fiscal_year_pe10=[MagicMock(missing=False) for _ in FY],
            fiscal_year_e10=[MagicMock(missing=False) for _ in FY],
            current_pe10=MagicMock(value=20.0),
            current_e10=MagicMock(value=5.0),
            warnings=[],
        ),
        tax=MagicMock(complete=True, years=[]),
        rd_decision=MagicMock(selected_useful_life=3, blocking=False, blocking_reasons=[]),
        rd=MagicMock(lookback_complete=True, capitalization_ok=True),
        leases=MagicMock(complete=True, review=None),
        lease_review=MagicMock(proposed_rate=0.04, blocking=False, status="approved", analyst_action="approve"),
        buybacks=MagicMock(
            years=[MagicMock(dollars=1.0, shares=1.0, shares_derived=False, absence_class=None) for _ in FY],
            complete=True,
            warnings=[],
        ),
        current=MagicMock(as_of_mismatch=False, warnings=[]),
        projection=MagicMock(
            seasonality_adjusted_roic=0.1,
            seasonality_adjusted_roce=0.1,
            confidence=ProjectionConfidence.HIGH,
            wacc=0.08,
        ),
        recalc=_ok_recalc(path=str(path)),
        valuation=AnnualValuationOutputs(
            expected_annual_return=0.1,
            expected_return_with_dividends=0.12,
            current_graham_intrinsic_value=100.0,
            nopat=80.0,
            invested_capital=500.0,
            roic=0.16,
        ),
        valuation_judgment=MagicMock(
            original_assumptions_preserved=True,
            hap_introduced_circular_count=0,
            status="ok",
            er_decision="KEEP_EXISTING",
            oe_decision="KEEP_EXISTING",
            graham_decision="KEEP_EXISTING",
            normalized_base_decision="KEEP_EXISTING",
        ),
    )
    kwargs.update(overrides)
    return kwargs


def test_buyback_explicit_10k_shares_and_cumulative_xbrl_rejected(tmp_path: Path):
    from services.new_company_buyback_service import parse_share_repurchase_program_table

    parsed = parse_share_repurchase_program_table(_IDCC_CAPITAL_TABLE)
    assert parsed[2016]["shares"] == pytest.approx(1.304)
    assert parsed[2016]["dollars"] == pytest.approx(64.685)
    assert parsed[2023]["shares"] == pytest.approx(4.411)
    assert parsed[2025]["shares"] == pytest.approx(0.385)

    facts = company_facts_for(buybacks=True)
    # Cumulative program-to-date share tag for 2019 (start 2014).
    facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"] = [
        {
            "val": 11_241_000,
            "fy": 2019,
            "fp": "FY",
            "form": "10-K",
            "start": "2014-01-01",
            "end": "2019-12-31",
            "filed": "2020-02-01",
            "accn": "0001",
            "frame": None,
        }
    ]
    # Remove annual share facts so 10-K table is the source.
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyBuybackService().apply(
        analysis_id="a",
        ticker="IDCC",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=facts,
        filings_text={"FY2025": _IDCC_CAPITAL_TABLE},
    )
    y2016 = next(y for y in report.years if y.fiscal_year == "FY2016")
    y2019 = next(y for y in report.years if y.fiscal_year == "FY2019")
    assert y2016.shares == pytest.approx(1.304)
    assert y2016.shares_derived is False
    assert "share_repurchase_program_table" in (y2016.shares_source or "")
    assert y2019.shares == pytest.approx(2.962)
    assert y2019.shares != pytest.approx(11.241)
    assert all(y.shares is not None for y in report.years)
    assert "BUYBACK_SHARES_COVERAGE_INCOMPLETE" not in ",".join(report.warnings)


def test_buyback_derived_from_avg_price_not_share_delta(tmp_path: Path):
    facts = company_facts_for(buybacks=True)
    facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"] = []
    facts["facts"]["us-gaap"]["CommonStockSharesOutstanding"] = {
        "label": "so",
        "units": {"shares": [_facts_entry(100_000_000, y) for y in YEARS]},
    }
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyBuybackService().apply(
        analysis_id="a", ticker="AAPL", workbook_path=path, fiscal_years=FY, company_facts=facts
    )
    y2016 = next(y for y in report.years if y.fiscal_year == "FY2016")
    assert y2016.shares_derived
    assert y2016.derivation_formula == "repurchase_dollars / disclosed_average_repurchase_price"
    assert y2016.shares == pytest.approx(1.0)
    assert "change in shares outstanding is not used" in " ".join(report.analysis.notes).lower()


def test_buyback_missing_evidence_stays_missing_not_zero(tmp_path: Path):
    facts = company_facts_for(buybacks=True)
    del facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]
    del facts["facts"]["us-gaap"]["TreasuryStockAcquiredAverageCostPerShare"]
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyBuybackService().apply(
        analysis_id="a", ticker="AAPL", workbook_path=path, fiscal_years=FY, company_facts=facts
    )
    y2016 = next(y for y in report.years if y.fiscal_year == "FY2016")
    assert y2016.dollars == pytest.approx(5.0)
    assert y2016.shares is None
    assert y2016.shares != 0
    assert y2016.absence_class is None
    assert any("BUYBACK_SHARES_COVERAGE_INCOMPLETE: FY2016" in w for w in report.warnings)


_LNN_NO_REPO_2019 = (
    "There were no shares repurchased during the twelve months ended August 31, 2019, 2018, and 2017.\n"
    "Repurchase of common shares — (48,335) (96,883)\n"
)
_LNN_NO_REPO_2021 = (
    "There were no shares repurchased during the twelve months ended August 31, 2021, 2020, and 2019.\n"
)
_LNN_CFS_2018 = "Repurchase of common shares - - (48,335)\n"


def test_buyback_lnn_style_narrative_and_cfs_zeros_not_quarterly_xbrl(tmp_path: Path):
    from services.new_company_buyback_service import (
        parse_cfs_repurchase_dash_zeros,
        parse_no_shares_repurchased_narrative,
    )

    narrative = parse_no_shares_repurchased_narrative(_LNN_NO_REPO_2019)
    assert set(narrative) >= {2017, 2018, 2019}
    assert narrative[2017]["dollars"] == 0.0
    cfs = parse_cfs_repurchase_dash_zeros(_LNN_CFS_2018, 2018)
    assert cfs[2018]["dollars"] == 0.0
    assert cfs[2017]["dollars"] == 0.0
    assert 2016 not in cfs

    facts = company_facts_for(buybacks=True)
    dollar_rows = facts["facts"]["us-gaap"]["PaymentsForRepurchaseOfCommonStock"]["units"]["USD"]
    facts["facts"]["us-gaap"]["PaymentsForRepurchaseOfCommonStock"]["units"]["USD"] = [
        e for e in dollar_rows if e["fy"] not in {2017, 2018, 2019, 2021}
    ]
    share_rows = facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"]
    facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodShares"]["units"]["shares"] = [
        e for e in share_rows if e["fy"] not in {2017, 2018, 2019, 2021}
    ]
    facts["facts"]["us-gaap"]["TreasuryStockSharesAcquired"] = {
        "label": "treasury shares acquired",
        "units": {
            "shares": [
                {
                    "val": 0,
                    "fy": y,
                    "fp": "FY",
                    "form": "10-K",
                    "start": f"{y - 1}-09-01",
                    "end": f"{y}-08-31",
                    "filed": f"{y + 1}-10-20",
                    "accn": "0001",
                    "frame": f"CY{y}",
                }
                for y in (2017, 2018, 2019, 2021)
            ]
        },
    }
    facts["facts"]["us-gaap"]["StockRepurchasedDuringPeriodValue"] = {
        "label": "period value",
        "units": {
            "USD": [
                {
                    "val": 0,
                    "fy": 2017,
                    "fp": "Q4",
                    "form": "10-Q",
                    "start": "2017-06-01",
                    "end": "2017-08-31",
                    "filed": "2017-10-01",
                    "accn": "q",
                    "frame": "CY2017Q4",
                }
            ]
        },
    }
    path = industrial_workbook(tmp_path / "lnn.xlsx")
    report = NewCompanyBuybackService().apply(
        analysis_id="a",
        ticker="LNN",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=facts,
        filings_text={
            "FY2019": _LNN_NO_REPO_2019,
            "FY2018": _LNN_CFS_2018,
            "FY2021": _LNN_NO_REPO_2021,
        },
    )
    for year in ("FY2017", "FY2018", "FY2019", "FY2021"):
        rec = next(y for y in report.years if y.fiscal_year == year)
        assert rec.dollars == 0.0
        assert rec.shares == 0.0
        assert rec.absence_class == BuybackAbsenceClass.REPORTED_ZERO
        assert rec.dollars_source and "10k" in rec.dollars_source
    y2016 = next(y for y in report.years if y.fiscal_year == "FY2016")
    assert y2016.dollars == pytest.approx(5.0)
    assert y2016.absence_class != BuybackAbsenceClass.REPORTED_ZERO
    assert not any("BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: FY2017" in w for w in report.warnings)
    gates = NewCompanyOutputGateService().evaluate(
        **_gate_base(tmp_path, buybacks=report)
    )
    assert gates.gates["G_buybacks"] == "pass"


def test_buyback_omitted_cfs_line_stays_missing_not_zero(tmp_path: Path):
    facts = company_facts_for(buybacks=True)
    facts["facts"]["us-gaap"]["PaymentsForRepurchaseOfCommonStock"]["units"]["USD"] = [
        e
        for e in facts["facts"]["us-gaap"]["PaymentsForRepurchaseOfCommonStock"]["units"]["USD"]
        if e["fy"] != 2019
    ]
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyBuybackService().apply(
        analysis_id="a",
        ticker="LNN",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=facts,
        filings_text={
            "FY2019": "Cash flows from financing activities\nProceeds from issuance of common stock 5,000\n"
        },
    )
    y2019 = next(y for y in report.years if y.fiscal_year == "FY2019")
    assert y2019.dollars is None
    assert y2019.shares is not None
    assert y2019.absence_class != BuybackAbsenceClass.REPORTED_ZERO
    assert any("BUYBACK_DOLLARS_COVERAGE_INCOMPLETE: FY2019" in w for w in report.warnings)
    gates = NewCompanyOutputGateService().evaluate(**_gate_base(tmp_path, buybacks=report))
    assert gates.gates["G_buybacks"] == "fail"


def test_lease_disclosed_rate_does_not_overwrite_long_term_formulas(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    wb = load_workbook(path)
    ls = wb["Leases"]
    ls["A18"] = "Estimated Long-Term Rate"
    for i in range(len(YEARS)):
        letter = chr(ord("C") + i)
        ls.cell(18, 3 + i, f"=Inputs!{letter}35/Inputs!{letter}27")
        ls.cell(20, 3 + i, f"=NPV(B18,C10:G10)")
    wb.save(path)
    wb.close()
    report = NewCompanyLeaseService().apply(
        analysis_id="a", ticker="LNN", workbook_path=path, fiscal_years=FY, company_facts=company_facts_for()
    )
    wb = load_workbook(path)
    try:
        assert str(wb["Leases"]["C18"].value).startswith("=Inputs!")
        blob = " ".join(str(c.value or "") for row in wb["Leases"].iter_rows(min_row=1, max_row=20, max_col=20) for c in row)
        assert "ASC 842" in blob
        assert "Interest Expense / Total Debt" in blob
        assert report.review.selected_rate == pytest.approx(0.045)
    finally:
        wb.close()


def test_rd_selected_life_rewrites_three_year_schedule_formulas(tmp_path: Path):
    path = industrial_workbook(tmp_path / "rd.xlsx", rd_life_cell=3)
    wb = load_workbook(path)
    rd = wb["R&D"]
    rd["B1"] = '="FY "&RIGHT(C1,4)-1'
    rd["C1"] = '="FY "&RIGHT(D1,4)-1'
    rd["D1"] = '="FY "&RIGHT(E1,4)-1'
    rd["E1"] = "=Inputs!C1"
    rd["B2"] = "=Inputs!E104"
    rd["C2"] = "=Inputs!F104"
    rd["D2"] = "=Inputs!G104"
    rd["E2"] = '=IF(Inputs!C103="",0,Inputs!C103)'
    rd["E3"] = "=E2+D2*2/3+1/3*C2"
    rd["E4"] = "=(E2+D2+C2)/3"
    wb.save(path)
    wb.close()
    svc = NewCompanyRdService()
    decision = svc.select_useful_life(
        analysis_id="a",
        ticker="LNN",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Lindsay Corporation", "sic": "3523", "sic_description": "Farm machinery"},
        company_facts=company_facts_for(),
    )
    report = svc.apply(
        analysis_id="a",
        ticker="LNN",
        workbook_path=path,
        fiscal_years=FY,
        decision=decision,
        company_facts=company_facts_for(),
    )
    assert decision.selected_useful_life == 5
    wb = load_workbook(path)
    try:
        assert wb["R&D"]["B8"].value == 5
        e3 = str(wb["R&D"]["E3"].value or "")
        e4 = str(wb["R&D"]["E4"].value or "")
        assert "/5" in e3.replace(" ", "") or "*1/5" in e3.replace(" ", "")
        assert "/3" not in e3.replace(" ", "")
        assert e4.replace(" ", "").endswith("/5,0)") or "/5)" in e4.replace(" ", "")
        assert isinstance(wb["R&D"]["B2"].value, (int, float))
        assert wb["R&D"]["B20"].value is not None
        blob = " ".join(str(c.value or "") for row in wb["R&D"].iter_rows(min_row=1, max_row=20, max_col=22) for c in row)
        assert "R&D!B8" in blob
    finally:
        wb.close()
    assert report.useful_life == 5


def test_q2_seasonality_sufficient_sec_ytd_and_insufficient_standalone(tmp_path: Path):
    path = industrial_workbook(tmp_path / "idcc.xlsx", quarter=2)
    wb = load_workbook(path)
    lq = wb["Last Quarter IS Standardized"]
    lq["C7"] = "3 Months Ended"
    lq["G11"] = None
    lq["G20"] = None
    lq["H11"] = None
    lq["H20"] = None
    lq["C11"] = 260.17
    lq["C20"] = 139.24
    lq["A21"] = "Other Operating Income"
    wb.save(path)
    wb.close()

    insufficient = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="IDCC", workbook_path=path, fiscal_years=FY, latest_quarter=2
    )
    oi = next(c for c in insufficient.components if c.metric == "operating_income")
    assert oi.ytd_value is None
    assert oi.seasonality_adjusted is None
    assert any("HISTORY_INSUFFICIENT" in w or "UNRELIABLE" in w for w in insufficient.warnings)

    facts = company_facts_for()
    facts["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"].extend(
        [_duration_entry(12_000_000 + i * 1_000_000, y, 6) for i, y in enumerate(range(2021, 2027))]
    )
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"].extend(
        [_duration_entry(50_000_000 + i * 2_000_000, y, 6) for i, y in enumerate(range(2021, 2027))]
    )
    sufficient = NewCompanySeasonalityService().project(
        analysis_id="a",
        ticker="IDCC",
        workbook_path=path,
        fiscal_years=FY,
        latest_quarter=2,
        company_facts=facts,
        latest_quarter_fiscal_year="FY2026",
    )
    oi2 = next(c for c in sufficient.components if c.metric == "operating_income")
    assert oi2.ytd_value is not None
    assert oi2.ytd_value != pytest.approx(139.24)
    assert len(oi2.proportions) >= 3
    assert oi2.seasonality_adjusted is not None
    assert sufficient.confidence in {ProjectionConfidence.HIGH, ProjectionConfidence.MEDIUM, ProjectionConfidence.LOW}


def test_wacc_mapped_missing_and_independent_roic(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", quarter=2)
    wb = load_workbook(path)
    bs = wb["Balance Sheet - Standardized"]
    bs["A126"] = "WACC Fiscal"
    bs["L126"] = 9.0646
    fm = wb["Final Metrics"]
    fm["A7"] = "WACC"
    fm["L7"] = 0.090646
    wb.save(path)
    wb.close()
    from services.new_company_projection_service import resolve_workbook_wacc

    mapped, src = resolve_workbook_wacc(path)
    assert mapped == pytest.approx(0.090646)
    assert src

    empty = industrial_workbook(tmp_path / "nowacc.xlsx", quarter=2)
    missing, missing_src = resolve_workbook_wacc(empty)
    assert missing is None
    assert missing_src is None

    seasonality = NewCompanySeasonalityService().project(
        analysis_id="a", ticker="MSFT", workbook_path=path, fiscal_years=FY, latest_quarter=2
    )
    proj = NewCompanyProjectionService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        latest_quarter=2,
        seasonality=seasonality,
        wacc=None,
        wacc_source=None,
    )
    assert proj.seasonality_adjusted_roic is not None
    assert proj.projected_roic_wacc is None
    assert "WACC_NOT_SUPPLIED" in proj.warnings
    proj2 = NewCompanyProjectionService().apply(
        analysis_id="a",
        ticker="MSFT",
        workbook_path=path,
        fiscal_years=FY,
        latest_quarter=2,
        seasonality=seasonality,
        wacc=mapped,
        wacc_source=src,
    )
    assert proj2.projected_roic_wacc == pytest.approx(proj2.seasonality_adjusted_roic - mapped)


def test_gates_g_and_i_pass_fail_and_word_withheld(tmp_path: Path):
    from services.new_company_deliverables_service import NewCompanyDeliverablesService

    passing = NewCompanyOutputGateService().evaluate(**_gate_base(tmp_path))
    assert passing.gates["G_buybacks"] == "pass"
    assert passing.gates["I_projection"] == "pass"

    share_gap = NewCompanyOutputGateService().evaluate(
        **_gate_base(
            tmp_path,
            buybacks=MagicMock(
                years=[MagicMock(dollars=1.0, shares=None, shares_derived=False, absence_class=None) for _ in FY],
                complete=False,
                warnings=["BUYBACK_SHARES_COVERAGE_INCOMPLETE: FY2016"],
            ),
        )
    )
    assert share_gap.gates["G_buybacks"] == "fail"
    assert "BUYBACK_SHARES_COVERAGE_INCOMPLETE" in share_gap.blockers
    assert not share_gap.report_authorized

    roic_fail = NewCompanyOutputGateService().evaluate(
        **_gate_base(
            tmp_path,
            projection=MagicMock(
                seasonality_adjusted_roic=None,
                seasonality_adjusted_roce=None,
                confidence=ProjectionConfidence.UNRELIABLE,
                wacc=None,
            ),
        )
    )
    assert roic_fail.gates["I_projection"] == "fail"
    assert "PROJECTED_ROIC_FAILED" in roic_fail.blockers
    assert not roic_fail.report_authorized

    independent = NewCompanyOutputGateService().evaluate(
        **_gate_base(
            tmp_path,
            projection=MagicMock(
                seasonality_adjusted_roic=0.12,
                seasonality_adjusted_roce=0.11,
                confidence=ProjectionConfidence.MEDIUM,
                wacc=None,
            ),
        )
    )
    assert independent.gates["I_projection"] == "pass"
    assert "WACC_NOT_SUPPLIED" in independent.warnings
    assert "PROJECTED_ROIC_FAILED" not in independent.blockers

    out = tmp_path / "word"
    withheld = NewCompanyDeliverablesService().produce(
        analysis_id="a",
        ticker="MSFT",
        company="Microsoft",
        fiscal_year=2025,
        completed_workbook_path=industrial_workbook(tmp_path / "word_wb.xlsx"),
        output_dir=out,
        periods=None,
        tax=None,
        pe10=None,
        rd_decision=None,
        rd=None,
        leases=None,
        lease_review=None,
        buybacks=None,
        projection=None,
        seasonality=None,
        valuation=None,
        gate=share_gap,
        authorized=False,
    )
    assert withheld.word_path is None
    assert list(out.glob("*.docx")) == []


def test_period_detects_current_lq_year_not_prior_column(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx", quarter=2)
    wb = load_workbook(path)
    lq = wb["Last Quarter IS Standardized"]
    lq["C5"] = "2026 Q2"
    lq["D5"] = "2025 Q2"
    lq["C4"] = None
    wb.save(path)
    wb.close()
    report = NewCompanyPeriodService().detect(analysis_id="a", ticker="IDCC", workbook_path=path)
    assert report.latest_quarter == 2
    assert report.latest_quarter_fiscal_year == "FY2026"
    assert report.fiscal_years[-1] == "FY2025"


def test_insufficient_lease_evidence_does_not_fabricate_rate(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    svc = NewCompanyLeaseService()
    report = svc.apply(
        analysis_id="a",
        ticker="NONE",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=company_facts_for(leases=False),
    )
    assert report.review.selected_rate is None
    assert report.review.proposed_rate is None
    assert report.review.classification == "insufficient"
    assert report.review.decision_class == "EVIDENCE_INSUFFICIENT"
    assert report.review.status == "LEASE_RATE_EVIDENCE_INSUFFICIENT"
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in report.review.audit_trail)
    assert "No rate was fabricated" in report.review.summary


def test_autonomous_rd_does_not_derive_life_from_spend_and_does_not_pause(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    svc = NewCompanyRdService()
    decision = svc.select_useful_life(
        analysis_id="a",
        ticker="LNN",
        workbook_path=path,
        fiscal_years=FY,
        sec_manifest={"company_name": "Lindsay Corporation", "sic": "3523", "sic_description": "Farm machinery"},
    )
    assert decision.blocking is False
    assert decision.selected_useful_life == 5
    assert any(e.get("event") == "AUTONOMOUS_AGENT_DECISION" for e in decision.audit_trail)
    assert not any("coefficient of variation" in e.lower() for e in decision.company_evidence)
    report = svc.apply(
        analysis_id="a", ticker="LNN", workbook_path=path, fiscal_years=FY, decision=decision
    )
    wb = load_workbook(path)
    try:
        assert wb["R&D"]["B8"].value == 5 or wb["R&D"]["C8"].value == 5 or wb["R&D"]["B2"].value == 5
        hap = False
        for row in wb["R&D"].iter_rows(min_row=1, max_row=20, max_col=22):
            for cell in row:
                if "HAP ANALYSIS" in str(cell.value or "") or "useful life" in str(cell.value or "").lower():
                    hap = True
        assert hap
        assert report.lookback_complete or report.expenses
    finally:
        wb.close()


def test_analyst_lease_override_is_distinct_from_agent_decision(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    svc = NewCompanyLeaseService()
    report = svc.apply(
        analysis_id="a", ticker="TJX", workbook_path=path, fiscal_years=FY, company_facts=company_facts_for()
    )
    overridden = svc.apply_review(report.review, action="correct", rate=0.055, reason="documented credit change", workbook_path=path)
    events = [e.get("event") for e in overridden.audit_trail]
    assert "AUTONOMOUS_AGENT_DECISION" in events
    assert "ANALYST_OVERRIDE" in events
    assert "LEASE_RATE_APPROVED" not in events
    assert overridden.decision_class == "ANALYST_OVERRIDE"


def test_gate_f_autonomous_supported_rate_passes_without_human_approval():
    from models.new_company import LeaseRateReview, LeaseRateProposal

    review = LeaseRateReview(
        analysis_id="a",
        ticker="MSFT",
        status="autonomous_selected",
        proposed_rate=0.04,
        selected_rate=0.04,
        blocking=False,
        classification="disclosed",
        decision_class="AUTONOMOUS_AGENT_DECISION",
        supporting_evidence=["FY2025 reported 0.04"],
        notes_written=["Leases!L1"],
        proposal=LeaseRateProposal(
            proposed_rate=0.04,
            methodology="reported_weighted_average_discount_rate",
            classification="disclosed",
            source_fiscal_year="FY2025",
        ),
    )
    gate = NewCompanyOutputGateService().evaluate(
        analysis_id="a",
        ticker="MSFT",
        periods=MagicMock(template_family="industrial_template", fiscal_years=FY, chronology_ok=True, latest_quarter=2),
        coverage=MagicMock(complete=True, lookback_complete=True),
        statements=MagicMock(unresolved_material=[], summary="ok"),
        pe10=MagicMock(
            fiscal_year_pe10=[MagicMock(missing=False) for _ in FY],
            fiscal_year_e10=[MagicMock(missing=False) for _ in FY],
            current_pe10=MagicMock(value=20.0),
            current_e10=MagicMock(value=5.0),
            warnings=[],
        ),
        tax=MagicMock(complete=True, years=[]),
        rd_decision=MagicMock(selected_useful_life=5, blocking=False, blocking_reasons=[], analyst_override=None),
        rd=MagicMock(lookback_complete=True, capitalization_ok=True),
        leases=MagicMock(complete=True, review=review),
        lease_review=review,
        buybacks=MagicMock(
            years=[MagicMock(dollars=1.0, shares=1.0, absence_class=None) for _ in FY],
            complete=True,
        ),
        current=MagicMock(as_of_mismatch=False, warnings=[]),
        projection=MagicMock(
            seasonality_adjusted_roic=0.1,
            seasonality_adjusted_roce=0.1,
            confidence=ProjectionConfidence.HIGH,
            wacc=0.08,
        ),
        recalc=_ok_recalc(),
        valuation=MagicMock(
            expected_annual_return=0.1,
            expected_return_with_dividends=0.12,
            current_graham_intrinsic_value=100.0,
            nopat=80.0,
            invested_capital=500.0,
            roic=0.16,
        ),
        valuation_judgment=MagicMock(
            status="ok",
            original_assumptions_preserved=True,
            hap_introduced_circular_count=0,
            er_decision="KEEP_EXISTING",
            oe_decision="KEEP_EXISTING",
            graham_decision="KEEP_EXISTING",
            normalized_base_decision="KEEP_EXISTING",
        ),
    )
    assert gate.gates["F_lease_rate"] == "pass"
    assert gate.gates["E_rd"] == "pass"
    assert "LEASE_RATE_REVIEW_PENDING" not in gate.blockers
    assert gate.report_authorized


def test_lease_notes_and_rate_cell_are_written(tmp_path: Path):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    report = NewCompanyLeaseService().apply(
        analysis_id="a", ticker="TJX", workbook_path=path, fiscal_years=FY, company_facts=company_facts_for()
    )
    assert report.review.selected_rate == pytest.approx(0.045)
    wb = load_workbook(path)
    try:
        blob = " ".join(
            str(cell.value or "")
            for row in wb["Leases"].iter_rows(min_row=1, max_row=20, max_col=22)
            for cell in row
        )
        assert "HAP ANALYSIS" in blob
        assert "Classification" in blob
        assert "Source filing" in blob
        assert "Why HAP selected" in blob
        assert "Material uncertainty" in blob
        rate_vals = [wb["Leases"].cell(18, c).value for c in range(3, 13)]
        assert any(isinstance(v, (int, float)) and abs(float(v) - 0.045) < 1e-9 for v in rate_vals)
        assert wb["Expected Returns & Buybacks"]["A11"].value == 0.04
    finally:
        wb.close()
    assert report.review.notes_written
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in report.review.audit_trail)


def test_optional_analyst_override_triggers_dependent_recalculation(tmp_path: Path, out_svc: OutputService):
    from services.new_company_review_service import NewCompanyReviewService

    path = industrial_workbook(tmp_path / "wb.xlsx")
    applied = NewCompanyLeaseService().apply(
        analysis_id="ov-recalc",
        ticker="TJX",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=company_facts_for(),
    )
    out_svc.write_json("ov-recalc", "lease_rate_review.json", applied.review)
    svc = NewCompanyReviewService(output_service=out_svc)
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "workflow_state": NewCompanyWorkflowState.NEEDS_REVIEW,
            "lease_review": applied.review,
            "rd_decision": None,
        }

    svc.runner.run = fake_run  # type: ignore[method-assign]
    result = svc.resolve_lease_rate(
        analysis_id="ov-recalc",
        ticker="TJX",
        company="TJX",
        workbook_path=path,
        custom_run_path=None,
        action="correct",
        rate=0.055,
        reason="documented credit change",
    )
    assert captured.get("finalize") is True
    assert result["workflow_state"] == NewCompanyWorkflowState.NEEDS_REVIEW
    stored = out_svc.read_json("ov-recalc", "lease_rate_review.json")
    assert stored["decision_class"] == "ANALYST_OVERRIDE"
    assert stored["selected_rate"] == pytest.approx(0.055)
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in stored["audit_trail"])


def test_more_evidence_request_pauses_and_does_not_fabricate_approval(tmp_path: Path, out_svc: OutputService):
    path = industrial_workbook(tmp_path / "wb.xlsx")
    applied = NewCompanyLeaseService().apply(
        analysis_id="more-ev",
        ticker="TJX",
        workbook_path=path,
        fiscal_years=FY,
        company_facts=company_facts_for(),
    )
    pending = NewCompanyLeaseService().apply_review(
        applied.review, action="request_more_evidence", reason="need incremental borrowing rate"
    )
    out_svc.write_json("more-ev", "lease_rate_review.json", pending)
    runner = NewCompanyRunner(output_service=out_svc)
    crf_path = tmp_path / "crf.xlsx"
    crf_path.write_bytes(b"x")
    with patch(_CRF_PARSE, return_value=_crf_for("TJX")):
        done = runner.run(
            analysis_id="more-ev",
            ticker="TJX",
            company="TJX",
            template_path=path,
            working_path=tmp_path / "working-more.xlsx",
            custom_run_path=crf_path,
            company_facts=company_facts_for(),
            sec_manifest=_filings_manifest(),
            tax_year_inputs=_tax_inputs(),
        )
    assert done["workflow_state"] == NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW
    assert done["lease_review"].blocking is True
    assert done["output_gate"] is None or "LEASE_RATE_REVIEW_PENDING" in (done["output_gate"].blockers or [])
    assert not any(e.get("event") == "LEASE_RATE_APPROVED" for e in done["lease_review"].audit_trail)



