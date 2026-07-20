# Industrial Template Inventory (M1)

**Status:** Milestone M1 deliverable — documentation only (no mapping, no cell writes).  
**Template family:** Industrial Template **v27.6** (all four suite companies).  
**Suite:** AAPL, MSFT, AMZN, TJX ([`VALIDATION_SUITE.md`](../VALIDATION_SUITE.md)).  
**Inventoried (UTC):** 2026-07-20T21:01:57.917499+00:00

## Workbook overview

The Mode A Excel deliverable is the completed **Industrial Template**: a multi-sheet financial model with standardized income, balance sheet, and cash flow statements, last-quarter (LQ) packs, percentage views, a central Inputs bridge, ratio/metrics sheets, and valuation / expected-return outputs. Formulas link sheets; HAP must preserve formulas and only write into non-formula input cells (mapping begins in M2 after M1.5 classification).

| Ticker | Source file | Filename ver | Sheet ver | Sheets | SHA256 (first 16) | Size |
|--------|-------------|--------------|-----------|--------|-------------------|------|
| AAPL | `AAPL 2026 Q2 - Industrial Template v27.6.xlsx` | v27.6 | v27.7 | 24 | `5dabe993a0cfc571…` | 869048 |
| MSFT | `MSFT 2026 Q3 - Industrial Template v27.6.xlsx` | v27.6 | v27.7 | 24 | `7cb46a1ce0c3dc71…` | 880581 |
| AMZN | `AMZN 2026 Q1 - Industrial Template v27.6.xlsx` | v27.6 | v27.7 | 24 | `da07f3f6df171ff4…` | 870279 |
| TJX | `TJX 2026 Q4 - Industrial Template v27.6.xlsx` | v27.6 | v27.7 | 24 | `5ee113e5e01c80a2…` | 871543 |

**Sheet count (AAPL):** 24.  **Sheet names identical across suite:** YES.

## Sheet list and purpose

| # | Sheet | Visibility | Role hint (heuristic) | Purpose |
|---|-------|------------|------------------------|---------|
| 1 | `Balance Sheet - Standardized` | visible | data_heavy | Annual standardized balance sheet (primary BS data grid). |
| 2 | `BS%` | visible | formula_heavy | Balance sheet common-size percentages; formulas reference Balance Sheet - Standardized. |
| 3 | `Income - GAAP` | visible | data_heavy | Annual GAAP income statement (primary IS data grid). |
| 4 | `IS%` | visible | formula_heavy | Income statement common-size percentages; formulas reference Income - GAAP. |
| 5 | `Cash Flow - Standardized` | visible | data_heavy | Annual standardized cash flow statement (primary CF data grid). |
| 6 | `CF%` | visible | formula_heavy | Cash flow percentages / rates; formulas reference Cash Flow - Standardized. |
| 7 | `FCF` | visible | formula_heavy | Free cash flow build derived largely from Inputs / statements / Tax. |
| 8 | `Last Quarter BS Standardized` | visible | data_heavy | Quarterly standardized balance sheet pack (LQ). |
| 9 | `Last Quarter IS Standardized` | visible | hybrid | Quarterly standardized income statement pack (LQ). |
| 10 | `Last Quarter CF Standardized` | visible | data_heavy | Quarterly standardized cash flow pack (LQ). |
| 11 | `Last Quarter BS As Reported` | visible | data_heavy | Quarterly balance sheet as-reported (company presentation; variable depth). |
| 12 | `Last Quarter IS As Reported` | visible | data_heavy | Quarterly income as-reported (company presentation; variable depth). |
| 13 | `Last Quarter CF As Reported` | visible | data_heavy | Quarterly cash flow as-reported (company presentation; variable depth). |
| 14 | `DividendHelper` | visible | data_heavy | Dividend helper / support calculations for capital returns. |
| 15 | `Inputs` | visible | formula_heavy | Central bridge sheet: pulls statement lines and feeds ratios, tax, leases, R&D, metrics. |
| 16 | `IC & NOPAT & ROIC ` | visible | formula_heavy | Invested capital, NOPAT, and ROIC calculations (note trailing space in sheet name). |
| 17 | `Tax` | visible | formula_heavy | Tax / ETR support feeding IC/NOPAT and FCF. |
| 18 | `Leases` | visible | formula_heavy | Lease capitalization / adjustments feeding IC & ROIC. |
| 19 | `R&D` | visible | formula_heavy | R&D capitalization / adjustments feeding IC & ROIC. |
| 20 | `All Ratios` | visible | formula_heavy | Ratio library; primarily formula-driven from Inputs (and some statement refs). |
| 21 | `Final Metrics` | visible | formula_heavy | Summary metrics hub; feeds and is fed by Enterprise Value / Expected Returns. |
| 22 | `Expected Returns & Buybacks` | visible | hybrid | Expected returns and buyback analysis outputs. |
| 23 | `Enterprise Value` | visible | hybrid | Enterprise value build-up and related valuation outputs. |
| 24 | `Template Version` | visible | data_heavy | Template metadata / version control sheet. |

*Role hint is formula-ratio based (`data_heavy` / `hybrid` / `formula_heavy`) and will be refined into Data / Formula / Hybrid / Control / Meta in **M1.5**. It is not a write policy.*

## Relationships between sheets

See [`INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md`](INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md) for the formula-derived dependency graph. High-level flow (AAPL):

| From | To | Approx. cross-sheet formula refs |
|------|----|----------------------------------|
| `BS%` | `Balance Sheet - Standardized` | 1110 |
| `IS%` | `Income - GAAP` | 542 |
| `CF%` | `Cash Flow - Standardized` | 530 |
| `Inputs` | `Balance Sheet - Standardized` | 371 |
| `Final Metrics` | `Inputs` | 243 |
| `All Ratios` | `Inputs` | 177 |
| `Inputs` | `Income - GAAP` | 173 |
| `Tax` | `Inputs` | 150 |
| `Leases` | `Inputs` | 90 |
| `IC & NOPAT & ROIC ` | `Inputs` | 70 |
| `FCF` | `Inputs` | 50 |
| `Enterprise Value` | `Final Metrics` | 47 |
| `Inputs` | `Cash Flow - Standardized` | 40 |
| `IC & NOPAT & ROIC ` | `Leases` | 30 |
| `IC & NOPAT & ROIC ` | `R&D` | 30 |
| `R&D` | `Inputs` | 23 |
| `Final Metrics` | `Enterprise Value` | 23 |
| `FCF` | `Balance Sheet - Standardized` | 20 |
| `All Ratios` | `Balance Sheet - Standardized` | 20 |
| `Expected Returns & Buybacks` | `Final Metrics` | 16 |
| `Final Metrics` | `Income - GAAP` | 11 |
| `FCF` | `Tax` | 10 |
| `FCF` | `Income - GAAP` | 10 |
| `IC & NOPAT & ROIC ` | `Tax` | 10 |
| `Tax` | `IC & NOPAT & ROIC ` | 10 |

