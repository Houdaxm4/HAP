# HAP Project Specification

## Product Name

Houda's Analyst Platform (HAP)

## Core Principle

HAP is workflow-driven, not prompt-driven.

## Central Object

The central object in HAP is an **Analysis**.

Every task, file, report, decision, and output belongs to an Analysis.

## First MVP Goal

Within one week, HAP should allow the analyst to:

1. Create a new Analysis.
2. Specify whether it is:
   - New Company
   - Annual Update
   - Quarterly Update
3. Upload:
   - prefilled workbook
   - previous analysis workbook, if applicable
   - custom_run_filter workbook
4. Run the analysis workflow.
5. Receive:
   - updated workbook
   - verification report
   - discrepancy report
   - decision log
   - analyst summary

## Interfaces

HAP will eventually have two main interfaces:

1. Dashboard / Command Center
2. Telegram communication interface

## Golden Rules

1. Never overwrite formulas.
2. Never invent financial data.
3. Never recompute proprietary metrics from custom_run_filter.
4. Never overwrite analyst-calculated Workbook Metrics — HAP computes independent HAP Metrics and compares when equivalents exist.
5. Preserve traceability for every important number.
6. Prefer SEC filings as the source of truth for financial statements.
7. Human judgment always overrides automation.

## Ingestion (HAP v1)

Product inputs: prefilled workbook + Bloomberg `custom_run_filter` workbook + SEC filings.
See [`docs/INGESTION_ARCHITECTURE.md`](INGESTION_ARCHITECTURE.md). Custom_Run_Filter is proprietary analytics, not a cell-mapping table.

## Architecture Freeze

The core HAP architecture is considered stable.

No new packages, contracts, or architectural layers may be introduced unless they solve a clearly identified limitation that cannot be addressed within the current design.

Future development should focus on:

- Financial intelligence
- Analysis modules
- Investment methodology
- Testing
- User experience

not architecture.