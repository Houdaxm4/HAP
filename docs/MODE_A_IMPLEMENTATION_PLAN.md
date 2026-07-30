# Mode A Implementation Plan — Completed Industrial Template

**Goal:** Make the **completed Industrial Template** the real Mode A Excel deliverable, filled from `CompanyFinancialModel` while preserving formulas.  
**Out of scope until Mode A is done:** Word report, email, Mode B.  
**Product spine:** [`HAP_PRODUCT_SPEC.md`](HAP_PRODUCT_SPEC.md)

**Current baseline (repo facts):**
- `FillWorkbookStage` copies the template (`shutil.copy2`) and writes provenance JSON only.
- `WorkbookService.write_values()` can copy + write non-formula cells — **not wired** into the fill stage.
- `extract_statement_cells_from_sec` emits logical cells (`SEC!concept!period`), not Industrial Template addresses.
- CFM already holds annual IS/BS/CF series used by the Analysis Engine.
- Official validation suite packages live under `validation_campaign/universe/{AAPL,MSFT,AMZN,TJX}/`.

**Official regression suite:** [`VALIDATION_SUITE.md`](VALIDATION_SUITE.md) — **AAPL, MSFT, AMZN, TJX** (not examples).

---

## Working agreement (approved)

1. Execute **one milestone at a time**.
2. **Validation suite gate (required):** after each major milestone:
   1. Implement the milestone
   2. Run **AAPL** first
   3. Verify: Dashboard workflow, Pipeline, Deliverables, JSON artifacts, Excel workbook, Recommendation, Validation report
   4. Fix any issues
   5. Run **MSFT → AMZN → TJX**
   6. Confirm **all four** complete successfully  
   Only then is the milestone complete. If any of the four breaks, fix before continuing.
3. No Analysis Engine methodology changes in this Mode A track.
4. No Word / email / Mode B until Mode A Excel completion is done.

---

## Milestone 0 — Freeze product + stop divergent Excel work

| | |
|--|--|
| **Objective** | Align docs/code intent: Mode A deliverable = completed Industrial Template only. Pause/disable treating `hap_workbook.xlsx` as the product Excel. |
| **Files** | `docs/HAP_PRODUCT_SPEC.md` (done), `docs/HAP_DELIVERABLES_CONTRACT.md`, `docs/HAP_WORKBOOK_STRUCTURE_PROPOSAL.md`, `docs/PROJECT.md`; optionally demote `hap_workbook` in Deliverables UI label to “experimental/internal” or stop writing it in `run_analysis.py` |
| **Dependencies** | None |
| **Testing** | Doc review; dashboard still runs; `completed_workbook.xlsx` remains primary download |
| **Definition of done** | Spec frozen; team agrees Mode A Excel = Industrial Template; no further work on alternate Mode A workbook design |

**Gate:** Suite — AAPL first, then MSFT / AMZN / TJX. Dashboard still works; product docs reviewed; no regressions.

---

## Milestone 1 — Industrial Template inventory (AAPL reference) — **COMPLETE**

| | |
|--|--|
| **Objective** | Document the production template’s sheet list, period header rows/columns, and candidate **input** (non-formula) cells for core statement lines. |
| **Files** | `docs/workbook_mapping/` (inventory MD/JSON, dependency map, risk log, fingerprints); script `validation_campaign/_inspect_industrial_template.py` |
| **Dependencies** | M0; local suite templates |
| **Testing** | Script runs on all four suite templates; inventory lists all 24 sheets; core IS/BS/CF documented; suite diff recorded |
| **Definition of done** | Inventory checked into repo; enough structure known to support full-sheet classification in M1.5 |

**Deliverables:** see [`docs/workbook_mapping/README.md`](workbook_mapping/README.md).  
**Gate:** [`docs/workbook_mapping/M1_RELEASE_GATE_REPORT.md`](workbook_mapping/M1_RELEASE_GATE_REPORT.md) — **PASSED WITH MINOR ISSUES** (2026-07-27). Ready for M1.5 after your go-ahead.

---

## Milestone 1.5 — Workbook Classification — **COMPLETE**

| | |
|--|--|
| **Objective** | Fully understand the Industrial Template **before** writing any mapping specification. Classify **every sheet** and its important cells so M2 only maps into safe, intentional targets. |
| **Files** | Package `backend/workbook_mapping/` (Scanner, Classifier, ManifestBuilder, Statistics); docs `Workbook_Manifest.json`, `Workbook_Classification.md`, `Workbook_Statistics.md`, `Workbook_Architecture.md` |
| **Dependencies** | M1 |
| **Testing** | `python -m workbook_mapping`; `pytest tests/test_workbook_classification.py`; suite fingerprints identical across AAPL/MSFT/AMZN/TJX |
| **Definition of done** | All 24 sheets classified; non-blank cells classified; manifest is SSoT for future Excel ops |