## Financial statement organization

### Annual vs percentage vs last-quarter packs

| Family | Annual / standardized | Common-size % | LQ standardized | LQ as-reported |
|--------|----------------------|---------------|-----------------|----------------|
| Income | `Income - GAAP` | `IS%` | `Last Quarter IS Standardized` | `Last Quarter IS As Reported` |
| Balance Sheet | `Balance Sheet - Standardized` | `BS%` | `Last Quarter BS Standardized` | `Last Quarter BS As Reported` |
| Cash Flow | `Cash Flow - Standardized` | `CF%` | `Last Quarter CF Standardized` | `Last Quarter CF As Reported` |

Additional derived sheets: `FCF`, `DividendHelper`, `Inputs`, `IC & NOPAT & ROIC ` (trailing space in name), `Tax`, `Leases`, `R&D`, `All Ratios`, `Final Metrics`, `Expected Returns & Buybacks`, `Enterprise Value`, `Template Version`.

Downstream analytics typically consume standardized/annual grids and LQ packs via `Inputs` → `All Ratios` / `Final Metrics` → valuation sheets. Exact edges are in the dependency map.

**Dimension note:** openpyxl reports `max_column` up to 16382 (`XFB`) on some sheets because of sparse dimension metadata. Inventory formula scans are capped at 100 columns; period headers observed for annual statements occupy roughly columns C–L for the FY window.

## Core statement detail — `Income - GAAP` (AAPL primary)

- Dimensions: 136 rows × 16382 cols
- Formula ratio: 0.0605 (54 formulas / 839 values in scanned used range)
- Freeze panes: `{'cell': 'C9'}`
- Merged cells: 0
- Tables: none
- Data validations: 0
- Hidden rows/cols: 2 / 1
- Sheet protection: {'sheet': False, 'password_set': False}

### Control / period header region

| Cell | Kind | Value | Formula? |
|------|------|-------|----------|
| `A1` | ticker_label | Ticker | False |
| `C1` | ticker_value | AAPL | False |
| `A2` | start_year_label | Start Year | False |
| `C2` | start_year_value | FY 2016 | False |
| `A3` | end_year_label | End Year | False |
| `C3` | end_year_value | FY 2025 | False |
| `A7` | units | In Millions of USD except Per Share | False |

### Period header rows (year/date-like)

- **Row 7:** C=FY 2016, D=FY 2017, E=FY 2018, F=FY 2019, G=FY 2020, H=FY 2021, I=FY 2022, J=FY 2023, K=FY 2024, L=FY 2025
- **Row 8:** C=2016-09-24 00:00:00, D=2017-09-30 00:00:00, E=2018-09-29 00:00:00, F=2019-09-28 00:00:00, G=2020-09-26 00:00:00, H=2021-09-25 00:00:00, I=2022-09-24 00:00:00, J=2023-09-30 00:00:00, K=2024-09-28 00:00:00, L=2025-09-27 00:00:00

### Hierarchy / labels (first 80)

