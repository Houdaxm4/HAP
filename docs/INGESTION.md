# HAP v1 Ingestion Layer

This document describes the HAP v1 ingestion architecture restored in Sprint 5.

## Product inputs (external interface)

Users provide:

1. **Prefilled Workbook** (`.xlsx`) — company-specific analysis template
2. **Custom_Run_Filter** (`.xlsx`) — Bloomberg-derived proprietary analytics workbook

Users do **not** provide worksheet/cell mapping CSV files. Mapping tables were an internal engineering artifact and are not part of the HAP v1 product specification.

## Bloomberg Custom_Run_Filter workbook structure

All companies (AAPL, MSFT, AMZN, TJX, …) use the same standardized workbook layout:

| Worksheet | Layout | Content |
|-----------|--------|---------|
| Metadata | Key-value (Field \| Value) | Ticker, Company Name, Currency, Fiscal Year End |
| Market Data | Key-value | Share Price, Market Cap, Shares Outstanding |
| Historical Metrics | Time series (Metric \| FY20xx …) | Historical financial and operating metrics |
| Proprietary Metrics | Time series | Bloomberg proprietary analytics |
| Valuation Metrics | Time series | P/E, EV/EBITDA, etc. |
| Quality Metrics | Metric \| Score | Business quality scores |
| Assumptions | Key-value | Terminal growth, WACC, etc. |

## Ingestion flow

```
Prefilled Workbook (.xlsx)
        +
Bloomberg Custom_Run_Filter (.xlsx)
        +
SEC Filings
        +
Market Data (from Custom_Run)
        ↓
Validation (CustomRunValidator)
        ↓
CompanyFinancialModelBuilder
        ↓
PrefilledWorkbookMapper (internal fill plan — not user-facing)
        ↓
Fill Workbook + Provenance
        ↓
Validate Workbook
        ↓
AnalysisEngine.run()
```

## Domain models

- **`CustomRunData`** — parsed Bloomberg workbook (`ingestion/models/custom_run_data.py`)
- **`CompanyFinancialModel`** — canonical merged model (`ingestion/models/company_financial_model.py`)
- **`InternalFillTarget`** — internal-only cell fill plan (`ingestion/prefilled_workbook_mapper.py`)

## Golden rules

1. SEC remains the source of truth for financial statement facts.
2. Custom_Run provides proprietary analytics and historical metrics — never recompute proprietary metrics.
3. Never overwrite formulas in the prefilled workbook.
4. Every populated value must have provenance.

## Code layout

```
backend/ingestion/
  custom_run_parser.py          # Bloomberg workbook parser
  custom_run_validator.py       # Structure + content validation
  custom_run_schema.py          # Worksheet names and required fields
  company_financial_model_builder.py
  analysis_engine.py            # Entry point after ingestion
  prefilled_workbook_mapper.py  # Internal fill plan (implementation detail)
  models/
    custom_run_data.py
    company_financial_model.py
```

## Pipeline stages

1. `parse_workbook` — prefilled workbook structure
2. `parse_custom_run` — Bloomberg workbook → `CustomRunData`
3. `validate_custom_run` — specification validation
4. `fetch_sec_filings` — SEC EDGAR data
5. `build_financial_model` — `CompanyFinancialModelBuilder`
6. `fill_workbook` — internal mapper + provenance
7. `validate_workbook` — discrepancy report
8. `run_analysis` — `AnalysisEngine.run()`