**Deliverables:** [`docs/workbook_mapping/Workbook_Manifest.json`](workbook_mapping/Workbook_Manifest.json) (+ Classification / Statistics / Architecture MD).  
**Gate (next):** Review + suite dashboard run, then M2.

---

## Milestone 2 — Workbook Mapping Specification (v0.1) — **COMPLETE**

| | |
|--|--|
| **Objective** | Define the machine-readable contract: CFM field + period → template worksheet + cell, **only** into Writable Input cells from the M1.5 manifest. |
| **Files** | `docs/workbook_mapping/CFM_Workbook_Mapping.json` (+ MD coverage/unmapped reports); `backend/workbook_mapping/explicit_mappings.py`, `mapping_builder.py`, `mapping_schema.py`, `m2_cli.py` |
| **Dependencies** | M1.5 manifest |
| **Testing** | `python -m workbook_mapping.m2_cli`; `pytest tests/test_workbook_mapping_spec.py`; 0 unexplained writable cells; labels validated against manifest |
| **Definition of done** | Explicit deterministic mappings; coverage reports; no Excel writes |

**Gate (next):** Review + suite run, then M3 (write intents only).

---

## Milestone 3 — Workbook Mapping Engine (read path)

| | |
|--|--|
| **Objective** | Given CFM + mapping file, produce a list of `CellProvenance`-compatible write intents (worksheet, cell, value, concept, period) **without** writing Excel yet. |
| **Files** | New: `backend/workbook_mapping/engine.py`; new: `backend/tests/test_workbook_mapping_engine.py`; use `models/provenance.py` |
| **Dependencies** | M2; `CompanyFinancialModel` |
| **Testing** | Fixture CFM with known FY series → engine emits expected cell targets; skips missing periods/values; never invents numbers; reports unmapped CFM fields as warnings; refuses intents that violate classification if classification JSON is loaded |
| **Definition of done** | Pure function/API: `map_model_to_write_intents(model, mapping) -> list[WriteIntent]`; tests green |

**Gate:** Suite — AAPL → MSFT → AMZN → TJX (unit tests + full dashboard/pipeline checklist; fill behavior unchanged until M4).

---

## Milestone 4 — Wire formula-safe write into FillWorkbookStage

| | |
|--|--|
| **Objective** | Mode A fill: copy template → apply mapping engine intents via `WorkbookService.write_values` → keep provenance report for written cells. |
| **Files** | `backend/pipeline/stages/fill_workbook.py`; possibly `backend/pipeline/orchestrator.py` (pass CFM later or map from company_facts+custom_run interim); `backend/tests/test_pipeline.py`; `backend/tests/test_workbook_service.py` |
| **Dependencies** | M3; existing `write_values` |
| **Testing** | Pipeline test with sample workbook: formula cells unchanged; value cells updated where mapped; `completed_workbook.xlsx` exists; provenance lists fills + `skipped_formula` |
| **Definition of done** | Fill stage no longer “copy-only” for mapped cells; dashboard download opens a workbook with at least one verified populated line |

**Note:** Ideal input is CFM. If fill runs **before** `run_analysis` today, either (a) build a lightweight CFM earlier for fill, or (b) move fill-after-CFM / dual-pass. Prefer **build CFM once before fill** without changing Analysis Engine math — small orchestrator reorder is allowed if needed for this milestone.

**Gate:** Suite — **AAPL first** (full checklist including Excel + recommendation + validation report), fix issues, then **MSFT → AMZN → TJX**. All four must succeed.

---

## Milestone 5 — Period alignment (template FY columns ↔ CFM periods)

| | |
|--|--|
| **Objective** | Correctly bind CFM periods (`FY2024`, …) to template column headers (`2024 A`, dates, Start/End Year). |
| **Files** | `backend/workbook_mapping/periods.py`; mapping file metadata; tests with AAPL template headers from M1 |
| **Dependencies** | M4 |
| **Testing** | AAPL template: Start/End Year and column set match extracted headers; wrong-year writes impossible; unit tests for period parse/normalize |
| **Definition of done** | Documented period rules; AAPL mapped annual writes land in the correct FY columns |

**Gate:** Suite — AAPL → MSFT → AMZN → TJX; correct FY columns verified per ticker.

---