| Row | Col | Indent | Role | Label |
|-----|-----|--------|------|-------|
| 1 | A | 0 | line_item | Ticker |
| 2 | A | 0 | line_item | Start Year |
| 3 | A | 0 | line_item | End Year |
| 7 | A | 0 | line_item | In Millions of USD except Per Share |
| 8 | C | 0 | line_item | 2016-09-24 00:00:00 |
| 9 | B | 0 | section_header | SALES_REV_TURN |
| 10 | B | 0 | section_header | IS_SALES_AND_SERVICES_REVENUES |
| 11 | B | 0 | section_header | IS_FINANCING_REVENUE |
| 12 | B | 0 | section_header | IS_OTHER_REVENUE |
| 13 | A | 0 | check | check |
| 14 | B | 0 | section_header | IS_COGS_TO_FE_AND_PP_AND_G |
| 15 | A | 0 | line_item | + Cost of Goods & Services |
| 16 | A | 0 | line_item | + Depreciation & Amortization - COGS |
| 17 | B | 0 | section_header | IS_COST_OF_FINANCING_REVENUE |
| 18 | A | 0 | check | check |
| 19 | A | 0 | line_item | Gross Profit |
| 20 | A | 0 | check | check |
| 21 | A | 0 | line_item | + Other Operating Income |
| 22 | A | 0 | line_item | - Operating Expenses |
| 23 | A | 0 | line_item | + Selling, General & Admin |
| 24 | A | 0 | line_item | + Selling & Marketing |
| 25 | B | 0 | section_header | IS_GENERAL_AND_ADMINISTRATIVE |
| 26 | B | 0 | section_header | IS_OPERATING_EXPENSES_R&D |
| 27 | A | 0 | line_item | + IS Depreciation & Amortization |
| 28 | B | 0 | section_header | OTHER_OPERATING_EXPENSES_RATIO |
| 29 | A | 0 | check | check |
| 30 | A | 0 | line_item | Operating Income (Loss) |
| 31 | A | 0 | check | check |
| 32 | A | 0 | line_item | - Non-Operating (Income) Loss |
| 33 | A | 0 | line_item | + Interest Expense, Net |
| 34 | A | 0 | line_item | + Interest Expense |
| 35 | A | 0 | line_item | - Interest Income |
| 36 | A | 0 | check | check |
| 37 | B | 0 | section_header | IS_OTHER_INVESTMENT_INCOME_LOSS |
| 38 | A | 0 | line_item | + Foreign Exch (Gain) Loss |
| 39 | A | 0 | line_item | + (Income) Loss from Affiliates |
| 40 | A | 0 | line_item | + Other Non-Op (Income) Loss |
| 41 | A | 0 | check | check |
| 42 | A | 0 | line_item | Pretax Income |
| 43 | A | 0 | check | check |
| 44 | A | 0 | line_item | - Income Tax Expense (Benefit) |
| 45 | B | 0 | section_header | IS_CURRENT_INCOME_TAX_BENEFIT |
| 46 | B | 0 | section_header | IS_DEFERRED_INCOME_TAX_BENEFIT |
| 47 | B | 0 | section_header | IS_TAX_VALN_ALLOWNCE_CREDITS |
| 48 | A | 0 | line_item | - (Income) Loss from Affiliates |
| 49 | A | 0 | check | check |
| 50 | A | 0 | line_item | Income (Loss) from Cont Ops |
| 51 | A | 0 | check | check |
| 52 | A | 0 | line_item | - Net Extraordinary Losses (Gains) |
| 53 | B | 0 | section_header | IS_DISCONTINUED_OPERATIONS |
| 54 | B | 0 | section_header | IS_EXTRAORD_ITEMS_&_ACCTG_CHNG |
| 55 | A | 0 | check | check |
| 56 | B | 0 | section_header | NI_INCLUDING_MINORITY_INT_RATIO |
| 57 | B | 0 | section_header | MIN_NONCONTROL_INTEREST_CREDITS |
| 58 | A | 0 | line_item | Net Income, GAAP |
| 59 | A | 0 | check | check |
| 60 | A | 0 | line_item | - Preferred Dividends |
| 61 | A | 0 | line_item | - Other Adjustments |
| 62 | A | 0 | line_item | Net Income Avail to Common, GAAP |
| 63 | A | 0 | check | check |
| 65 | A | 0 | line_item | Basic Weighted Avg Shares |
| 66 | A | 0 | line_item | Basic EPS, GAAP |
| 67 | B | 0 | section_header | IS_EARN_BEF_XO_ITEMS_PER_SH |
| 68 | A | 0 | line_item | Basic EPS from Cont Ops, Adjusted |
| 70 | A | 0 | line_item | Diluted Weighted Avg Shares |
| 71 | A | 0 | line_item | Diluted EPS, GAAP |
| 72 | A | 0 | line_item | Diluted EPS from Cont Ops |
| 73 | A | 0 | line_item | Diluted EPS from Cont Ops, Adjusted |
| 75 | A | 0 | line_item | Reference Items |
| 76 | A | 0 | section_header | EBITDA |
| 77 | A | 0 | section_header | EBITA |
| 78 | A | 0 | section_header | EBIT |
| 79 | A | 0 | ratio_like | Gross Margin |
| 80 | A | 0 | ratio_like | Operating Margin |
| 81 | A | 0 | ratio_like | Profit Margin |
| 82 | A | 0 | line_item | Dividends per Share |
| 83 | A | 0 | line_item | Depreciation Expense |
| 84 | B | 0 | section_header | BS_CURR_RENTAL_EXPENSE |
| 87 | A | 0 | line_item | 10-k Total Shares Buybacks (Millions) |
| 88 | B | 0 | section_header | BS_TOT_VAL_OF_SHARES_REPURCHASED |

_… 17 additional labels in JSON._

### Section boundaries

- R9: SALES_REV_TURN
- R10: IS_SALES_AND_SERVICES_REVENUES
- R11: IS_FINANCING_REVENUE
- R12: IS_OTHER_REVENUE
- R14: IS_COGS_TO_FE_AND_PP_AND_G
- R17: IS_COST_OF_FINANCING_REVENUE
- R25: IS_GENERAL_AND_ADMINISTRATIVE
- R26: IS_OPERATING_EXPENSES_R&D
- R28: OTHER_OPERATING_EXPENSES_RATIO
- R37: IS_OTHER_INVESTMENT_INCOME_LOSS
- R45: IS_CURRENT_INCOME_TAX_BENEFIT
- R46: IS_DEFERRED_INCOME_TAX_BENEFIT
- R47: IS_TAX_VALN_ALLOWNCE_CREDITS
- R53: IS_DISCONTINUED_OPERATIONS
- R54: IS_EXTRAORD_ITEMS_&_ACCTG_CHNG
- R56: NI_INCLUDING_MINORITY_INT_RATIO
- R57: MIN_NONCONTROL_INTEREST_CREDITS
- R67: IS_EARN_BEF_XO_ITEMS_PER_SH
- R76: EBITDA
- R77: EBITA
- R78: EBIT
- R84: BS_CURR_RENTAL_EXPENSE
- R88: BS_TOT_VAL_OF_SHARES_REPURCHASED
- R97: IS_DILUTED_EPS
- R98: IS_DILUTED_EPS
- R99: IS_DILUTED_EPS
- R100: IS_DILUTED_EPS
- R101: IS_DILUTED_EPS
- R102: IS_DILUTED_EPS
- R103: IS_DILUTED_EPS
- R104: IS_DILUTED_EPS
- R105: IS_DILUTED_EPS

### Check rows

- R13: check
- R18: check
- R20: check
- R29: check
- R31: check
- R36: check
- R41: check
- R43: check
- R49: check
- R51: check
- R55: check
- R59: check
- R63: check
- R93: Closing Price (Sanity check with Buyback Price)

### Units notes

- R7: In Millions of USD except Per Share
- R87: 10-k Total Shares Buybacks (Millions)

### Writable vs formula regions (sample line items)

Per-row samples of which columns hold values vs formulas (not a final write policy — that is M1.5):

- Row 1: values in ['D', 'M', 'N']; formulas in —
- Row 2: values in —; formulas in —
- Row 3: values in —; formulas in —
- Row 7: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 8: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 15: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 16: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 19: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in ['M']
- Row 21: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 22: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in ['M']
- Row 23: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 24: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —

## Core statement detail — `Balance Sheet - Standardized` (AAPL primary)

- Dimensions: 132 rows × 16382 cols
- Formula ratio: 0.0201 (25 formulas / 1219 values in scanned used range)
- Freeze panes: `{'cell': 'C9'}`
- Merged cells: 0
- Tables: none
- Data validations: 0
- Hidden rows/cols: 2 / 1
- Sheet protection: {'sheet': False, 'password_set': False}

