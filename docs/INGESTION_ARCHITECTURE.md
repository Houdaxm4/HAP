# HAP v1 Ingestion Architecture

## Purpose

Restore the product ingestion layer so it matches the HAP Master Specification.
This document describes **inputs, parsing, validation, and model merge only**.
It does not change investment methodology, scoring, or AnalysisEngine logic.

## Product inputs

```
Prefilled Workbook (.xlsx)
  +
Bloomberg Custom_Run_Filter (.xlsx)
  +
SEC Filings (companyfacts / filing set)
  +
Market Data (from Custom_Run and/or adapters)

        ↓
    Validation
        ↓
CompanyFinancialModelBuilder
        ↓
AnalysisEngine.run()
```

| Input | Role |
|-------|------|
| **Prefilled Workbook** | Industrial analyst template (structure, formulas). Copied forward as the completed workbook artifact. |
| **Custom_Run_Filter** | Bloomberg-derived proprietary analytics workbook (same structure for all companies). Imported, never recalculated. |
| **SEC filings / companyfacts** | Source of truth for statement facts (IS / BS / CF). |
| **Market data** | Live price, market cap, EV, etc. Prefer Custom_Run summary / scalars when present. |

Users never supply a worksheet/cell/concept/period **mapping CSV**. That format is not a HAP v1 product input.

## Custom_Run_Filter shape

Every company uses the same Bloomberg export layout:

1. **Ticker sheet** (e.g. `AAPL`)
   - Meta block (company, ticker, …)
   - Period axes (dates, fiscal quarters, fiscal years)
   - Historical series
   - Scalar proprietary metrics (PE10, WACC, expected returns, quality scores, …)
2. **`Summary` sheet**
   - Wide header row + one data row (~111 fields)

Parser: `backend/services/custom_run_service.py`  
Domain model: `backend/models/custom_run.py` → `CustomRunData`

`CustomRunData` sections:

- `metadata`, `summary`
- `market_data`, `historical_metrics`
- `proprietary_metrics`, `valuation_metrics`, `quality_metrics`
- `assumptions`, `scalars`, `periods`

## Pipeline stages

1. **parse_workbook** — inspect prefilled template structure  
2. **parse_custom_run** — Bloomberg workbook → `CustomRunData` → `custom_run_data.json`  
3. **fetch_sec_filings** — resolve CIK, filings manifest, companyfacts  
4. **fill_workbook** — copy template; record SEC + Custom_Run provenance (internal detail)  
5. **validate_workbook** — Custom_Run structural / field validation + light SEC coverage checks  
6. **run_analysis** — `CompanyFinancialModelBuilder` (SEC facts + CustomRunData) → `AnalysisEngine.run()`

## Builder merge rules

`CompanyFinancialModelBuilder.build(..., company_facts=, custom_run=)`:

1. Statement series from SEC `companyfacts` (never invented).
2. Overlay market / valuation / proprietary metrics from `CustomRunData`.
3. Proprietary ratios go to `workbook_metrics` / metadata for comparison — HAP does not recompute them.

Golden rule: **Never recompute proprietary metrics from Custom_Run_Filter.**

## Validation (Custom_Run)

`backend/services/custom_run_validation.py` checks:

- Required worksheets / Summary presence (via parse)
- Expected structure (period and series counts)
- Required proprietary / summary fields
- Missing historical coverage
- Malformed numerics
- Inconsistent tickers / metadata

It does **not** validate `worksheet` / `cell` / `concept` / `period` mapping columns.

## Internal vs external

| External (product) | Internal (implementation only) |
|--------------------|--------------------------------|
| `Custom_Run_Filter.xlsx` | Optional SEC→template cell routing for fill / provenance |
| Prefilled Industrial Template | Provenance JSON / completed workbook copy |

Internal routing must never be required as a user upload.