## Milestone 6 — Expand mapping coverage (statement depth)

| | |
|--|--|
| **Objective** | Map all CFM statement fields that have clear template line labels and Writable classification; leave nested FA children blank unless unambiguously matched. |
| **Files** | `industrial_template_v27.json` (expand); inventory/classification updates; `test_workbook_mapping_engine.py` |
| **Dependencies** | M5 |
| **Testing** | Coverage report: % of CFM series with ≥1 mapped cell; golden test on AAPL CFM from a real run artifact |
| **Definition of done** | All current CFM IS/BS/CF fields mapped or explicitly listed as `unmapped` with reason; no silent drops; no writes into Read-only regions |

**Gate:** Suite — AAPL → MSFT → AMZN → TJX; broader Excel spot-check on each.

---

## Milestone 7 — Production validation harness (deep checks)

| | |
|--|--|
| **Objective** | Automated + manual deep checks that completed workbooks are coherent vs production template expectations for the **full suite**. |
| **Files** | `validation_campaign/` scripts or `backend/tests/test_mode_a_workbook_suite.py`; checklist `docs/workbook_mapping/MODE_A_VALIDATION_CHECKLIST.md` |
| **Dependencies** | M6; all four packages in `validation_campaign/universe/` |
| **Testing** | Suite order AAPL → MSFT → AMZN → TJX; assert: sheet count/names stable; sample formulas still formulas; mapped cells numeric where CFM has values; units note (millions) documented; Deliverables download works |
| **Definition of done** | Checklist signed off for **all four**; failures logged with ticker + cell refs |

**Gate:** Formal suite sign-off (AAPL first, then MSFT / AMZN / TJX).

---

## Milestone 8 — Suite hardening + known-gap ledger

| | |
|--|--|
| **Objective** | Close remaining cross-ticker gaps; publish an explicit known-gap ledger for anything not yet mapped. (Suite already runs every milestone; this milestone is hardening, not “first multi-ticker.”) |
| **Files** | Mapping engine (fixes only); validation campaign runners; `docs/workbook_mapping/KNOWN_GAPS.md`; no methodology changes |
| **Dependencies** | M7 |
| **Testing** | Same deep checks as M7 for all four; period header differences handled or flagged |
| **Definition of done** | All four complete Mode A with populated `completed_workbook.xlsx`; known gaps listed and accepted |

**Gate:** Suite — AAPL → MSFT → AMZN → TJX; gap ledger reviewed.

---

## Milestone 9 — Dashboard / deliverable polish for Mode A

| | |
|--|--|
| **Objective** | Analyst UX: primary download is completed template; clear status if mapping partial; optional fill stats in Run activity / Verification. |
| **Files** | `frontend/.../DeliverablesTab.tsx`; `AnalysisHeader`; maybe validation report fields for `mapped_cells` / `skipped_formula` counts from fill stage |
| **Dependencies** | M7 |
| **Testing** | Manual suite: for each ticker create analysis → watch progress → Complete → Download `completed_workbook.xlsx` → open in Excel and spot-check Revenue/NI/Assets |
| **Definition of done** | Analyst can finish Mode A end-to-end from dashboard for all four suite companies and trust the Excel as the model deliverable |

**Gate:** Final Mode A UX acceptance on **AAPL → MSFT → AMZN → TJX**.

---

## Explicitly deferred (after Mode A)

| Item | When |
|------|------|
| Last Quarter template sheets | After annual path is solid |
| Writing into `Inputs` / overwriting ratio sheets | Avoid — let Excel formulas compute (Read-only per M1.5) |
| Word report | After Mode A |
| Email templates | After Word |
| Mode B blank-template clone + Yahoo | After Mode A |
| Recreating proprietary CRF metrics | Never recompute |

---

## Milestone sequence (updated)

```
M0 Freeze
 → M1 Inventory
 → M1.5 Classification
 → M2 Mapping Spec
 → M3 Mapping Engine
 → M4 Fill wiring
 → M5 Periods
 → M6 Coverage
 → M7 Deep validation harness (full suite)
 → M8 Suite hardening + known-gap ledger
 → M9 Dashboard polish
```

**After every milestone:** AAPL first → verify checklist → fix → MSFT → AMZN → TJX → all four green.

---

## Suggested next action

**M2 is complete — stop here for review.** After approval and suite gate, start **M3 Mapping Engine** (intents only; still no Excel writes).

Manifest SSoT: `docs/workbook_mapping/Workbook_Manifest.json`  
Mapping SSoT: `docs/workbook_mapping/CFM_Workbook_Mapping.json`