### Control / period header region

| Cell | Kind | Value | Formula? |
|------|------|-------|----------|
| `A1` | ticker_label | Ticker | False |
| `C1` | ticker_value | AAPL | False |
| `A2` | start_year_label | Start Year | False |
| `C2` | start_year_value | FY 2016 | False |
| `A3` | end_year_label | End Year | False |
| `C3` | end_year_value | FY 2025 | False |
| `A7` | units | In Millions of USD except Per Share | False |

### Period header rows (year/date-like)

- **Row 4:** C=2016-09-24 00:00:00, D=2017-09-30 00:00:00, E=2018-09-29 00:00:00, F=2019-09-28 00:00:00, G=2020-09-26 00:00:00, H=2021-09-25 00:00:00, I=2022-09-24 00:00:00, J=2023-09-30 00:00:00, K=2024-09-28 00:00:00, L=2025-09-27 00:00:00
- **Row 5:** C=2016 A, D=2017 A, E=2018 A, F=2019 A, G=2020 A, H=2021 A, I=2022 A, J=2023 A, K=2024 A, L=2025 A
- **Row 7:** C=FY 2016, D=FY 2017, E=FY 2018, F=FY 2019, G=FY 2020, H=FY 2021, I=FY 2022, J=FY 2023, K=FY 2024, L=FY 2025
- **Row 8:** C=2016-09-24 00:00:00, D=2017-09-30 00:00:00, E=2018-09-29 00:00:00, F=2019-09-28 00:00:00, G=2020-09-26 00:00:00, H=2021-09-25 00:00:00, I=2022-09-24 00:00:00, J=2023-09-30 00:00:00, K=2024-09-28 00:00:00, L=2025-09-27 00:00:00

### Hierarchy / labels (first 80)

| Row | Col | Indent | Role | Label |
|-----|-----|--------|------|-------|
| 1 | A | 0 | line_item | Ticker |
| 2 | A | 0 | line_item | Start Year |
| 3 | A | 0 | line_item | End Year |
| 4 | C | 0 | line_item | 2016-09-24 00:00:00 |
| 5 | C | 0 | section_header | 2016 A |
| 7 | A | 0 | line_item | In Millions of USD except Per Share |
| 8 | C | 0 | line_item | 2016-09-24 00:00:00 |
| 9 | A | 0 | line_item | Total Assets |
| 10 | A | 0 | line_item | + Cash, Cash Equivalents & STI |
| 11 | A | 0 | line_item | + Cash & Cash Equivalents |
| 12 | B | 0 | section_header | BS_MKT_SEC_OTHER_ST_INVEST |
| 13 | A | 0 | check | check |
| 14 | A | 0 | line_item | + Accounts & Notes Receiv |
| 15 | B | 0 | section_header | BS_ACCTS_REC_EXCL_NOTES_REC |
| 16 | A | 0 | line_item | + Notes Receivable, Net |
| 17 | A | 0 | check | check |
| 19 | B | 0 | section_header | BS_UNBILLED_REVENUES |
| 20 | B | 0 | section_header | BS_INVENTORIES |
| 21 | B | 0 | section_header | INVTRY_RAW_MATERIALS |
| 22 | B | 0 | section_header | INVTRY_IN_PROGRESS |
| 23 | B | 0 | section_header | INVTRY_FINISHED_GOODS |
| 24 | A | 0 | line_item | + Other Inventory |
| 25 | A | 0 | check | check |
| 26 | B | 0 | section_header | OTHER_CURRENT_ASSETS_DETAILED |
| 27 | A | 0 | line_item | + Prepaid Expenses |
| 28 | A | 0 | line_item | + ST Derivative & Hedging Assets |
| 29 | B | 0 | section_header | BS_ASSETS_HELD_FOR_SALE_ST |
| 30 | B | 0 | section_header | BS_DEFERRED_TAX_ASSETS_ST |
| 31 | B | 0 | section_header | BS_TAXES_RECEIVABLE_SHORT_TERM |
| 32 | A | 0 | line_item | + Assets of Discontinued Operations ST |
| 33 | B | 0 | section_header | BS_OTHER_CUR_ASSET_LESS_PREPAY |
| 34 | A | 0 | check | check |
| 35 | A | 0 | line_item | Total Current Assets |
| 36 | A | 0 | check | check |
| 37 | A | 0 | line_item | + Property, Plant & Equip, Net (As Reported) |
| 38 | A | 0 | line_item | + Property, Plant & Equip, Net (Standardized) |
| 39 | A | 0 | line_item | + Property, Plant & Equip (Standardized) |
| 40 | A | 0 | line_item | - Accumulated Depreciation (Standardized) |
| 41 | A | 0 | line_item | Operating Leases |
| 42 | A | 0 | check | check |
| 43 | A | 0 | line_item | + LT Investments & Receivables |
| 44 | B | 0 | section_header | BS_LONG_TERM_INVESTMENTS |
| 45 | B | 0 | section_header | BS_LT_MARKETABLE_SECURITIES |
| 46 | A | 0 | check | check |
| 47 | B | 0 | section_header | BS_OTHER_ASSETS_DEF_CHRG_OTHER |
| 48 | A | 0 | line_item | + Total Intangible Assets |
| 49 | B | 0 | section_header | BS_GOODWILL |
| 50 | B | 0 | section_header | OTHER_INTANGIBLE_ASSETS_DETAILED |
| 51 | B | 0 | section_header | BS_PREPAID_EXPENSE_LT |
| 52 | B | 0 | section_header | BS_DEFERRED_TAX_ASSETS_LT |
| 53 | A | 0 | line_item | + LT Derivative & Hedging Assets |
| 54 | B | 0 | section_header | BS_PREPAID_PENSION_COSTS_LT |
| 55 | A | 0 | line_item | + Investments in Affiliates |
| 56 | A | 0 | line_item | + Assets of Discontinued Operations LT |
| 57 | B | 0 | section_header | OTHER_NONCURRENT_ASSETS_DETAILED |
| 58 | A | 0 | check | check |
| 59 | A | 0 | line_item | Total Noncurrent Assets |
| 60 | A | 0 | check | check |
| 61 | A | 0 | line_item | Total Assets |
| 62 | A | 0 | check | check |
| 63 | A | 0 | line_item | Liabilities & Shareholders' Equity |
| 64 | B | 0 | section_header | ACCT_PAYABLE_&_ACCRUALS_DETAILED |
| 65 | A | 0 | line_item | + Accounts Payable |
| 66 | B | 0 | section_header | BS_TAXES_PAYABLE |
| 67 | B | 0 | section_header | BS_INTEREST_&_DIVIDENDS_PAYABLE |
| 68 | A | 0 | line_item | + Other Payables & Accruals |
| 69 | A | 0 | check | check |
| 70 | B | 0 | section_header | BS_ST_BORROW |
| 71 | B | 0 | section_header | ST_CAPITALIZED_LEASE_LIABILITIES |
| 72 | B | 0 | section_header | ST_CAPITAL_LEASE_OBLIGATIONS |
| 73 | B | 0 | section_header | BS_ST_OPERATING_LEASE_LIABS |
| 74 | B | 0 | section_header | SHORT_TERM_DEBT_DETAILED |
| 75 | A | 0 | line_item | + Current Portion of LT Debt |
| 76 | A | 0 | check | check |
| 77 | B | 0 | section_header | OTHER_CURRENT_LIABS_SUB_DETAILED |
| 78 | A | 0 | line_item | + ST Deferred Revenue |
| 79 | B | 0 | section_header | BS_DERIVATIVE_&_HEDGING_LIABS_ST |
| 80 | A | 0 | line_item | + ST Deferred Tax Liabilities |
| 81 | A | 0 | line_item | + Liabilities of Discontinued Operations ST |
| 82 | B | 0 | section_header | OTHER_CURRENT_LIABS_DETAILED |

