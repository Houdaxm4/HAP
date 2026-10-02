# New Company Production Certification

Recommendation: **READY_FOR_PRODUCTION**

New Company remains a ten-year Industrial Template initiation path. Certified Annual/Quarterly ER/EV/OE/Graham judgment is reused after genuine lease approval and Excel COM. Word is generated only when gates A–L authorize it.

Regression: **542 passed, 1 skipped, 0 failed**.

Source initiation workbook: IDCC Industrial Template (FY2016–FY2025 annual columns, latest quarter FY2026 Q2) plus Bloomberg CRF from analysis `275d5e21-42e2-4a39-9f78-be9fa48c1b44`.
Pipeline analysis: `edd8ea8f-534e-4ca9-a78a-bb908abf9692` (new run; prior `0880db66-6fcb-4aa7-9add-b50ceeffc6be` PASS statuses were not reused).
Working copies: `backend/storage/outputs/edd8ea8f-534e-4ca9-a78a-bb908abf9692/` and `backend/storage/outputs/new-company-idcc-cert/`.

Sequence executed: Mode A (parse → CRF → SEC → fill → validate) → NewCompanyRunner → lease-rate review → FastAPI `/analyst-review/lease-rate` approve → genuine Excel COM `CalculateFullRebuild` → Annual-parity valuation judgment → post-COM projection refresh → gates A–L → authorized Word.

Excel: Microsoft Excel COM 16.0. Recalc `ok`, `com_invoked=true`, method `excel_com_calculate_full_rebuild`, 20 cells checked, 0 missing caches, 0 formula errors.

## 1. Root cause of the prior G and I failures

### Gate G — `BUYBACK_SHARES_COVERAGE_INCOMPLETE`

Failure class: **retrieval / mapping**, not missing disclosure.

| Fiscal year | Missing field (prior run) | 10-K location | Shares explicitly disclosed? | Dollars + avg price for derivation? | Cause |
| --- | --- | --- | --- | --- | --- |
| FY2016 | shares | 2025 10-K capital-return table (Item 7 / Share Repurchase Program); also 2018–2025 comparatives | Yes — 1,304 thousand shares | CF $64.685m matches table; no XBRL average-price tag | Retrieval: annual share XBRL tag absent; cumulative program tag not used |
| FY2017 | shares | same table | Yes — 107 thousand | CF $7.693m | same |
| FY2018 | shares | same table | Yes — 1,478 thousand | CF $110.505m | same |
| FY2019 | shares mapped wrongly | same table | Yes — 2,962 thousand | CF $196.269m | Mapping: `StockRepurchasedDuringPeriodShares` was 2014–2019 cumulative (11.241m), used as annual |
| FY2020 | not flagged but wrong grain when present | same table | Yes — 6 thousand | CF $0.349m | Cumulative XBRL 11.247m rejected |
| FY2021 | wrong grain | same table | Yes — 458 thousand | CF $30.0m | Annual-framed XBRL 11.705m implied ~$2.56/share; rejected as implausible / unreconciled to CF |
| FY2022 | wrong grain | same table | Yes — 1,224 thousand | CF $74.445m | Cumulative XBRL 12.929m |
| FY2023 | shares | same table | Yes — 4,411 thousand (includes Dutch-auction tender) | CF $339.704m | Retrieval: no annual share XBRL |
| FY2024 | shares | same table | Yes — 644 thousand | CF $66.726m | Retrieval |
| FY2025 | wrong grain | same table | Yes — 385 thousand | CF $102.319m | Cumulative XBRL 18.369m / $1,241.73m program-to-date |

Share-count Δ outstanding was correctly **not** used. Treasury-share balance deltas were also **not** used. Average-price XBRL tags are absent; shares are **explicit 10-K table disclosures** (in thousands), not derived. Gate G coverage was appropriate; it was not weakened.

### Gate I — `PROJECTED_ROIC_FAILED`

Failure class: **calculation / mapping**, not insufficient SEC history and not a WACC prerequisite.

