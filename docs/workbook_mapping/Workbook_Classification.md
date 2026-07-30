# Workbook Classification (M1.5)

**Baseline:** AAPL / `AAPL 2026 Q2 - Industrial Template v27.6.xlsx`  
**Versions:** filename `v27.6` · sheet `v27.7`  
**Generated (UTC):** 2026-07-30T19:05:10.716044+00:00  
**Schema:** 1.0.0  
**Suite structure identical:** True

This document summarizes the machine-readable [`Workbook_Manifest.json`](Workbook_Manifest.json). Future Mode A Excel modules must consume the manifest — not re-scan the workbook for roles/write policy.

## Sheet classification

| # | Sheet | Role | Write policy | Fill priority | Formulas | Constants | Writable cells | Purpose |
|---|-------|------|--------------|---------------|----------|-----------|----------------|---------|
| 1 | `Balance Sheet - Standardized` | Data | Hybrid | P0 | 25 | 1219 | 952 | Annual standardized balance sheet — primary BS data grid for HAP fill. |
| 2 | `BS%` | Formula | Read-only | Never | 1110 | 1 | 0 | BS common-size percentages driven by Balance Sheet - Standardized. |
| 3 | `Income - GAAP` | Data | Hybrid | P0 | 54 | 839 | 651 | Annual GAAP income statement — primary IS data grid for HAP fill. |
| 4 | `IS%` | Formula | Read-only | Never | 543 | 0 | 0 | IS common-size percentages driven by Income - GAAP. |
| 5 | `Cash Flow - Standardized` | Data | Hybrid | P0 | 7 | 773 | 629 | Annual standardized cash flow — primary CF data grid for HAP fill. |
| 6 | `CF%` | Formula | Read-only | Never | 531 | 0 | 0 | CF percentages driven by Cash Flow - Standardized. |
| 7 | `FCF` | Formula | Read-only | Never | 130 | 12 | 0 | Free cash flow build (formula-driven). |
| 8 | `Last Quarter BS Standardized` | Data | Hybrid | P1 | 111 | 394 | 0 | LQ standardized balance sheet (deferred fill after annual path). |
| 9 | `Last Quarter IS Standardized` | Hybrid | Hybrid | P1 | 118 | 341 | 0 | LQ standardized income statement (deferred fill). |
| 10 | `Last Quarter CF Standardized` | Data | Hybrid | P1 | 47 | 225 | 0 | LQ standardized cash flow (deferred fill). |
| 11 | `Last Quarter BS As Reported` | Data | Read-only | Never | 0 | 1348 | 0 | LQ BS as-reported — company presentation; treat as historical, do not map in v0. |
| 12 | `Last Quarter IS As Reported` | Data | Read-only | Never | 0 | 590 | 0 | LQ IS as-reported — historical / presentation; do not map in v0. |
| 13 | `Last Quarter CF As Reported` | Data | Read-only | Never | 0 | 296 | 0 | LQ CF as-reported — historical / presentation; do not map in v0. |
| 14 | `DividendHelper` | Helper | Read-only | Never | 0 | 351 | 0 | Dividend helper support sheet. |
| 15 | `Inputs` | Formula | Read-only | Never | 637 | 114 | 0 | Central bridge — pulls statements; feeds ratios/tax/leases/metrics. |
| 16 | `IC & NOPAT & ROIC ` | Formula | Read-only | Never | 171 | 19 | 0 | Invested capital / NOPAT / ROIC (note trailing space in name). |
| 17 | `Tax` | Formula | Read-only | Never | 220 | 22 | 0 | Tax / ETR support. |
| 18 | `Leases` | Formula | Read-only | Never | 180 | 18 | 0 | Lease adjustments. |
| 19 | `R&D` | Formula | Read-only | Never | 46 | 6 | 0 | R&D capitalization adjustments. |
| 20 | `All Ratios` | Formula | Read-only | Never | 280 | 36 | 0 | Ratio library from Inputs. |
| 21 | `Final Metrics` | Formula | Read-only | Never | 416 | 72 | 0 | Summary metrics hub. |
| 22 | `Expected Returns & Buybacks` | Output | Read-only | Never | 73 | 43 | 0 | Expected returns / buybacks outputs. |
| 23 | `Enterprise Value` | Output | Read-only | Never | 111 | 85 | 0 | Enterprise value outputs. |
| 24 | `Template Version` | Meta | Read-only | Never | 0 | 2 | 0 | Template version metadata. |