_… 50 additional labels in JSON._

### Section boundaries

- R5: 2016 A
- R12: BS_MKT_SEC_OTHER_ST_INVEST
- R15: BS_ACCTS_REC_EXCL_NOTES_REC
- R19: BS_UNBILLED_REVENUES
- R20: BS_INVENTORIES
- R21: INVTRY_RAW_MATERIALS
- R22: INVTRY_IN_PROGRESS
- R23: INVTRY_FINISHED_GOODS
- R26: OTHER_CURRENT_ASSETS_DETAILED
- R29: BS_ASSETS_HELD_FOR_SALE_ST
- R30: BS_DEFERRED_TAX_ASSETS_ST
- R31: BS_TAXES_RECEIVABLE_SHORT_TERM
- R33: BS_OTHER_CUR_ASSET_LESS_PREPAY
- R44: BS_LONG_TERM_INVESTMENTS
- R45: BS_LT_MARKETABLE_SECURITIES
- R47: BS_OTHER_ASSETS_DEF_CHRG_OTHER
- R49: BS_GOODWILL
- R50: OTHER_INTANGIBLE_ASSETS_DETAILED
- R51: BS_PREPAID_EXPENSE_LT
- R52: BS_DEFERRED_TAX_ASSETS_LT
- R54: BS_PREPAID_PENSION_COSTS_LT
- R57: OTHER_NONCURRENT_ASSETS_DETAILED
- R64: ACCT_PAYABLE_&_ACCRUALS_DETAILED
- R66: BS_TAXES_PAYABLE
- R67: BS_INTEREST_&_DIVIDENDS_PAYABLE
- R70: BS_ST_BORROW
- R71: ST_CAPITALIZED_LEASE_LIABILITIES
- R72: ST_CAPITAL_LEASE_OBLIGATIONS
- R73: BS_ST_OPERATING_LEASE_LIABS
- R74: SHORT_TERM_DEBT_DETAILED
- R77: OTHER_CURRENT_LIABS_SUB_DETAILED
- R79: BS_DERIVATIVE_&_HEDGING_LIABS_ST
- R82: OTHER_CURRENT_LIABS_DETAILED
- R86: BS_LT_BORROW
- R87: LONG_TERM_BORROWINGS_DETAILED
- R88: LT_CAPITALIZED_LEASE_LIABILITIES
- R89: LT_CAPITAL_LEASE_OBLIGATIONS
- R90: BS_LT_OPERATING_LEASE_LIABS
- R92: OTHER_NONCUR_LIABS_SUB_DETAILED
- R93: BS_ACCRUED_LIABILITIES

### Check rows

- R13: check
- R17: check
- R25: check
- R34: check
- R36: check
- R42: check
- R46: check
- R58: check
- R60: check
- R62: check
- R69: check
- R76: check
- R83: check
- R85: check
- R91: check
- R103: check
- R105: check
- R107: check
- R112: check
- R119: check
- R121: check
- R122: check

### Units notes

- R7: In Millions of USD except Per Share

### Writable vs formula regions (sample line items)

Per-row samples of which columns hold values vs formulas (not a final write policy — that is M1.5):

- Row 1: values in ['D', 'M', 'N']; formulas in —
- Row 2: values in —; formulas in —
- Row 3: values in —; formulas in —
- Row 4: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'N', 'O']; formulas in —
- Row 7: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 8: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 9: values in —; formulas in —
- Row 10: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in ['M']
- Row 11: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 14: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in ['M']
- Row 16: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 24: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —

## Core statement detail — `Cash Flow - Standardized` (AAPL primary)

- Dimensions: 82 rows × 16382 cols
- Formula ratio: 0.009 (7 formulas / 773 values in scanned used range)
- Freeze panes: `{'cell': 'C9'}`
- Merged cells: 0
- Tables: none
- Data validations: 0
- Hidden rows/cols: 2 / 1
- Sheet protection: {'sheet': False, 'password_set': False}

### Control / period header region

| Cell | Kind | Value | Formula? |
|------|------|-------|----------|
| `A1` | ticker_label | Ticker | False |
| `C1` | ticker_value | AAPL | False |
| `A2` | start_year_label | Start Year | False |
| `C2` | start_year_value | FY 2016 | False |
| `A3` | end_year_label | End Year | False |
| `C3` | end_year_value | FY 2025 | False |
| `A7` | units | In Millions of USD except Per Share | False |

### Period header rows (year/date-like)

