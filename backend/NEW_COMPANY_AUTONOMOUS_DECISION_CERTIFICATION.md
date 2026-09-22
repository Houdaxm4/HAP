# New Company Autonomous-Decision Certification

Recommendation: **NOT_READY_FOR_PRODUCTION**

This report certifies the **autonomous lease-rate and R&D useful-life workflow**. It does **not** supersede or restate the prior IDCC New Company production certification at commit `da1765badfd339dfdc3deb2ffc92968ff0012268` (analysis `edd8ea8f`). That baseline remains the last production-certified New Company revision.

Generated at: 2026-09-22T18:19:22.413719+00:00
LNN run id: `07e53d34-7768-4d58-b84a-07af579fae14`
Ticker: LNN (Lindsay Corporation)
Source revision at run time: uncommitted autonomous-decision working tree on top of `da1765badfd339dfdc3deb2ffc92968ff0012268`
Workbook: `storage/uploads/e49429d4-2828-41ac-8eec-f78ded145015/prefilled_workbook.xlsx`
CRF: `storage/uploads/e49429d4-2828-41ac-8eec-f78ded145015/Custom_Run_Filter_2026-08-27-_20-57_-LNN.xlsx`

## Prior LNN block (e49429d4) — inspection before the workflow change

Run `e49429d4-2828-41ac-8eec-f78ded145015` paused at `awaiting_analyst_review` because Gate F required a human lease-rate approval even though HAP already had a rank-1 company-disclosed FY2025 weighted-average operating-lease discount rate of **4.00%**. R&D useful life was already selected at **5 years** with `blocking=false`; it was shown on the Review tab but was not the pause condition. After the analyst approved the 4.00% rate, the run continued through Excel COM and valuation, then stopped on unrelated Gate G (`BUYBACK_DOLLARS_COVERAGE_INCOMPLETE`). That run’s audit trail contains `LEASE_RATE_APPROVED`, so it was **not** reused as the autonomous certification run.

## New LNN run — autonomous workflow

Status after first pass: `needs_review` (not `awaiting_analyst_review`).
Review path: `not_required` (no Approve click, no fabricated human approval).

| Gate | Result | Evidence |
| --- | --- | --- |
| Mode A + NewCompanyRunner first pass | **PASS** | `new_company_run_state.json` |
| Ten-year validation | **PASS** | `ten_year_source_coverage.json` |
| Autonomous lease-rate decision | **PASS** | `lease_rate_review.json` — 4.00% disclosed, `AUTONOMOUS_AGENT_DECISION` |
| Autonomous R&D useful life | **PASS** | `rd_useful_life_decision.json` — 5 years, SIC 3523, `AUTONOMOUS_AGENT_DECISION` |
| Genuine Excel COM CalculateFullRebuild | **PASS** | method `excel_com_calculate_full_rebuild`, Excel 16.0, `com_invoked=true`, status `ok` |
| Valuation judgment (ER/EV/OE/Graham) | **PASS** | KEEP_EXISTING / KEEP_REPORTED_BASE; original assumptions preserved; 0 HAP-introduced circulars |
| Gates A–F, H–L | **PASS** | `new_company_output_gate_report.json` |
| Gate G buybacks | **FAIL** | `BUYBACK_DOLLARS_COVERAGE_INCOMPLETE` for FY2017, FY2018, FY2019, FY2021 |
| Report authorization / Word | **FAIL** | Word withheld; not forced |

## Lease discount rate

- Selected rate: **4.00%** (0.04), effective period FY2025
- Classification: **disclosed**
- Decision class: **AUTONOMOUS_AGENT_DECISION**
- Source: SEC 10-K FY2025 accession `0001193125-25-248751`
- Methodology: `reported_weighted_average_discount_rate` (hierarchy A)
- Why selected: company-disclosed ASC 842 weighted-average operating-lease discount rate for the latest fiscal year
- Audit trail: `AUTONOMOUS_AGENT_DECISION` only — no `LEASE_RATE_APPROVED`
- `lease_rate_approved`: false

Workbook notes (HAP ANALYSIS, Leases L1:M8) record selected rate, classification, source filing, methodology, rationale, and limitations.

Leases row 18 in this Industrial Template is a formula (`=Inputs!C35/Inputs!C27`, interest expense / total debt). HAP did **not** overwrite those formulas. The disclosed 4.00% is recorded in the HAP ANALYSIS block rather than smashing the template methodology.

## R&D useful life

- Selected useful life: **5 years** (template B8 was 3; HAP wrote 5)
- SIC: **3523** Farm Machinery & Equipment
- Decision class: **AUTONOMOUS_AGENT_DECISION**
- Economic rationale: industrial machinery product-development cycle; life is not derived from annual R&D spend
- Capitalization: straight-line over 5 years; lookback FY2012–FY2025
- Notes: R&D P1:Q8 HAP ANALYSIS block plus A1 warning
- Blocking: false (run did not pause)

## Deliverables

- Completed workbook: `storage/outputs/07e53d34-7768-4d58-b84a-07af579fae14/completed_workbook.xlsx`
- Working Excel copy `2025 LNN FA.xlsx` exists as a run artifact
- Word analysis: **withheld** because Gate G failed
- Provenance: `new_company_assumption_notes.json` and `provenance_report.json`

## Why this is not READY_FOR_PRODUCTION

The autonomous-decision change did what it was asked to do: LNN no longer stops for routine lease-rate or R&D approval, Excel COM ran, valuation judgment ran, and Word stayed withheld when a required gate failed.

Gate G buyback-dollar coverage is still incomplete for four fiscal years. That blocker is unchanged from the previous LNN attempt and is **not** forced to pass.

The prior IDCC production certification is preserved and is not claimed to cover this workflow.

## Artifact directory

`C:\Users\Soulaymane Kachani\Downloads\HAP2\backend\storage\outputs\07e53d34-7768-4d58-b84a-07af579fae14`
