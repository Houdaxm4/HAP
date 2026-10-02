# Quarterly Update certification — IDCC Q2

Status: **READY_FOR_PRODUCTION**

Source analysis: `275d5e21-42e2-4a39-9f78-be9fa48c1b44` (IDCC 2026 Q2 template + 2026 Q1 FA previous).
Working outputs: `backend/storage/outputs/quarterly-idcc-q2-cert/`

Bloomberg IS/CF bodies were cleared (301 cells) to force SEC retrieval. Previous-quarter standardized workbook was required and used.

## Acceptance gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Retrieval (missing Bloomberg IS/CF → SEC) | **PASS** | `quarterly_presentation_report.json` — IS 10 SEC rows, CF 6 SEC rows |
| Carry-forward I27:I32 | **PASS** | `quarterly_carry_forward_report.json` |
| Q2 ROIC/ROCE % + yellow M1:N25 | **PASS** | `quarterly_projection_report.json` |
| ER/EV/Graham Annual parity | **PASS** | ER/OE/Graham `KEEP_EXISTING`; original cells preserved |
| Excel COM recalculation | **PASS** | `excel_com_calculate_full_rebuild` status ok |
| Provenance | **PASS** | SEC primary on rebuilt IS/CF |
| No HAP circular references | **PASS** | hap_introduced=0 |
| No regression of originals | **PASS** | `cell_diff_original_assumptions.json` preserved=26 diffs=0 |

Regression: **530 passed, 1 skipped**.

## Verified I27:I32 mapping (by Inputs!Bxx, not row index)

| Dest | H formula | Field | Source (Q1 FA) | Value | Format |
| --- | --- | --- | --- | --- | --- |
| I27 | Inputs!B67 | Max Current Price to Buy | I26 | 95.01 | `"$"#,##0.00` |
| I28 | Inputs!B73 | Current 3-Year EPS 10-Year Average Growth | I27 | 1.0377 | `0.00%` |
| I29 | Inputs!B74 | Growth Direction | I28 | P | `@` |
| I30 | Inputs!B75 | Current 3-Year Revenue 10-Year Average Growth | I29 | 0.4952 | `0.00%` |
| I31 | Inputs!B70 | Expected Return Price Plus Dividends Given Current Price | I30 | 0.0218 | `0.00%` |
| I32 | Inputs!B71 | Expected Return Price Plus Dividends Given Max Entry Price | I31 | 0.1709 | `0.00%` |

I22 formula preserved. Dest I26 (Current Price / Inputs!B63) is outside the required six-cell range.

## Source-selection and quarter-derivation rules

1. Inspect Bloomberg at fact level. Structural IS/CF failure → rebuild from SEC 10-Q presentation (do not force Bloomberg layout).
2. SEC EDGAR is authoritative. Yahoo is supplementary only, with source attribution. Material Yahoo/SEC conflicts keep SEC.
3. Missing facts stay unresolved (`value=None`); never written as zero.
4. IS: prefer reported 3-month standalone; else YTD subtract.
5. CF standalone: Q2 = 6m YTD − Q1 YTD; Q3 = 9m − 6m; Q4 = 10-K FY − 9m YTD.
6. BS: point-in-time only; never manufactured by subtracting consecutive statements.