1. `_find_row("operating income")` matched **Other Operating Income** (zeros) instead of **Operating Income (Loss)** / `IS_OPER_INC`.
2. LQ IS column G is empty (growth formulas). Column C is **standalone 3-month** (`3 Months Ended`, C5=`2026 Q2`, revenue 260.17). The model treated C as 6M YTD.
3. Historical YTD used only LQ column H (one prior year, also a formula). The model required ≥3 YTD/FY proportions. SEC 10-Q 6-month duration facts for revenue and operating income exist for FY2021–FY2026 and were unused.
4. `latest_quarter_fiscal_year` was FY2025 because prior-column `2025 Q2` overwrote current `2026 Q2`.
5. Invested-capital formulas on `IC & NOPAT & ROIC` have formula year headers, so the IC cell was not resolved before COM.
6. **WACC was present** at Balance Sheet!L126 = 9.0646% (Inputs!L54 → Final Metrics!L7 = 0.090646). `custom_run.assumptions.wacc` was None. Gate I does **not** require WACC; ROIC failed because seasonality-adjusted OI (and then IC) was missing. WACC is used only for the ROIC–WACC spread.

## 2. Files changed and methodology decisions

- `backend/services/new_company_buyback_service.py` — reject multi-year cumulative XBRL share tags; parse the 10-K Share Repurchase Program table (thousands); keep missing as missing; no outstanding-delta or treasury-delta proxy.
- `backend/services/new_company_seasonality_service.py` — preferred OI/revenue labels; do not treat standalone 3-month C as 6M YTD; SEC 6M/9M duration facts for current and historical YTD.
- `backend/services/new_company_period_service.py` — current LQ year from column C (`2026 Q2`), not the prior-year column.
- `backend/services/new_company_projection_service.py` — map WACC from Final Metrics!L7 / Inputs / BS L126; ROIC independent of WACC; house IC = OA − OL + capitalized leases + R&D when the IC formula cache is empty.
- `backend/services/new_company_runner.py` — pass company facts / 10-K manifest into buybacks and seasonality; refresh projection after genuine COM.
- `backend/services/new_company_output_gate_service.py` — missing WACC is a warning, not a Gate I fail.
- `backend/tests/test_new_company_pipeline.py` — focused G/I tests listed below.
- Gate G coverage requirement unchanged. Naive ×2 annualization remains comparison-only.

## 3. Year-by-year buyback coverage (this run)

All ten years: **explicit** 10-K Share Repurchase Program table in the FY2025 10-K (accession `0001405495-26-000011`), dollars from `PaymentsForRepurchaseOfCommonStock`. Shares not derived.

| Year | Dollars ($m) | Shares (m) | Status | Source |
| --- | ---: | ---: | --- | --- |
| FY2016 | 64.685 | 1.304 | explicit | 10-K table |
| FY2017 | 7.693 | 0.107 | explicit | 10-K table |
| FY2018 | 110.505 | 1.478 | explicit | 10-K table |
| FY2019 | 196.269 | 2.962 | explicit | 10-K table |
| FY2020 | 0.349 | 0.006 | explicit | 10-K table |
| FY2021 | 30.000 | 0.458 | explicit | 10-K table |
| FY2022 | 74.445 | 1.224 | explicit | 10-K table |
| FY2023 | 339.704 | 4.411 | explicit | 10-K table (includes tender) |
| FY2024 | 66.726 | 0.644 | explicit | 10-K table |
| FY2025 | 102.319 | 0.385 | explicit | 10-K table |

Evidence: `edd8ea8f-.../new_company_buyback_report.json`.

## 4. Seasonality, WACC, projection

Required Q2 observations: current 6M YTD and ≥3 historical (6M YTD, full-year) pairs for revenue and operating income.

Available: FY2026 H1 YTD revenue 465.586 / OI 221.500 (SEC 6-month 10-Q facts, not the 3-month 260.17 / 139.24). Historical 6M YTD for FY2021–FY2025 (five pairs). Selected OI YTD/FY factor ≈ 0.596. Confidence **high**.

Naive ×2 OI annualization is comparison-only (unadjusted ROIC 0.300 vs seasonality-adjusted 0.278).

WACC provenance after COM: **Final Metrics!L7 = 0.090646** (Inputs!L54 / 100 from Balance Sheet!L126 9.0646%). Mapped, not invented, not a stale substitute.

Projected ROIC 0.278; ROCE 0.287; ROIC–WACC 0.188; IC 1,167.3 (post-COM house IC including lease/R&D capitalization); NOPAT 325.0.

Evidence: `seasonality_projection_report.json`, `new_company_projection_report.json`.

## 5. Regression suite

`python -m pytest tests -q` → **542 passed, 1 skipped, 0 failed**.

Existing New Company, Annual, and Quarterly tests preserved. Added coverage for explicit 10-K shares, documented derivation, missing-not-zero, no share-count-delta proxy, cumulative XBRL rejection, sufficient vs insufficient Q2 seasonality, YTD vs standalone vs FY, WACC present/missing, independent ROIC vs WACC-dependent spread, Gate G/I PASS/FAIL, and Word withholding when a gate fails.