- **Row 7:** C=FY 2016, D=FY 2017, E=FY 2018, F=FY 2019, G=FY 2020, H=FY 2021, I=FY 2022, J=FY 2023, K=FY 2024, L=FY 2025
- **Row 8:** C=2016-09-24 00:00:00, D=2017-09-30 00:00:00, E=2018-09-29 00:00:00, F=2019-09-28 00:00:00, G=2020-09-26 00:00:00, H=2021-09-25 00:00:00, I=2022-09-24 00:00:00, J=2023-09-30 00:00:00, K=2024-09-28 00:00:00, L=2025-09-27 00:00:00

### Hierarchy / labels (first 80)

| Row | Col | Indent | Role | Label |
|-----|-----|--------|------|-------|
| 1 | A | 0 | line_item | Ticker |
| 2 | A | 0 | line_item | Start Year |
| 3 | A | 0 | line_item | End Year |
| 7 | A | 0 | line_item | In Millions of USD except Per Share |
| 8 | C | 0 | line_item | 2016-09-24 00:00:00 |
| 9 | A | 0 | line_item | Cash from Operating Activities |
| 10 | A | 0 | line_item | + Net Income |
| 11 | A | 0 | line_item | + CF Depreciation & Amortization |
| 12 | B | 0 | section_header | NON_CASH_ITEMS_DETAILED |
| 13 | B | 0 | section_header | CF_STOCK_BASED_COMPENSATION |
| 14 | A | 0 | line_item | + Deferred Income Taxes |
| 15 | B | 0 | section_header | OTHER_NON_CASH_ADJ_LESS_DETAILED |
| 16 | A | 0 | check | check |
| 17 | A | 0 | line_item | + Chg in Non-Cash Work Cap |
| 18 | A | 0 | line_item | + (Inc) Dec in Accts Receiv |
| 19 | A | 0 | line_item | + (Inc) Dec in Inventories |
| 20 | B | 0 | section_header | CF_CHANGE_IN_ACCOUNTS_PAYABLE |
| 21 | B | 0 | section_header | INC_DEC_IN_OT_OP_AST_LIAB_DETAIL |
| 22 | A | 0 | check | check |
| 23 | A | 0 | line_item | + Net Operating Cash From Disc Ops |
| 24 | A | 0 | line_item | Cash from Operating Activities |
| 25 | A | 0 | check | check |
| 26 | A | 0 | line_item | Cash from Investing Activities |
| 27 | B | 0 | section_header | CHG_IN_FXD_&_INTANG_AST_DETAILED |
| 28 | B | 0 | section_header | DISP_FXD_&_INTANGIBLES_DETAILED |
| 29 | B | 0 | section_header | CF_DISPOSAL_OF_FIXED_PROD_ASSETS |
| 30 | B | 0 | section_header | CF_DISPOSAL_OF_INTANGIBLE_ASSETS |
| 31 | B | 0 | section_header | ACQUIS_FXD_&_INTANG_DETAILED |
| 32 | B | 0 | section_header | CF_PURCHASE_OF_FIXED_PROD_ASSETS |
| 33 | B | 0 | section_header | CF_ACQUISITION_OF_INTANG_ASSETS |
| 34 | A | 0 | check | check |
| 35 | A | 0 | line_item | + Net Change in LT Investment |
| 36 | A | 0 | line_item | + Dec in LT Investment |
| 37 | A | 0 | line_item | + Inc in LT Investment |
| 38 | A | 0 | check | check |
| 39 | B | 0 | section_header | CF_NT_CSH_RCVD_PD_FOR_ACQUIS_DIV |
| 40 | A | 0 | line_item | + Cash from Divestitures |
| 41 | B | 0 | section_header | CF_CASH_FOR_ACQUIS_SUBSIDIARIES |
| 42 | B | 0 | section_header | CF_CASH_FOR_JOINT_VENTURES_ASSOC |
| 43 | A | 0 | check | check |
| 44 | A | 0 | line_item | + Other Investing Activities |
| 45 | A | 0 | line_item | + Net Investing Cash From Disc Ops |
| 46 | A | 0 | line_item | Cash from Investing Activities |
| 47 | A | 0 | check | check |
| 48 | A | 0 | line_item | Cash from Financing Activities |
| 49 | A | 0 | line_item | + Dividends Paid |
| 50 | B | 0 | section_header | PROC_FR_REPAYMNTS_BOR_DETAILED |
| 51 | B | 0 | section_header | CF_NET_CHG_IN_ST_DBT_&_CPTL_LEAS |
| 52 | B | 0 | section_header | CF_PROC_LT_DEBT_&_CAPITAL_LEASE |
| 53 | B | 0 | section_header | CF_PYMT_LT_DEBT_&_CAPITAL_LEASE |
| 54 | A | 0 | check | check |
| 55 | A | 0 | line_item | + Cash (Repurchase) of Equity |
| 56 | A | 0 | line_item | + Increase in Capital Stock |
| 57 | A | 0 | line_item | + Decrease in Capital Stock |
| 58 | A | 0 | check | check |
| 59 | B | 0 | section_header | CF_OTHER_FINANCING_ACT_EXCL_FX |
| 60 | A | 0 | line_item | + Net Financing Cash From Disc Ops |
| 61 | A | 0 | line_item | Cash from Financing Activities |
| 62 | A | 0 | check | check |
| 63 | A | 0 | line_item | Effect of Foreign Exchange Rates |
| 65 | A | 0 | line_item | Net Changes in Cash |
| 66 | B | 0 | section_header | CF_CASH_&_CASH_EQUIV_BEG_BAL |
| 67 | B | 0 | section_header | CF_CASH_&_CASH_EQUIV_END_BAL |
| 68 | A | 0 | check | check |
| 69 | B | 0 | section_header | CF_CASH_PAID_FOR_TAX |
| 70 | B | 0 | section_header | CF_ACT_CASH_PAID_FOR_INT_DEBT |
| 72 | A | 0 | line_item | Reference Items |
| 73 | B | 0 | section_header | CF_FREE_CASH_FLOW |
| 74 | A | 0 | line_item | Free Cash Flow to Firm |
| 75 | A | 0 | line_item | Free Cash Flow to Equity |
| 76 | A | 0 | line_item | Free Cash Flow per Basic Share |
| 77 | A | 0 | line_item | Price to Free Cash Flow |

### Section boundaries

