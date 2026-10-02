# New Company LNN Gate G Correction Certification

Recommendation: **READY_FOR_PRODUCTION** for the autonomous New Company workflow.

This report certifies the **corrected LNN run** after recovering filing-supported buyback zeros, tracing lease/R&D assumptions into the model, and fixing the FY2065 header-token flake. It does **not** supersede the prior IDCC New Company production certification at commit `da1765badfd339dfdc3deb2ffc92968ff0012268` (analysis `edd8ea8f`). The prior autonomous LNN failure report for analysis `07e53d34-7768-4d58-b84a-07af579fae14` is retained as historical evidence and is not reused as pass evidence.

Generated at: 2026-09-22T19:17:21Z
New analysis ID: `17feded2-1785-4807-8560-1716c7cfa34c`
Ticker: LNN (Lindsay Corporation)
Parent revision: `f1b8b1a189bc9b0c7390b384fff625f0daac9d9a`
Certified code revision: `2a8cc3cbe6b09947bd4ad85c8522b1bb471ec386` (Gate G narrative/CFS zeros, duration-safe dollar facts, lease-note vs row-18 formula distinction, R&D life-driven capitalization formulas, FY token range/formula guard)
Workbook source: `storage/uploads/e49429d4-2828-41ac-8eec-f78ded145015/prefilled_workbook.xlsx`
CRF: `storage/uploads/e49429d4-2828-41ac-8eec-f78ded145015/Custom_Run_Filter_2026-08-27-_20-57_-LNN.xlsx`
Run artifacts: `storage/outputs/17feded2-1785-4807-8560-1716c7cfa34c`
Frozen evidence copy: `storage/certifications/new-company-lnn-17feded2`

## Investigation findings (before the code change)

### Missing buyback years were explicit zeros, not unavailable dollars

Gate G failed on `07e53d34` because FY2017, FY2018, FY2019, and FY2021 had `dollars=None` and `absence_class=None`. Shares were `0.0` from annual `TreasuryStockSharesAcquired`. That is case **C**: the company had no repurchases and the annual filings explicitly support a zero amount. Missing was not treated as zero; zeros are now recorded only with filing evidence.

| FY | Filing evidence | Amount | Units | Why the old pipeline missed it |
| --- | --- | --- | --- | --- |
| 2017 | FY2019 10-K: “There were no shares repurchased during the twelve months ended August 31, 2019, 2018, and 2017.” FY2017 CFS `Repurchase of common shares — (48,335) (96,883)` (thousands; em-dash = $0 for 2017). Annual XBRL `TreasuryStockSharesAcquired=0`. No current-year `PaymentsForRepurchaseOfCommonStock`. | **$0** | USD millions | Narrative parser only matched an IDCC-style capital-return table. CFS dashes were not parsed. Dollar matching used `find_fact` without an annual-duration filter. Shares=0 did not set `REPORTED_ZERO` while dollars stayed null. |
| 2018 | Same rolling 10-K language; FY2018 CFS `Repurchase of common shares - - (48,335)`. Annual shares tag = 0. | **$0** | USD millions | Same. |
| 2019 | FY2021 10-K: “no shares repurchased … August 31, 2021, 2020, and 2019.” FY2019–FY2021 CFS omit the repurchase line while still listing option proceeds, withholding, debt, and dividends. Annual shares tag = 0. | **$0** | USD millions | Omitted CFS line is **not** treated as zero. The zero comes from the explicit narrative. |
| 2021 | Same FY2021/FY2023 10-K rolling language. Annual shares tag = 0. No annual repurchase-dollar tag. | **$0** | USD millions | Same. |

Not used as buyback dollars: Bloomberg `PROC_FR_REPURCH_EQTY_DETAILED` (net equity), treasury-stock balance ($277,238 cost / 8,083 shares unchanged 2016–2022), or changes in shares outstanding.

FY2016 $48.335m, FY2024 $22.454m, and FY2025 $11.532m remain from annual `PaymentsForRepurchaseOfCommonStock`. FY2020/FY2022/FY2023 are reported zeros with narrative and/or annual XBRL support. Quarterly `StockRepurchasedDuringPeriodValue` is no longer accepted as an annual dollar fact.

Gate G was not weakened. Years that remain unsupported still fail.

### Autonomous 4.00% lease rate did not feed NPV

The 4.00% figure is the FY2025 ASC 842 weighted-average operating-lease discount rate (10-K accn `0001193125-25-248751`). Leases row 18 is `=Inputs!{col}35/{col}27` (Interest Expense / Total Debt). NPV/PV (`Leases!B14 =NPV(B18,B5:B9)`, `B15 =PV(B18,…)`) use that Estimated Long-Term Rate. Documenting 4.00% in HAP ANALYSIS did not write 4.00% into the model. The disclosed WtdAvg is not a substitute for the template long-term rate; original row-18 formulas are preserved.

