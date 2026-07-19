# Custom_Run_Filter Reverse Engineering

**Status:** BLOCKED — production AAPL workbook not in repository  
**Branch:** `cursor/production-workbook-parser-145e`  
**Date:** 2026-07-19

## Objective

Reverse-engineer the **real** Bloomberg `Custom_Run_Filter` workbook used by HAP and implement a parser that adapts to that layout. The workbook is the contract. The parser must not invent worksheet names, standardized sheet layouts, or synthetic fixtures.

## Current blocker

The production AAPL workbook is **not available** in this cloud environment or in the GitHub repository.

| Location checked | Result |
|------------------|--------|
| `backend/fixtures/production/custom_run_filter_aapl.xlsx` | Missing |
| `backend/storage/uploads/` | Empty (gitignored runtime dir) |
| All git branches | No production `.xlsx` committed |
| Only xlsx in repo | `backend/fixtures/custom_run_filter_aapl.example.xlsx` — **synthetic, rejected** |

Until the real workbook is committed, reverse-engineering cannot be completed.

## What was rejected in Sprint 5

Sprint 5 invented a standardized 7-worksheet format:

- Metadata
- Market Data
- Historical Metrics
- Proprietary Metrics
- Valuation Metrics
- Quality Metrics
- Assumptions

That layout is **not** evidence-based. It must not be used as the parser contract.

## What HAP specs say the workbook contains

From the HAP Master Specification (not layout):

- PE10 / E10
- Tax data
- Current valuation metrics
- Growth metrics
- Historical valuation statistics
- Expected returns
- Other proprietary Bloomberg metrics

These are **content categories**, not worksheet names.

## Required deliverables (pending production workbook)

### 1. Reverse-engineering evidence

For the production AAPL workbook, document:

- Worksheet names (exact Bloomberg export names)
- Row layout per worksheet
- Column layout per worksheet
- Historical metric layout
- Metadata layout
- Valuation layout
- Quality metrics layout
- Assumptions layout

### 2. Evidence-based profile

Commit:

```
backend/fixtures/production/custom_run_filter_aapl.xlsx
backend/fixtures/production/custom_run_filter_aapl.profile.json
```

The profile maps semantic `CustomRunData` sections to actual worksheet coordinates. It is authored from introspection output, not assumptions.

### 3. Parser

`backend/ingestion/custom_run_parser.py` now reads only from the committed profile. It does not hardcode worksheet names.

### 4. Cross-ticker generalization

Only after inspecting AAPL, MSFT, AMZN, and TJX:

- If layouts are identical → one profile
- If layouts differ → parser supports per-ticker or variant profiles

## How to unblock

### Step 1 — Commit the production workbook

Place the real file at:

```
backend/fixtures/production/custom_run_filter_aapl.xlsx
```

If the file is on your local machine (e.g. `C:\Users\...\Downloads\HAP\backend\storage\uploads\...\custom_run_filter.xlsx`), copy it to the path above and push.

### Step 2 — Generate introspection report

```bash
cd backend
python3 scripts/inspect_custom_run_workbook.py \
  fixtures/production/custom_run_filter_aapl.xlsx \
  -o fixtures/production/custom_run_filter_aapl.introspection.json
```

### Step 3 — Author the profile JSON

Translate introspection evidence into `custom_run_filter_aapl.profile.json`. Example structure:

```json
{
  "version": 1,
  "evidence_tickers": ["AAPL"],
  "sections": [
    {
      "section": "metadata",
      "sheet_name": "<actual Bloomberg sheet name>",
      "layout": "key_value",
      "label_column": 1,
      "value_column": 2,
      "data_start_row": 2
    }
  ]
}
```

### Step 4 — Validate end-to-end

```bash
cd backend
python3 -m pytest tests/test_production_workbook.py -m production
python3 -m pytest
```

Success criteria: production AAPL workbook reaches `AnalysisEngine.run()` with **no artificial workbook transformation**.

## Tooling added in this branch

| File | Purpose |
|------|---------|
| `backend/ingestion/workbook_introspector.py` | Dump actual worksheet structure |
| `backend/ingestion/production_workbook_profile.py` | Evidence-based profile loader |
| `backend/scripts/inspect_custom_run_workbook.py` | CLI for reverse-engineering |
| `backend/tests/test_production_workbook.py` | Production-gated tests |

## Test status without production workbook

- Profile-driven unit tests pass (using non-standard `TEST_*` sheet names)
- Production tests skip with explicit message
- Invented `custom_run_filter_aapl.example.xlsx` is rejected by parser