## Writable candidate regions (P0 annual)

- **`Balance Sheet - Standardized`:** rows 1–132, cols 3–14, 952 writable cells — Bounding box of writable cells; fill_priority=P0
- **`Income - GAAP`:** rows 1–106, cols 3–14, 651 writable cells — Bounding box of writable cells; fill_priority=P0
- **`Cash Flow - Standardized`:** rows 1–77, cols 3–14, 629 writable cells — Bounding box of writable cells; fill_priority=P0

## Do-not-write summary

- **`BS%`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 1110 formula cells are never writable.
- **`IS%`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 543 formula cells are never writable.
- **`CF%`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 531 formula cells are never writable.
- **`FCF`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 130 formula cells are never writable.
- **`Last Quarter BS As Reported`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; As-reported LQ content is Historical Data for Mode A v0.
- **`Last Quarter IS As Reported`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; As-reported LQ content is Historical Data for Mode A v0.
- **`Last Quarter CF As Reported`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; As-reported LQ content is Historical Data for Mode A v0.
- **`DividendHelper`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.
- **`Inputs`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 637 formula cells are never writable.
- **`IC & NOPAT & ROIC `:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 171 formula cells are never writable.
- **`Tax`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 220 formula cells are never writable.
- **`Leases`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 180 formula cells are never writable.
- **`R&D`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 46 formula cells are never writable.
- **`All Ratios`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 280 formula cells are never writable.
- **`Final Metrics`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 416 formula cells are never writable.
- **`Expected Returns & Buybacks`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 73 formula cells are never writable.
- **`Enterprise Value`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.; 111 formula cells are never writable.
- **`Template Version`:** Entire sheet write_policy=Read-only — HAP must not write any cells.; fill_priority=Never.

## Control cells (annual statements)

- **`Balance Sheet - Standardized`:** `A1`, `A2`, `A3`, `C1`, `C2`, `C3`
- **`Income - GAAP`:** `A1`, `A2`, `A3`, `C1`, `C2`, `C3`
- **`Cash Flow - Standardized`:** `A1`, `A2`, `A3`, `C1`, `C2`, `C3`

## Classification legend

| Class | Meaning | Writable? |
|-------|---------|-----------|
| Writable Input | HAP may populate from CFM (controls + annual period values) | Yes |
| Formula | Excel formula cell | No |
| Output | Formula on valuation/metrics output sheets | No |
| Read-only | Constant on a read-only policy sheet / meta | No |
| Historical Data | As-reported or deferred LQ values | No (v0) |
| Helper | Labels, headers, CapIQ codes | No |
| Named Range | Target also listed under named_ranges on the cell | — |
| Protected | Sheet protection enabled | No |
| Empty | Blank inside used range (region aggregate) | No |
| Reserved | Hidden row/col content | No |

## Assumptions

- Computed used ranges are capped (400 rows × 80 cols) to ignore spurious openpyxl max_column=XFB.
- Blank cells inside used ranges are aggregated as Empty regions, not enumerated cell-by-cell.
- Every non-blank cell in the used range receives an explicit classification record.
- Annual IS/BS/CF period-body constants are Writable Input (P0 candidates); formulas are never writable.
- LQ standardized values are Historical Data / deferred P1 (writable=false until a future mapping).
- As-reported LQ sheets are Historical Data / Never for Mode A v0 mapping.
- Formula-driven sheets (Inputs, %, ratios, tax, leases, R&D, IC, FCF, Final Metrics) are Read-only.
- Output sheets (Enterprise Value, Expected Returns) classify formula cells as Output.
- Control values on annual sheets live in C1:C3; labels in A1:A3; CapIQ codes often in column B (hidden).
- Sheet name 'IC & NOPAT & ROIC ' includes a trailing space — exact match required.
- Filename version (v27.6) may differ from Template Version sheet (v27.7) — both recorded.
- Baseline manifest is built from the chosen ticker workbook; suite fingerprints validate structure parity.
- Downstream modules must consume this manifest and must not re-derive sheet roles from Excel.

## Suite fingerprints

### AAPL
- Sheets: 24
- Roles match baseline policies applied per sheet name.

### MSFT
- Sheets: 24
- Roles match baseline policies applied per sheet name.

### AMZN
- Sheets: 24
- Roles match baseline policies applied per sheet name.

### TJX
- Sheets: 24
- Roles match baseline policies applied per sheet name.