### Autonomous 5-year R&D life did not feed capitalization math

`R&D!B8` was written to 5 and lookback FY2012–FY2025 was retrieved, but rows 3–4 still used hardcoded 3-year formulas (`E2+D2*2/3+1/3*C2`, `(E2+D2+C2)/3`). IC Capitalized R&D `='R&D'!G3` therefore still amortized over 3 years. B8 is the designated input; New Company now generates remaining-life formulas from that life. Annual Update still carries existing formulas and is unchanged.

### FY2065 suite flake

`test_jbss_fiscal_year_alignment_and_inputs_pe10` failed in the full suite (`dropped_years` included FY2065) and passed in isolation. Cause: `_fy_token` stringified non-string header objects (including ArrayFormula) and took the first `20xx` in formula text such as row `2065`, with no year-range guard. Isolation passed because neighboring tests did not leave those header objects in the same process-visible workbooks; the parser was order-sensitive to formula/array header cells. Formulas and out-of-range years (outside 1990–current+2) are now rejected.

## Corrections applied

1. **Buybacks (New Company only).** Parse 10-K “no shares repurchased during the twelve months ended …” and CFS repurchase-line dashes/literal zeros. Fill `dollars=0`, `shares=0`, `absence_class=reported_zero` with the filing URL. Annual-duration filter on dollar XBRL tags. Omitted CFS lines remain missing. Share-count and treasury-balance deltas are still excluded.
2. **Leases.** Do not overwrite row-18 formulas. HAP ANALYSIS notes now record selected 4.00%, source, rationale, confidence/limitations, the actual input cells, and that NPV/PV use Interest/Debt rather than ASC 842 WtdAvg.
3. **R&D (New Company only).** Write lookback expenses into the pre-window (B2:D2) and extra lookback `R&D!B20` (FY2012). Rewrite adaptable 3-year template formulas on rows 3–4 to 5-year remaining-life weights. IC Capitalized R&D continues to reference row 3.
4. **FY tokens.** `_fy_token` ignores non-strings, `=` formulas (except `="FY…"` / `=FY…`), and years outside 1990–current+2.

Annual and Quarterly certified workflows were not changed except for the safer FY header parser used by Annual period alignment.

## Fresh LNN run `17feded2` — independent gates

Status after first pass: **`complete`**. Review path: **`not_required`**. No lease or R&D approval pause. Word generated because gates authorized it.

| Gate | Result | Evidence |
| --- | --- | --- |
| Mode A + NewCompanyRunner | **PASS** | `new_company_run_state.json`; status `complete` |
| Ten-year validation | **PASS** | `ten_year_source_coverage.json` |
| Autonomous lease-rate decision | **PASS** | 4.00% disclosed, `AUTONOMOUS_AGENT_DECISION`; audit trail has no `LEASE_RATE_APPROVED`; `lease_rate_approved=false` |
| Autonomous R&D useful life | **PASS** | 5 years, SIC 3523 Farm Machinery & Equipment |
| Buyback history (Gate G) | **PASS** | See table below; `complete=true`; no `BUYBACK_DOLLARS_COVERAGE_INCOMPLETE` |
| Genuine Excel COM CalculateFullRebuild | **PASS** | method `excel_com_calculate_full_rebuild`, Excel 16.0, `com_invoked=true`, status `ok`, 20 cells checked, 0 errors, 6.7s |
| Valuation judgment | **PASS** | KEEP_EXISTING / KEEP_REPORTED_BASE; `original_assumptions_preserved=true` |
| Circular references | **PASS** | `hap_introduced=[]`; remaining Tax sheet loops are `template_native` |
| Gates A–L | **PASS** | `new_company_output_gate_report.json`; blockers `[]`; `report_authorized=true` |
| Word / Excel deliverables | **PASS** | `2025 LNN FA.xlsx`, `2025 LNN New Company.docx` |

### Buyback evidence by fiscal year (this run)

