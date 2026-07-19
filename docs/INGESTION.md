# HAP v1 Ingestion Layer

This document describes the HAP v1 ingestion architecture.

## Product inputs (external interface)

Users provide:

1. **Prefilled Workbook** (`.xlsx`) — company-specific analysis template
2. **Custom_Run_Filter** (`.xlsx`) — Bloomberg-derived proprietary analytics workbook

Users do **not** provide worksheet/cell mapping CSV files. Mapping tables were an internal engineering artifact and are not part of the HAP v1 product specification.

## Bloomberg Custom_Run_Filter workbook structure

The parser does **not** assume worksheet names or a standardized layout.

The production workbook is the contract. The parser adapts to it using an evidence-based profile reverse-engineered from the real AAPL workbook.

See:

- `docs/CUSTOM_RUN_REVERSE_ENGINEERING.md` — reverse-engineering status and unblock steps
- `backend/fixtures/production/README.md` — where to commit production workbooks

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
5. Never invent workbook layout — generalize only from evidence across company workbooks.

## Code layout

```
backend/ingestion/
  workbook_introspector.py      # Reverse-engineer actual worksheet layout
  production_workbook_profile.py
  custom_run_parser.py          # Profile-driven Bloomberg workbook parser
  custom_run_validator.py       # Structure + content validation
  custom_run_schema.py          # Semantic sections (not worksheet names)
  company_financial_model_builder.py
  analysis_engine.py            # Entry point after ingestion
  prefilled_workbook_mapper.py  # Internal fill plan (implementation detail)
  models/
    custom_run_data.py
    company_financial_model.py
backend/scripts/
  inspect_custom_run_workbook.py
backend/fixtures/production/
  custom_run_filter_aapl.xlsx           # REQUIRED production workbook
  custom_run_filter_aapl.profile.json   # Evidence-based parser profile
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
