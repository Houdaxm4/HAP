# CFM ↔ Workbook Mapping Specification (M2)

**Generated:** 2026-07-30T19:22:21.507240+00:00  
**Baseline:** AAPL  
**Manifest:** `C:/Users/G/HAP/docs/workbook_mapping/Workbook_Manifest.json` (schema 1.0.0)  

This specification is **deterministic**. Every row is an explicit binding. No Excel writes occur in M2. Consumers must only target `Writable Input` cells.

## Coverage snapshot

- CFM statement metrics mapped: **23/25** (92.0%)
- Writable cells explained: **100.0%** (unexplained=0)
- Mapped writable cells: 240
- Intentionally empty: 460
- Unsupported: 229
- Future feature: 1303

## Explicit mappings

| ID | CFM path | Sheet | Row | Columns | Label | Unit | Transform | Priority |
|----|----------|-------|-----|---------|-------|------|-----------|----------|
| `ctrl.ticker.Income - GAAP` | `ticker` | `Income - GAAP` | 1 | C | Ticker | text | — | 10 |
| `ctrl.start_year.Income - GAAP` | `metadata.template_start_year` | `Income - GAAP` | 2 | C | Start Year | fy_label | format_fy_token | 11 |
| `ctrl.ticker.Balance Sheet - Standardized` | `ticker` | `Balance Sheet - Standardized` | 1 | C | Ticker | text | — | 11 |
| `ctrl.end_year.Income - GAAP` | `metadata.template_end_year` | `Income - GAAP` | 3 | C | End Year | fy_label | format_fy_token | 12 |
| `ctrl.start_year.Balance Sheet - Standardized` | `metadata.template_start_year` | `Balance Sheet - Standardized` | 2 | C | Start Year | fy_label | format_fy_token | 12 |
| `ctrl.ticker.Cash Flow - Standardized` | `ticker` | `Cash Flow - Standardized` | 1 | C | Ticker | text | — | 12 |
| `ctrl.end_year.Balance Sheet - Standardized` | `metadata.template_end_year` | `Balance Sheet - Standardized` | 3 | C | End Year | fy_label | format_fy_token | 13 |
| `ctrl.start_year.Cash Flow - Standardized` | `metadata.template_start_year` | `Cash Flow - Standardized` | 2 | C | Start Year | fy_label | format_fy_token | 13 |
| `ctrl.end_year.Cash Flow - Standardized` | `metadata.template_end_year` | `Cash Flow - Standardized` | 3 | C | End Year | fy_label | format_fy_token | 14 |
| `is.revenue` | `income_statement.revenue` | `Income - GAAP` | 9 | C–L (10) | Revenue | USD_millions | divide_by_1_000_000 | 20 |
| `is.cost_of_revenue` | `income_statement.cost_of_revenue` | `Income - GAAP` | 14 | C–L (10) | - Cost of Revenue | USD_millions | divide_by_1_000_000 | 21 |
| `is.gross_profit` | `income_statement.gross_profit` | `Income - GAAP` | 19 | C–L (10) | Gross Profit | USD_millions | divide_by_1_000_000 | 22 |
| `is.operating_income` | `income_statement.operating_income` | `Income - GAAP` | 30 | C–L (10) | Operating Income (Loss) | USD_millions | divide_by_1_000_000 | 23 |
| `is.interest_expense` | `income_statement.interest_expense` | `Income - GAAP` | 34 | C–L (10) | + Interest Expense | USD_millions | divide_by_1_000_000 | 24 |
| `is.tax_expense` | `income_statement.tax_expense` | `Income - GAAP` | 44 | C–L (10) | - Income Tax Expense (Benefit) | USD_millions | divide_by_1_000_000 | 25 |
| `is.net_income` | `income_statement.net_income` | `Income - GAAP` | 58 | C–L (10) | Net Income, GAAP | USD_millions | divide_by_1_000_000 | 26 |
| `is.diluted_eps` | `income_statement.diluted_eps` | `Income - GAAP` | 71 | C–L (10) | Diluted EPS, GAAP | USD_millions | — | 27 |
| `is.ebitda` | `income_statement.ebitda` | `Income - GAAP` | 76 | C–L (10) | EBITDA | USD_millions | divide_by_1_000_000 | 28 |
| `is.ebit` | `income_statement.ebit` | `Income - GAAP` | 78 | C–L (10) | EBIT | USD_millions | divide_by_1_000_000 | 29 |
| `bs.cash` | `balance_sheet.cash` | `Balance Sheet - Standardized` | 11 | C–L (10) | + Cash & Cash Equivalents | USD_millions | divide_by_1_000_000 | 30 |
| `bs.current_assets` | `balance_sheet.current_assets` | `Balance Sheet - Standardized` | 35 | C–L (10) | Total Current Assets | USD_millions | divide_by_1_000_000 | 31 |
| `bs.total_assets` | `balance_sheet.total_assets` | `Balance Sheet - Standardized` | 61 | C–L (10) | Total Assets | USD_millions | divide_by_1_000_000 | 32 |
| `bs.current_liabilities` | `balance_sheet.current_liabilities` | `Balance Sheet - Standardized` | 84 | C–L (10) | Total Current Liabilities | USD_millions | divide_by_1_000_000 | 33 |
| `bs.total_liabilities` | `balance_sheet.total_liabilities` | `Balance Sheet - Standardized` | 106 | C–L (10) | Total Liabilities | USD_millions | divide_by_1_000_000 | 34 |
| `bs.shareholders_equity` | `balance_sheet.shareholders_equity` | `Balance Sheet - Standardized` | 118 | C–L (10) | Total Equity | USD_millions | divide_by_1_000_000 | 35 |
| `cf.operating_cash_flow` | `cash_flow_statement.operating_cash_flow` | `Cash Flow - Standardized` | 24 | C–L (10) | Cash from Operating Activities | USD_millions | divide_by_1_000_000 | 40 |
| `cf.capital_expenditures` | `cash_flow_statement.capital_expenditures` | `Cash Flow - Standardized` | 32 | C–L (10) | + Acq of Fixed Prod Assets | USD_millions | divide_by_1_000_000 | 41 |
| `cf.investing_cash_flow` | `cash_flow_statement.investing_cash_flow` | `Cash Flow - Standardized` | 46 | C–L (10) | Cash from Investing Activities | USD_millions | divide_by_1_000_000 | 42 |
| `cf.dividends` | `cash_flow_statement.dividends` | `Cash Flow - Standardized` | 49 | C–L (10) | + Dividends Paid | USD_millions | divide_by_1_000_000 | 43 |
| `cf.share_repurchases` | `cash_flow_statement.share_repurchases` | `Cash Flow - Standardized` | 55 | C–L (10) | + Cash (Repurchase) of Equity | USD_millions | divide_by_1_000_000 | 44 |
| `cf.financing_cash_flow` | `cash_flow_statement.financing_cash_flow` | `Cash Flow - Standardized` | 61 | C–L (10) | Cash from Financing Activities | USD_millions | divide_by_1_000_000 | 45 |
| `cf.free_cash_flow` | `cash_flow_statement.free_cash_flow` | `Cash Flow - Standardized` | 73 | C–L (10) | Free Cash Flow | USD_millions | divide_by_1_000_000 | 46 |