- R12: NON_CASH_ITEMS_DETAILED
- R13: CF_STOCK_BASED_COMPENSATION
- R15: OTHER_NON_CASH_ADJ_LESS_DETAILED
- R20: CF_CHANGE_IN_ACCOUNTS_PAYABLE
- R21: INC_DEC_IN_OT_OP_AST_LIAB_DETAIL
- R27: CHG_IN_FXD_&_INTANG_AST_DETAILED
- R28: DISP_FXD_&_INTANGIBLES_DETAILED
- R29: CF_DISPOSAL_OF_FIXED_PROD_ASSETS
- R30: CF_DISPOSAL_OF_INTANGIBLE_ASSETS
- R31: ACQUIS_FXD_&_INTANG_DETAILED
- R32: CF_PURCHASE_OF_FIXED_PROD_ASSETS
- R33: CF_ACQUISITION_OF_INTANG_ASSETS
- R39: CF_NT_CSH_RCVD_PD_FOR_ACQUIS_DIV
- R41: CF_CASH_FOR_ACQUIS_SUBSIDIARIES
- R42: CF_CASH_FOR_JOINT_VENTURES_ASSOC
- R50: PROC_FR_REPAYMNTS_BOR_DETAILED
- R51: CF_NET_CHG_IN_ST_DBT_&_CPTL_LEAS
- R52: CF_PROC_LT_DEBT_&_CAPITAL_LEASE
- R53: CF_PYMT_LT_DEBT_&_CAPITAL_LEASE
- R59: CF_OTHER_FINANCING_ACT_EXCL_FX
- R66: CF_CASH_&_CASH_EQUIV_BEG_BAL
- R67: CF_CASH_&_CASH_EQUIV_END_BAL
- R69: CF_CASH_PAID_FOR_TAX
- R70: CF_ACT_CASH_PAID_FOR_INT_DEBT
- R73: CF_FREE_CASH_FLOW

### Check rows

- R16: check
- R22: check
- R25: check
- R34: check
- R38: check
- R43: check
- R47: check
- R54: check
- R58: check
- R62: check
- R68: check

### Units notes

- R7: In Millions of USD except Per Share

### Writable vs formula regions (sample line items)

Per-row samples of which columns hold values vs formulas (not a final write policy — that is M1.5):

- Row 1: values in ['D', 'M', 'N']; formulas in —
- Row 2: values in —; formulas in —
- Row 3: values in —; formulas in —
- Row 7: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 8: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 9: values in —; formulas in ['M']
- Row 10: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 11: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 14: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 17: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 18: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —
- Row 19: values in ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L']; formulas in —

## Named ranges

| Name | Attr / destinations |
|------|---------------------|
| `IQ_CH` | `110000` |
| `IQ_CQ` | `5000` |
| `IQ_CY` | `10000` |
| `IQ_DAILY` | `500000` |
| `IQ_FH` | `100000` |
| `IQ_FQ` | `500` |
| `IQ_FWD_CY` | `10001` |
| `IQ_FWD_CY1` | `10002` |
| `IQ_FWD_CY2` | `10003` |
| `IQ_FWD_FY` | `1001` |
| `IQ_FWD_FY1` | `1002` |
| `IQ_FWD_FY2` | `1003` |
| `IQ_FWD_Q` | `501` |
| `IQ_FWD_Q1` | `502` |
| `IQ_FWD_Q2` | `503` |
| `IQ_FY` | `1000` |
| `IQ_LATESTK` | `1000` |
| `IQ_LATESTQ` | `500` |
| `IQ_LTM` | `2000` |
| `IQ_LTMMONTH` | `120000` |
| `IQ_MONTH` | `15000` |
| `IQ_NTM` | `6000` |
| `IQ_TODAY` | `0` |
| `IQ_WEEK` | `50000` |
| `IQ_YTD` | `3000` |
| `IQ_YTDMONTH` | `130000` |
| `SplitsByYear` | `DividendHelper!$K$1:$M$12` |
| `SpreadsheetBuilder_1` | `#REF!` |
| `SpreadsheetBuilder_10` | `'Income - GAAP'!$D$106:$E$114` |
| `SpreadsheetBuilder_2` | `#REF!` |
| `SpreadsheetBuilder_3` | `#REF!` |
| `SpreadsheetBuilder_4` | `#REF!` |
| `SpreadsheetBuilder_5` | `#REF!` |
| `SpreadsheetBuilder_6` | `#REF!` |
| `SpreadsheetBuilder_7` | `'Last Quarter BS Standardized'!#REF!` |
| `SpreadsheetBuilder_8` | `'Last Quarter BS Standardized'!#REF!` |
| `SpreadsheetBuilder_9` | `'Income - GAAP'!$D$106:$E$108` |

## Hidden sheets

_No hidden / veryHidden sheets in AAPL inventory._

## Freeze panes / merged cells / tables / validation / CF (summary)