## 6. New IDCC pipeline ID and Excel COM

- Analysis: `edd8ea8f-534e-4ca9-a78a-bb908abf9692`
- Excel COM 16.0; `excel_com_calculate_full_rebuild`; `com_invoked=true`; status `ok`; checked=20; missing=0; errors=0; 5.7s
- Lease approval: `POST /analysis/edd8ea8f-534e-4ca9-a78a-bb908abf9692/analyst-review/lease-rate` action=approve; approved 6.20%
- Evidence: `new_company_excel_recalc_report.json`, `lease_rate_review.json`

## 7. Gates A–L

| Gate | Result | Evidence |
| --- | --- | --- |
| Workbook (10-year Industrial Template + CRF) | **PASS** | `storage/uploads/275d5e21-42e2-4a39-9f78-be9fa48c1b44/prefilled_workbook.xlsx` |
| Mode A → NewCompanyRunner | **PASS** | `edd8ea8f-.../new_company_run_state.json` |
| Ten-year SEC / statement validation | **PASS** | `ten_year_source_coverage.json` |
| Lease-rate proposal | **PASS** | proposed 6.20% — `lease_rate_review.json` |
| Analyst lease-rate approval | **PASS** | FastAPI approve; approved 6.20%; blocking=false |
| Genuine Excel COM CalculateFullRebuild | **PASS** | `new_company_excel_recalc_report.json` |
| Valuation judgment (ER / EV / OE / Graham) | **PASS** | ER=`KEEP_EXISTING` OE=`KEEP_EXISTING` Graham=`KEEP_EXISTING`; originals preserved; Q2 YTD vs standalone vs projected FY disclosed |
| HAP_ANALYSIS labeled and adjacent | **PASS** | 59 labeled HAP ANALYSIS cells; original assumption cells unchanged |
| No HAP-introduced circular references | **PASS** | `hap_introduced=0` — `new_company_circular_reference_report.json` |
| Original valuation assumptions preserved | **PASS** | `new-company-idcc-cert/cell_diff_original_assumptions.json` — 8/8 preserved, 0 diffs |
| Gate A template/period | **PASS** | `new_company_output_gate_report.json` |
| Gate B statements | **PASS** | same |
| Gate C PE10/E10 | **PASS** | same |
| Gate D tax | **PASS** | same |
| Gate E R&D | **PASS** | 3-year agent-selected life (not manually approved) |
| Gate F leases + lease rate | **PASS** | same |
| Gate G buybacks | **PASS** | explicit 10-K shares FY2016–FY2025 |
| Gate H current data | **PASS** | same |
| Gate I Q2 projection | **PASS** | seasonality-adjusted ROIC 0.278; WACC mapped from Final Metrics!L7 |
| Gate J recalc | **PASS** | genuine COM |
| Gate K valuation extract | **PASS** | ER/EV/OE/Graham/ROIC after COM |
| Gate L valuation judgment | **PASS** | originals preserved; no HAP circulars |
| Report authorization / Word | **PASS** | `2025 IDCC New Company.docx` |

## 8. Original-assumption cell diff and circulars

Preserved (diff_count=0): `Expected Returns & Buybacks!A11`, `B5`, `E14`, `F14`; `Enterprise Value!C6`, `B6`; `R&D!B8`; `Leases!A18`.

HAP alternatives sit in unused adjacent columns labeled `HAP ANALYSIS — not original analyst data.`

Template-native Tax circulars (D15↔D8 and peers) remain pre-existing; HAP introduced none.

## 9. Frozen report location

This file: `backend/NEW_COMPANY_PRODUCTION_CERTIFICATION.md`. Run copy: `storage/outputs/edd8ea8f-534e-4ca9-a78a-bb908abf9692/` and `storage/outputs/new-company-idcc-cert/`.

Completed workbook: `2025 IDCC FA.xlsx`, `completed_workbook.xlsx`. Authorized Word: `2025 IDCC New Company.docx`.

## 10. Remaining blockers

None. Gates A–L passed on this real-workbook Windows run. Authorized Excel and Word were generated and validated.

Warnings retained (non-blocking): PE10 period notes; R&D useful life is agent-selected and not manually approved.

## Status rule

READY_FOR_PRODUCTION is set only when every required real-workbook Windows certification gate is PASS and authorized deliverables are generated. That condition is met on analysis `edd8ea8f-534e-4ca9-a78a-bb908abf9692`.