## Period column maps

### `Income - GAAP` (header row 7)

| Column | FY token |
|--------|----------|
| C | `FY2016` |
| D | `FY2017` |
| E | `FY2018` |
| F | `FY2019` |
| G | `FY2020` |
| H | `FY2021` |
| I | `FY2022` |
| J | `FY2023` |
| K | `FY2024` |
| L | `FY2025` |

### `Balance Sheet - Standardized` (header row 7)

| Column | FY token |
|--------|----------|
| C | `FY2016` |
| D | `FY2017` |
| E | `FY2018` |
| F | `FY2019` |
| G | `FY2020` |
| H | `FY2021` |
| I | `FY2022` |
| J | `FY2023` |
| K | `FY2024` |
| L | `FY2025` |

### `Cash Flow - Standardized` (header row 7)

| Column | FY token |
|--------|----------|
| C | `FY2016` |
| D | `FY2017` |
| E | `FY2018` |
| F | `FY2019` |
| G | `FY2020` |
| H | `FY2021` |
| I | `FY2022` |
| J | `FY2023` |
| K | `FY2024` |
| L | `FY2025` |

## Assumptions

- Mappings are explicit constants; no fuzzy label matching at runtime.
- Only Writable Input cells may be targets; validated against Workbook_Manifest.json.
- AAPL baseline period window FY2016–FY2025 maps to columns C–L; other tickers may shift FY labels — M5 aligns periods.
- CFM absolute USD amounts use transformation divide_by_1_000_000 except diluted_eps.
- capital_expenditures maps explicitly to '+ Acq of Fixed Prod Assets' (row 32) as documented proxy.
- total_debt and invested_capital remain unmapped in v0.1 with recorded reasons.
- Check rows are Intentionally Empty (never write).
- Analytics/extra rows are Unsupported; remaining statement detail is Future Feature.
- M2 does not write Excel and does not invent values.
