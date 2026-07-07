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
4. Preserve traceability for every important number.
5. Prefer SEC filings as the source of truth for financial statements.
6. Human judgment always overrides automation.