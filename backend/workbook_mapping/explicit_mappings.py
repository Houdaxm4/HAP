"""Explicit CFM ↔ Industrial Template row bindings (deterministic — no fuzzy match).

Row numbers and expected A-column labels are taken from Workbook_Manifest.json
(M1.5) for the AAPL baseline Industrial Template. The builder validates that:
  - expected_label matches Helper cell A{row}
  - target cells are classification Writable Input
"""

from __future__ import annotations

from workbook_mapping.mapping_schema import MappingEntry, TimeDimension

# Period body columns on annual statement sheets (AAPL baseline FY2016–FY2025).
ANNUAL_PERIOD_COLS = ["C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]

# Canonical FY tokens matching Start/End Year window on AAPL baseline template.
ANNUAL_PERIOD_FY_TOKENS = [
    "FY2016",
    "FY2017",
    "FY2018",
    "FY2019",
    "FY2020",
    "FY2021",
    "FY2022",
    "FY2023",
    "FY2024",
    "FY2025",
]

COMMON_SERIES_VALIDATION = [
    "manifest_cell_is_writable_input",
    "label_cell_matches_expected",
    "cfm_period_must_match_column_fy_token",
    "value_numeric_or_null",
    "null_skips_write",
]

SCALE_TO_MILLIONS = "divide_by_1_000_000"  # CFM stores absolute USD; template is millions


def _series(
    mapping_id: str,
    cfm_path: str,
    metric_name: str,
    sheet: str,
    row: int,
    expected_label: str,
    *,
    write_priority: int,
    transformation: str | None = SCALE_TO_MILLIONS,
    notes: str | None = None,
    extra_validation: list[str] | None = None,
) -> MappingEntry:
    rules = list(COMMON_SERIES_VALIDATION)
    if extra_validation:
        rules.extend(extra_validation)
    return MappingEntry(
        mapping_id=mapping_id,
        cfm_path=cfm_path,
        metric_name=metric_name,
        sheet=sheet,
        row=row,
        columns=list(ANNUAL_PERIOD_COLS),
        expected_label=expected_label,
        label_cell=f"A{row}",
        time_dimension=TimeDimension.ANNUAL_FY,
        unit="USD_millions",
        data_type="float",
        transformation=transformation,
        validation_rules=rules,
        write_priority=write_priority,
        fill_priority="P0",
        notes=notes,
    )


def explicit_mappings() -> list[MappingEntry]:
    """Return the full explicit mapping table (controls + statement series)."""
    entries: list[MappingEntry] = []

    # --- Controls (same on all three annual sheets) ---
    for sheet, prio_base in (
        ("Income - GAAP", 10),
        ("Balance Sheet - Standardized", 11),
        ("Cash Flow - Standardized", 12),
    ):
        entries.append(
            MappingEntry(
                mapping_id=f"ctrl.ticker.{sheet}",
                cfm_path="ticker",
                metric_name="Ticker",
                sheet=sheet,
                row=1,
                columns=["C"],
                expected_label="Ticker",
                label_cell="A1",
                time_dimension=TimeDimension.CONTROL,
                unit="text",
                data_type="string",
                transformation=None,
                validation_rules=[
                    "manifest_cell_is_writable_input",
                    "label_cell_matches_expected",
                    "value_non_empty_string",
                ],
                write_priority=prio_base,
                fill_priority="P0",
                notes="Control value C1",
            )
        )
        entries.append(
            MappingEntry(
                mapping_id=f"ctrl.start_year.{sheet}",
                cfm_path="metadata.template_start_year",
                metric_name="Start Year",
                sheet=sheet,
                row=2,
                columns=["C"],
                expected_label="Start Year",
                label_cell="A2",
                time_dimension=TimeDimension.CONTROL,
                unit="fy_label",
                data_type="string",
                transformation="format_fy_token",  # e.g. FY2016
                validation_rules=[
                    "manifest_cell_is_writable_input",
                    "label_cell_matches_expected",
                    "matches_period_map_first_column",
                ],
                write_priority=prio_base + 1,
                fill_priority="P0",
                notes="Control value C2; must align with period column map",
            )
        )
        entries.append(
            MappingEntry(
                mapping_id=f"ctrl.end_year.{sheet}",
                cfm_path="metadata.template_end_year",
                metric_name="End Year",
                sheet=sheet,
                row=3,
                columns=["C"],
                expected_label="End Year",
                label_cell="A3",
                time_dimension=TimeDimension.CONTROL,
                unit="fy_label",
                data_type="string",
                transformation="format_fy_token",
                validation_rules=[
                    "manifest_cell_is_writable_input",
                    "label_cell_matches_expected",
                    "matches_period_map_last_column",
                ],
                write_priority=prio_base + 2,
                fill_priority="P0",
                notes="Control value C3; must align with period column map",
            )
        )

    # --- Income statement ---
    is_sheet = "Income - GAAP"
    entries += [
        _series("is.revenue", "income_statement.revenue", "Revenue", is_sheet, 9, "Revenue", write_priority=20),
        _series(
            "is.cost_of_revenue",
            "income_statement.cost_of_revenue",
            "Cost of Revenue",
            is_sheet,
            14,
            "- Cost of Revenue",
            write_priority=21,
        ),
        _series(
            "is.gross_profit",
            "income_statement.gross_profit",
            "Gross Profit",
            is_sheet,
            19,
            "Gross Profit",
            write_priority=22,
        ),
        _series(
            "is.operating_income",
            "income_statement.operating_income",
            "Operating Income",
            is_sheet,
            30,
            "Operating Income (Loss)",
            write_priority=23,
        ),
        _series(
            "is.interest_expense",
            "income_statement.interest_expense",
            "Interest Expense",
            is_sheet,
            34,
            "+ Interest Expense",
            write_priority=24,
        ),
        _series(
            "is.tax_expense",
            "income_statement.tax_expense",
            "Tax Expense",
            is_sheet,
            44,
            "- Income Tax Expense (Benefit)",
            write_priority=25,
        ),
        _series(
            "is.net_income",
            "income_statement.net_income",
            "Net Income",
            is_sheet,
            58,
            "Net Income, GAAP",
            write_priority=26,
        ),
        _series(
            "is.diluted_eps",
            "income_statement.diluted_eps",
            "Diluted EPS",
            is_sheet,
            71,
            "Diluted EPS, GAAP",
            write_priority=27,
            transformation=None,  # per-share, not millions
            notes="Per-share metric; do not scale by 1e6",
            extra_validation=["unit_is_per_share"],
        ),
        _series(
            "is.ebitda",
            "income_statement.ebitda",
            "EBITDA",
            is_sheet,
            76,
            "EBITDA",
            write_priority=28,
        ),
        _series(
            "is.ebit",
            "income_statement.ebit",
            "EBIT",
            is_sheet,
            78,
            "EBIT",
            write_priority=29,
        ),
    ]

    # --- Balance sheet ---
    bs_sheet = "Balance Sheet - Standardized"
    entries += [
        _series(
            "bs.cash",
            "balance_sheet.cash",
            "Cash",
            bs_sheet,
            11,
            "+ Cash & Cash Equivalents",
            write_priority=30,
        ),
        _series(
            "bs.current_assets",
            "balance_sheet.current_assets",
            "Current Assets",
            bs_sheet,
            35,
            "Total Current Assets",
            write_priority=31,
        ),
        _series(
            "bs.total_assets",
            "balance_sheet.total_assets",
            "Total Assets",
            bs_sheet,
            61,
            "Total Assets",
            write_priority=32,
            notes="Uses foot Total Assets row 61 (not section header row 9)",
        ),
        _series(
            "bs.current_liabilities",
            "balance_sheet.current_liabilities",
            "Current Liabilities",
            bs_sheet,
            84,
            "Total Current Liabilities",
            write_priority=33,
        ),
        _series(
            "bs.total_liabilities",
            "balance_sheet.total_liabilities",
            "Total Liabilities",
            bs_sheet,
            106,
            "Total Liabilities",
            write_priority=34,
        ),
        _series(
            "bs.shareholders_equity",
            "balance_sheet.shareholders_equity",
            "Shareholders Equity",
            bs_sheet,
            118,
            "Total Equity",
            write_priority=35,
        ),
    ]

    # --- Cash flow ---
    cf_sheet = "Cash Flow - Standardized"
    entries += [
        _series(
            "cf.operating_cash_flow",
            "cash_flow_statement.operating_cash_flow",
            "Operating Cash Flow",
            cf_sheet,
            24,
            "Cash from Operating Activities",
            write_priority=40,
            notes="Uses total OCF row 24 (not section header row 9)",
        ),
        _series(
            "cf.capital_expenditures",
            "cash_flow_statement.capital_expenditures",
            "Capital Expenditures",
            cf_sheet,
            32,
            "+ Acq of Fixed Prod Assets",
            write_priority=41,
            notes="Explicit proxy: template has no Capex label; maps to Acq of Fixed Prod Assets",
            extra_validation=["explicit_proxy_mapping"],
        ),
        _series(
            "cf.investing_cash_flow",
            "cash_flow_statement.investing_cash_flow",
            "Investing Cash Flow",
            cf_sheet,
            46,
            "Cash from Investing Activities",
            write_priority=42,
        ),
        _series(
            "cf.dividends",
            "cash_flow_statement.dividends",
            "Dividends",
            cf_sheet,
            49,
            "+ Dividends Paid",
            write_priority=43,
        ),
        _series(
            "cf.share_repurchases",
            "cash_flow_statement.share_repurchases",
            "Share Repurchases",
            cf_sheet,
            55,
            "+ Cash (Repurchase) of Equity",
            write_priority=44,
        ),
        _series(
            "cf.financing_cash_flow",
            "cash_flow_statement.financing_cash_flow",
            "Financing Cash Flow",
            cf_sheet,
            61,
            "Cash from Financing Activities",
            write_priority=45,
        ),
        _series(
            "cf.free_cash_flow",
            "cash_flow_statement.free_cash_flow",
            "Free Cash Flow",
            cf_sheet,
            73,
            "Free Cash Flow",
            write_priority=46,
        ),
    ]

    return entries


# CFM series fields that exist on CompanyFinancialModel statements.
CFM_STATEMENT_METRICS: list[str] = [
    "income_statement.revenue",
    "income_statement.cost_of_revenue",
    "income_statement.gross_profit",
    "income_statement.operating_income",
    "income_statement.ebit",
    "income_statement.ebitda",
    "income_statement.interest_expense",
    "income_statement.tax_expense",
    "income_statement.net_income",
    "income_statement.diluted_eps",
    "balance_sheet.cash",
    "balance_sheet.current_assets",
    "balance_sheet.total_assets",
    "balance_sheet.current_liabilities",
    "balance_sheet.total_liabilities",
    "balance_sheet.total_debt",
    "balance_sheet.shareholders_equity",
    "balance_sheet.invested_capital",
    "cash_flow_statement.operating_cash_flow",
    "cash_flow_statement.capital_expenditures",
    "cash_flow_statement.free_cash_flow",
    "cash_flow_statement.dividends",
    "cash_flow_statement.share_repurchases",
    "cash_flow_statement.financing_cash_flow",
    "cash_flow_statement.investing_cash_flow",
]

# Plus controls treated as mappable CFM-adjacent fields
CFM_CONTROL_METRICS: list[str] = [
    "ticker",
    "metadata.template_start_year",
    "metadata.template_end_year",
]

UNMAPPED_CFM_EXPLICIT: list[tuple[str, str, str]] = [
    (
        "balance_sheet.total_debt",
        "No single Total Debt line on Balance Sheet - Standardized",
        "Future: composite ST Debt row 70 + LT Debt row 86 (not in M2 v0.1 single-cell map)",
    ),
    (
        "balance_sheet.invested_capital",
        "Invested Capital is not a line on Balance Sheet - Standardized (lives on IC & NOPAT & ROIC sheet, Read-only)",
        "Leave to Excel IC sheet; do not write statement grid",
    ),
]

# Deterministic disposition catalogs (row-level) for writable cells not covered by mappings.
CHECK_ROWS: dict[str, frozenset[int]] = {
    "Income - GAAP": frozenset(
        {13, 18, 20, 29, 31, 36, 41, 43, 49, 51, 55, 59, 63}
    ),
    "Balance Sheet - Standardized": frozenset(
        {13, 17, 25, 34, 36, 42, 46, 58, 60, 62, 69, 76, 83, 85, 91, 103, 105, 107, 112, 119, 121, 122}
    ),
    "Cash Flow - Standardized": frozenset({16, 22, 25, 34, 38, 43, 47, 54, 58, 62, 68}),
}

UNSUPPORTED_ROWS: dict[str, frozenset[int]] = {
    # Margins, buyback analytics, bloomberg extras, treasury — not CFM statement fields
    "Income - GAAP": frozenset(range(79, 107)),
    # Cost of debt / WACC / rental schedule — valuation helpers, not statement CFM
    "Balance Sheet - Standardized": frozenset(range(124, 133)),
    # FCFF/FCFE/ratio lines derived in-template
    "Cash Flow - Standardized": frozenset({74, 75, 76, 77}),
}