| Sheet | Freeze | Merged | Tables | DV | CF rules | Hidden rows | Hidden cols | Protected |
|-------|--------|--------|--------|----|----------|-------------|-------------|-----------|
| `Balance Sheet - Standardized` | `{'cell': 'C9'}` | 0 | 0 | 0 | 45 | 2 | 1 | False |
| `BS%` | `{'cell': 'C9'}` | 0 | 0 | 0 | 0 | 2 | 1 | False |
| `Income - GAAP` | `{'cell': 'C9'}` | 0 | 0 | 0 | 29 | 2 | 1 | False |
| `IS%` | `{'cell': 'C9'}` | 0 | 0 | 0 | 0 | 2 | 1 | False |
| `Cash Flow - Standardized` | `{'cell': 'C9'}` | 0 | 0 | 0 | 25 | 2 | 1 | False |
| `CF%` | `{'cell': 'C9'}` | 0 | 0 | 0 | 0 | 2 | 1 | False |
| `FCF` | `{'cell': 'B5'}` | 0 | 0 | 0 | 0 | 0 | 0 | False |
| `Last Quarter BS Standardized` | `None` | 7 | 0 | 0 | 45 | 4 | 1 | False |
| `Last Quarter IS Standardized` | `{'cell': 'C10'}` | 4 | 0 | 0 | 47 | 4 | 1 | False |
| `Last Quarter CF Standardized` | `{'cell': 'C11'}` | 1 | 0 | 0 | 21 | 4 | 1 | False |
| `Last Quarter BS As Reported` | `None` | 0 | 0 | 0 | 0 | 0 | 1 | False |
| `Last Quarter IS As Reported` | `None` | 0 | 0 | 0 | 0 | 0 | 1 | False |
| `Last Quarter CF As Reported` | `None` | 0 | 0 | 0 | 0 | 0 | 1 | False |
| `DividendHelper` | `None` | 0 | 0 | 0 | 0 | 0 | 0 | False |
| `Inputs` | `{'cell': 'B3'}` | 0 | 0 | 0 | 0 | 0 | 0 | False |
| `IC & NOPAT & ROIC ` | `{'cell': 'B2'}` | 0 | 0 | 0 | 2 | 0 | 0 | False |
| `Tax` | `{'cell': 'C3'}` | 0 | 0 | 0 | 0 | 0 | 1 | False |
| `Leases` | `{'cell': 'B2'}` | 0 | 0 | 0 | 0 | 0 | 0 | False |
| `R&D` | `{'cell': 'B2'}` | 0 | 0 | 0 | 0 | 0 | 0 | False |
| `All Ratios` | `{'cell': 'B2'}` | 0 | 0 | 0 | 12 | 0 | 0 | False |
| `Final Metrics` | `{'cell': 'B3'}` | 0 | 0 | 0 | 7 | 0 | 0 | False |
| `Expected Returns & Buybacks` | `None` | 1 | 0 | 0 | 0 | 0 | 0 | False |
| `Enterprise Value` | `None` | 2 | 0 | 0 | 0 | 0 | 0 | False |
| `Template Version` | `None` | 0 | 0 | 0 | 0 | 0 | 0 | False |

## Suite consistency (AAPL vs MSFT / AMZN / TJX)

- Sheet names identical (order + spelling): **True**
- Dependency edge *types* identical across suite (75 shared pairs; no ticker-only edges).
- Named ranges: no name-set differences vs AAPL.

### What differs (expected company data, not template structure)

Core statement **row counts match** across the suite (Income 97 labels, BS 130, CF 72 in the inventory scan). Observed 'label diffs' are almost entirely:

1. **Fiscal period end dates** in header rows (Apple Sept YE, Microsoft June YE, Amazon Dec YE, TJX late-Jan YE).
2. **FY window shift for TJX** — period headers show FY 2017–2026 vs FY 2016–2025 on AAPL/MSFT/AMZN.
3. Occasional **year-embedded text** (e.g. TJX `Retained Earnings FY 2016` vs AAPL `… FY 2015`).
4. **As-reported LQ sheet depths** differ (`Last Quarter * As Reported` max_row varies by ticker) — company presentation length, not a different template family.
5. Role-hint on `Last Quarter IS Standardized` is hybrid for AAPL vs data_heavy for others (fill/formula mix differs; structure same).

**Structural conclusion for M1.5/M2:** The v27.6 sheet skeleton is shared. Map by **row labels + period column headers**, not by assuming identical date cells or identical as-reported LQ depth. Do not treat AAPL fiscal dates as universal.

Raw mismatch summaries (includes period dates):
- `Income - GAAP` vs MSFT: counts AAPL=97 MSFT=97; recorded mismatches=1
- `Income - GAAP` vs AMZN: counts AAPL=97 AMZN=97; recorded mismatches=1
- `Income - GAAP` vs TJX: counts AAPL=97 TJX=97; recorded mismatches=2
- `Balance Sheet - Standardized` vs MSFT: counts AAPL=130 MSFT=130; recorded mismatches=2
- `Balance Sheet - Standardized` vs AMZN: counts AAPL=130 AMZN=130; recorded mismatches=2
- `Balance Sheet - Standardized` vs TJX: counts AAPL=130 TJX=130; recorded mismatches=3
- `Cash Flow - Standardized` vs MSFT: counts AAPL=72 MSFT=72; recorded mismatches=1
- `Cash Flow - Standardized` vs AMZN: counts AAPL=72 AMZN=72; recorded mismatches=1
- `Cash Flow - Standardized` vs TJX: counts AAPL=72 TJX=72; recorded mismatches=1

- Per-sheet structural field diffs: 4 sheets (mostly LQ as-reported depth / role_hint) — details in JSON.

Full machine diff: [`suite_structural_diff.json`](suite_structural_diff.json).

## Unusual observations

- **Control value cells:** On annual IS/BS/CF, labels are `A1:A3`; values are **`C1:C3`** (Ticker / Start Year / End Year). Column B is typically blank and may be hidden.
- **Version string mismatch:** Filenames use `v27.6`; `Template Version!A2` observed as `v27.7` on AAPL — treat both as identity signals for regression.
- **Trailing space** in sheet name `IC & NOPAT & ROIC ` must be preserved exactly.
- **Hidden structure on Income - GAAP (AAPL):** rows 4–5 hidden; column B hidden; freeze at `C9`.
- **Named ranges:** CapIQ-style `IQ_*` period codes plus helpers; broken `SpreadsheetBuilder_*` names with `#REF!` may exist — do not rely on them for HAP fill.
- **AAPL:** volatile-formula samples=0; external-ref samples=0
- **MSFT:** volatile-formula samples=0; external-ref samples=0
- **AMZN:** volatile-formula samples=0; external-ref samples=0
- **TJX:** volatile-formula samples=0; external-ref samples=0

See also [`INDUSTRIAL_TEMPLATE_RISK_LOG.md`](INDUSTRIAL_TEMPLATE_RISK_LOG.md).

## Machine artifacts

| File | Role |
|------|------|
| `industrial_template_v27_inventory.json` | Full inventory (all 4) |
| `industrial_template_v27_fingerprint.json` | Compact regression fingerprints |
| `suite_structural_diff.json` | Cross-ticker structural diff |
| `INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md` | Formula dependency graph |
| `INDUSTRIAL_TEMPLATE_RISK_LOG.md` | Mapping risks |

## Definition of done (M1)

- [x] Human documentation of the Industrial Template
- [x] Machine JSON inventory
- [x] Dependency map
- [x] Risk log
- [x] Regression fingerprints for future template versions
- [x] Suite validation AAPL / MSFT / AMZN / TJX
- [ ] **Stopped** — M1.5 / M2 not started (awaiting review)