| FY | Dollars ($m) | Shares (m) | Absence | Source |
| --- | --- | --- | --- | --- |
| 2016 | 48.335 | 0.68879 | — | XBRL `PaymentsForRepurchaseOfCommonStock` / `TreasuryStockSharesAcquired` |
| 2017 | 0.0 | 0.0 | reported_zero | FY2019 10-K narrative (accn `0000950123-19-009834`) |
| 2018 | 0.0 | 0.0 | reported_zero | FY2020 10-K narrative (accn `0001564590-20-047271`) |
| 2019 | 0.0 | 0.0 | reported_zero | FY2021 10-K narrative (accn `0001564590-21-051450`) |
| 2020 | 0.0 | 0.0 | reported_zero | FY2022 10-K narrative (accn `0000950170-22-019799`) |
| 2021 | 0.0 | 0.0 | reported_zero | FY2023 10-K narrative (accn `0000950170-23-054198`) |
| 2022 | 0.0 | 0.0 | reported_zero | Annual XBRL dollars + FY2023 10-K narrative |
| 2023 | 0.0 | 0.0 | reported_zero | Annual XBRL dollars + FY2023 10-K narrative |
| 2024 | 22.454 | 0.194 | — | XBRL `PaymentsForRepurchaseOfCommonStock` / `TreasuryStockSharesAcquired` |
| 2025 | 11.532 | 0.086 | — | XBRL `PaymentsForRepurchaseOfCommonStock` / `TreasuryStockSharesAcquired` |

### Lease assumption-to-calculation trace

| Item | Value |
| --- | --- |
| Selected value | **4.00%** (0.04) |
| Source / period | 10-K FY2025 accession `0001193125-25-248751`; methodology `reported_weighted_average_discount_rate` |
| Decision class | `AUTONOMOUS_AGENT_DECISION` |
| Rationale | Company-disclosed ASC 842 weighted-average operating-lease discount rate for the latest fiscal year |
| Confidence / limitations | Rank-1 disclosed rate; a remaining-term WtdAvg is not the template long-term rate |
| Workbook input cell | HAP ANALYSIS `Leases!M2=4.00%`. Row 18 formulas **not** overwritten (9 formula cells). |
| Dependent calculation | `Leases!C18=Inputs!D35/Inputs!D27` etc.; `NPV(C18,C5:C9)` and `PV(C18,…)` use Interest Expense / Total Debt |

### R&D assumption-to-calculation trace

| Item | Value |
| --- | --- |
| Selected value | **5 years** (`R&D!B8=5`; template was 3) |
| Source / period | SIC 3523 Farm Machinery & Equipment; 10-K business description / companyfacts; lookback FY2012–FY2025 |
| Decision class | `AUTONOMOUS_AGENT_DECISION` |
| Rationale | Industrial machinery product-development cycle; life is not derived from annual R&D spend |
| Confidence / limitations | 0.7; optional analyst override |
| Workbook input cell | `R&D!B8` |
| Lookback written | `B2=11.395`, `C2=11.125`, `D2=12.849`, `B20=9.481` (FY2012 extra year) |
| Dependent calculation | `E3=IFERROR(E2+D2*4/5+C2*3/5+B2*2/5+B20*1/5,0)`; `E4=IFERROR((E2+D2+C2+B2+B20)/5,0)`; later years the same 5-year weights; IC `Capitalized R&D` `='R&D'!G3` |

### Original-assumption cell snapshot

Valuation preserved original ER/EV formulas, including `Expected Returns & Buybacks!E14`, `F14`, `Enterprise Value!B6`, `C6`, `B42`. HAP ANALYSIS blocks are adjacent notes only. `hap_introduced_circular_count=0`.

### Regression suite

Full backend suite after the fix: **554 passed, 0 failed, 1 skipped** (92.55s). Previously 548 passed, 1 failed (`test_jbss_fiscal_year_alignment_and_inputs_pe10` FY2065), 1 skipped. The JBSS alignment test now passes in the full suite.

## Historical evidence preserved

- Certified baseline: `da1765badfd339dfdc3deb2ffc92968ff0012268` (IDCC `edd8ea8f`)
- Autonomous workflow commits: `9dd3bc7`, `f1b8b1a`
- Autonomous LNN failure (Gate G): analysis `07e53d34-7768-4d58-b84a-07af579fae14`, report `NEW_COMPANY_AUTONOMOUS_DECISION_CERTIFICATION.md` and `storage/certifications/new-company-lnn-07e53d34/`

## Deliverables

- Completed workbook: `storage/outputs/17feded2-1785-4807-8560-1716c7cfa34c/completed_workbook.xlsx`
- Working Excel: `storage/outputs/17feded2-1785-4807-8560-1716c7cfa34c/2025 LNN FA.xlsx`
- Word analysis: `storage/outputs/17feded2-1785-4807-8560-1716c7cfa34c/2025 LNN New Company.docx` (authorized, not forced)

This run is a new analysis ID with independently evaluated gates. The failed `07e53d34` gate results were not reused.
