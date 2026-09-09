"""Deterministic Inputs-tab mappings: tax, PE10, current_data."""

from __future__ import annotations

from workbook_mapping.explicit_mappings import ANNUAL_PERIOD_COLS
from workbook_mapping.mapping_schema import MappingEntry, TimeDimension

_INPUTS_PERIOD_VALIDATION = [
    "cfm_period_must_match_column_fy_token",
    "value_numeric_or_null",
    "null_skips_write",
]


def inputs_mappings() -> list[MappingEntry]:
    """CFM → Industrial Template Inputs sinks (writable bridge cells)."""
    entries: list[MappingEntry] = []

    # --- PE10 / E10 history (Bloomberg CRF) ---
    entries.append(
        MappingEntry(
            mapping_id="inputs.pe10",
            cfm_path="inputs.pe10",
            metric_name="PE10",
            sheet="Inputs",
            row=57,
            columns=list(ANNUAL_PERIOD_COLS),
            expected_label="PE10",
            label_cell="A57",
            time_dimension=TimeDimension.ANNUAL_FY,
            unit="ratio",
            data_type="float",
            transformation=None,
            validation_rules=list(_INPUTS_PERIOD_VALIDATION),
            write_priority=5,
            fill_priority="P0",
            notes="inputs_sink:pe10 bloomberg_custom_run",
        )
    )
    entries.append(
        MappingEntry(
            mapping_id="inputs.e10",
            cfm_path="inputs.e10",
            metric_name="E10",
            sheet="Inputs",
            row=58,
            columns=list(ANNUAL_PERIOD_COLS),
            expected_label="E10",
            label_cell="A58",
            time_dimension=TimeDimension.ANNUAL_FY,
            unit="USD",
            data_type="float",
            transformation=None,
            validation_rules=list(_INPUTS_PERIOD_VALIDATION),
            write_priority=6,
            fill_priority="P0",
            notes="inputs_sink:e10 bloomberg_custom_run",
        )
    )

    # --- Current data scalars ---
    current_points = [
        ("inputs.current_price", "inputs.current_price", "Current Price", "B63", 63, "market_internet"),
        ("inputs.current_e10", "inputs.current_e10", "Current E10", "B64", 64, "bloomberg_custom_run"),
        ("inputs.current_pe10", "inputs.current_pe10", "Current PE10", "B65", 65, "bloomberg_custom_run"),
        (
            "inputs.current_max_pe10",
            "inputs.current_max_pe10",
            "Current Max PE10 to Enter (Lowest PE10 or 7PE10)",
            "B66",
            66,
            "bloomberg_custom_run",
        ),
        (
            "inputs.max_price_to_buy",
            "inputs.max_price_to_buy",
            "Max Current Price to Buy",
            "B67",
            67,
            "bloomberg_custom_run",
        ),
        ("inputs.exit_price_1", "inputs.exit_price_1", "1st Exit Price", "B68", 68, "bloomberg_custom_run"),
        (
            "inputs.expected_return_current",
            "inputs.expected_return_current",
            "Expected Return @ Current Price",
            "B69",
            69,
            "bloomberg_custom_run",
        ),
        (
            "inputs.expected_return_div_current",
            "inputs.expected_return_div_current",
            "Expected Return Price Plus Dividends - Given Current Price",
            "B70",
            70,
            "bloomberg_custom_run",
        ),
        (
            "inputs.expected_return_div_max_entry",
            "inputs.expected_return_div_max_entry",
            "Expected Return Price Plus Dividends - Given Max Entry Price",
            "B71",
            71,
            "bloomberg_custom_run",
        ),
        (
            "inputs.pe10_percentile",
            "inputs.pe10_percentile",
            "Current PE10 Percentile",
            "B72",
            72,
            "bloomberg_custom_run",
        ),
        (
            "inputs.current_eps_3y_10y_growth",
            "inputs.current_eps_3y_10y_growth",
            "Current 3 year EPS 10 years Av Growth",
            "B73",
            73,
            "bloomberg_custom_run",
        ),
        (
            "inputs.current_eps_growth_direction",
            "inputs.current_eps_growth_direction",
            "Current 3 year EPS 10 years Av Growth Direction",
            "B74",
            74,
            "bloomberg_custom_run",
        ),
        (
            "inputs.current_revenue_3y_10y_growth",
            "inputs.current_revenue_3y_10y_growth",
            "Current 3 year Revenue 10 years Av Growth",
            "B75",
            75,
            "bloomberg_custom_run",
        ),
    ]
    for mid, path, label, cell, row, src in current_points:
        entries.append(
            MappingEntry(
                mapping_id=mid,
                cfm_path=path,
                metric_name=label,
                sheet="Inputs",
                row=row,
                columns=["B"],
                expected_label=label.split("(")[0].strip() if "Current PE10 Percentile" not in label else label,
                label_cell=f"A{row}",
                time_dimension=TimeDimension.POINT,
                unit=(
                    "flag"
                    if "Direction" in label
                    else "ratio"
                    if any(tok in label for tok in ("PE10", "Return", "E10", "Growth"))
                    else "USD"
                ),
                data_type="str" if "Direction" in label else "float",
                transformation=None,
                validation_rules=["value_numeric_or_null", "null_skips_write"],
                write_priority=7,
                fill_priority="P0",
                notes=f"inputs_sink:current_data source={src} cell={cell}",
            )
        )

    # --- Tax table (SEC 10-K), USD millions mode ---
    entries.append(
        MappingEntry(
            mapping_id="inputs.tax_unit_flag",
            cfm_path="inputs.tax_unit_flag",
            metric_name="Tax Unit Flag",
            sheet="Inputs",
            row=106,
            columns=["E"],
            expected_label=None,
            label_cell=None,
            time_dimension=TimeDimension.POINT,
            unit="flag",
            data_type="int",
            transformation=None,
            validation_rules=["null_skips_write"],
            write_priority=3,
            fill_priority="P0",
            notes="inputs_sink:tax set millions(0) when filling SEC absolute tax",
        )
    )
    tax_rows = [
        ("inputs.tax_federal", "inputs.tax_federal", "Federal Tax", 107),
        ("inputs.tax_state", "inputs.tax_state", "State Taxes", 108),
        ("inputs.tax_foreign", "inputs.tax_foreign", "Foreign Taxes", 109),
        ("inputs.tax_expense", "inputs.tax_expense", "Income Tax Expense", 112),
    ]
    for mid, path, label, row in tax_rows:
        entries.append(
            MappingEntry(
                mapping_id=mid,
                cfm_path=path,
                metric_name=label,
                sheet="Inputs",
                row=row,
                columns=list(ANNUAL_PERIOD_COLS),
                expected_label=label,
                label_cell=f"A{row}",
                time_dimension=TimeDimension.ANNUAL_FY,
                unit="USD_millions",
                data_type="float",
                transformation="divide_by_1_000_000",
                validation_rules=list(_INPUTS_PERIOD_VALIDATION),
                write_priority=4,
                fill_priority="P0",
                notes="inputs_sink:tax sec_edgar_10k",
            )
        )
    return entries
