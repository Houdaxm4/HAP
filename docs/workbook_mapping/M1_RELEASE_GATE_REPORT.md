# HAP — M1 Release Gate Report

**Date:** 2026-07-27  
**Milestone:** M1 — Industrial Template Inventory  
**Scope:** Documentation review + suite regression (AAPL / MSFT / AMZN / TJX)  
**Out of scope:** M1.5 classification, M2 mapping, workbook write engine, new features  

**Gate method:**
- Documentation review of `docs/workbook_mapping/` (gaps fixed during review)
- Full pipeline via `python -m validation` on `validation_campaign/universe` (4/4)
- Artifact inspection of CFM / engine / validation / provenance / Excel
- Dashboard + API smoke (`http://localhost:3000`, `http://127.0.0.1:8000`)

**Harness artifacts:** `validation_campaign/runs/m1_release_gate/results/`  
**Deep inspection:** `validation_campaign/runs/m1_release_gate/artifact_inspection.json`

---

## Recommendation

**M1 PASSED WITH MINOR ISSUES — proceed while tracking listed issues**

M1 inventory documentation is adequate for M1.5. All four suite companies complete the Mode A pipeline with CFM, validation (15/15), recommendation, and an unchanged Industrial Template copy as Excel output. Remaining issues are known / non-blocking for starting Workbook Classification.

---

## 1. Documentation Review

**Result: PASS** (after gap fixes applied during this gate)

### Verified

| Check | Result |
|-------|--------|
| Every worksheet documented (24/24) | Pass |
| Sheet purposes accurate vs real names (`IS%`, `BS%`, LQ packs, etc.) | Pass |
| Hidden sheets documented | Pass — **none** on any suite workbook (suite confirmation added) |
| Named ranges documented (CapIQ `IQ_*`, `SplitsByYear`, broken `SpreadsheetBuilder_*`) | Pass |
| Cross-sheet dependencies described | Pass — dependency map + inventory flow |
| Suite consistency (not AAPL-only) | Pass |
| Control cells C1:C3, units, FY headers | Pass |
| Role hints present but explicitly **not** write policy | Pass (clarified) |

### Issues discovered (and disposition)

| ID | Issue | Severity | Disposition |
|----|-------|----------|-------------|
| D1 | Inventory did not clearly separate M1 role hints from M1.5 Writable/Read-only | Medium (doc) | **Fixed** — added M1 vs M1.5 scope table + column layout (A/B/C) + canonical flow diagram |
| D2 | Hidden sheets note was AAPL-only | Low | **Fixed** — suite-wide zero hidden sheets confirmed |
| D3 | Dependency edge count said “75” after parser tightening (actual shared pairs = 46) | Low | **Fixed** — inventory text updated to 46 |
| D4 | Writable vs Read-only not classified | Expected | **Not a doc defect for M1** — deferred to M1.5 by design; samples only |
| D5 | Indentation shows 0 for most lines (alignment not used; CapIQ codes in col B) | Low | Noted in column-layout section; full hierarchy polish belongs in M1.5 |
| D6 | Filename `v27.6` vs Template Version sheet `v27.7` | Medium (known) | Already in risk log R14 — track in M1.5 fingerprints |

### Documentation files reviewed

- `INDUSTRIAL_TEMPLATE_INVENTORY.md` (updated)
- `INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md`
- `INDUSTRIAL_TEMPLATE_RISK_LOG.md`
- `industrial_template_v27_inventory.json`
- `industrial_template_v27_fingerprint.json`
- `suite_structural_diff.json`
- `README.md`

---

## 2. Regression Results

Harness: exit code **0**, wall ~421s, average ~104s/company.  
`validation_failures.log`: empty.

### Summary table

| Company | Result | Reason |
|---------|--------|--------|
| **AAPL** | **PASS WITH WARNINGS** | Pipeline complete; margins module skipped (scaffold); fill remains copy-only (expected M1) |
| **MSFT** | **PASS WITH WARNINGS** | Same as AAPL |
| **AMZN** | **PASS WITH WARNINGS** | Same as AAPL |
| **TJX** | **PASS WITH WARNINGS** | Same as AAPL; plus pre-existing `#N/A N/A` literals on DividendHelper (source template — **not** introduced by HAP; output SHA256 identical to source) |

### Analysis IDs (this gate)

| Ticker | analysis_id | Duration |
|--------|-------------|----------|
| AAPL | `7fe9fb27-5de0-46ad-8dd3-ee5070765a0e` | 105.8s |
| MSFT | `fc826b93-1b7f-49c1-abf7-518493f44fcb` | 102.5s |
| AMZN | `a35c3cc7-79d6-4ac0-bae6-7fab5989a870` | 104.0s |
| TJX | `254e036f-46fa-4f05-bc49-2a40528f7832` | 104.1s |

### Per-company checklist

#### Dashboard / API

| Check | AAPL | MSFT | AMZN | TJX |
|-------|------|------|------|-----|
| Listed on dashboard Active Analyses | Pass | Pass | Pass | Pass |
| Status Complete / 100% | Pass | Pass | Pass | Pass |
| Recommendation shown | Avoid | Avoid | Avoid | Avoid |
| API `GET /analysis/{id}` 200 | Pass | Pass* | Pass* | Pass* |
| Backend `/health` | Pass (shared) | | | |
| Frontend loads | Pass — Command Center at `:3000` | | | |

\*Suite created via validation harness (same orchestrator as dashboard `POST /run`). Dashboard UI confirmed listing + scores for all four. Full interactive create→upload→run from UI was not re-driven per ticker in this gate (pipeline coverage via harness + API detail for AAPL).

**Frontend note:** Next.js hydration warning in `Sidebar.tsx` (dev overlay) — does not block analysis listing or completion display.

#### Pipeline stages (all four)

`parse_workbook` → `parse_custom_run` → `fetch_sec_filings` → `fill_workbook` → `validate_workbook` → `run_analysis` → **complete**

No stage failures.

#### CompanyFinancialModel

| Check | Result (suite) |
|-------|----------------|
| Artifact present | Pass (all) |
| `reporting_currency` USD | Pass (AAPL inspected; others present) |
| Periods / IS / BS / CF series | Pass — AAPL: 10 periods; IS/BS/CF populated |
| Metadata present | Pass |
| Missing required CFM file | None |

#### JSON outputs

| Artifact | AAPL | MSFT | AMZN | TJX |
|----------|------|------|------|-----|
| `company_financial_model.json` | Pass | Pass | Pass | Pass |
| `analysis_engine_result.json` | Pass | Pass | Pass | Pass |
| `validation_report.json` | 15/15 pass | 15/15 | 15/15 | 15/15 |
| `provenance_report.json` | Present | Present | Present | Present |
| Module coverage | margins skipped | same | same | same |

#### Excel (`completed_workbook.xlsx`)

| Check | AAPL | MSFT | AMZN | TJX |
|-------|------|------|------|-----|
| Opens (openpyxl) | Pass | Pass | Pass | Pass |
| 24 sheets match template order | Pass | Pass | Pass | Pass |
| Named ranges preserved (37) | Pass | Pass | Pass | Pass |
| Formula sheets still formulas (e.g. IS%) | Pass (AAPL sampled) | Pass* | Pass* | Pass* |
| HAP-introduced `#VALUE!` / `#DIV/0!` / `#REF!` / `#NAME?` | None | None | None | None |
| Pre-existing `#N/A N/A` on DividendHelper | No | No | No | Yes (source = output byte-identical) |
| Structure unchanged vs input | Pass (M1 fill = copy) | Pass | Pass | Pass (SHA256 match source) |

\*Structure + formula preservation expected from copy-only fill; AAPL deep-sampled.

#### Recommendation / valuation / expected return

| Ticker | Rec | BQ | IA | Valuation module | Expected return module |
|--------|-----|-----|-----|------------------|------------------------|
| AAPL | AVOID | 78.17 High Quality | 46.29 Highly Overvalued | ok | ok |
| MSFT | AVOID | 84.11 Excellent | 45.89 Highly Overvalued | ok | ok |
| AMZN | AVOID | 65.83 Average | 45.30 Highly Overvalued | ok | ok |
| TJX | AVOID | 67.02 Average | 39.06 Highly Overvalued | ok | ok |

Supporting findings present in engine result (34–38 findings each). Recommendation confidence ~0.58–0.61.

#### Validation report

All four: **pass_count=15, warn_count=0, fail_count=0**, summary “All 15 checks passed.”

---

## 3. Bugs

### Critical

_None._

### High

_None blocking M1.5._

### Medium

| ID | Bug / defect | Evidence | Notes |
|----|--------------|----------|-------|
| B1 | `margins` analysis module still scaffold / skipped | All four suite runs | Known product gap; not introduced by M1 inventory; track outside M1.5 workbook work |
| B2 | Frontend React hydration error in `Sidebar.tsx` | DevTools overlay on dashboard | UX noise; analyses still list and open |

### Low

| ID | Bug / defect | Evidence | Notes |
|----|--------------|----------|-------|
| B3 | TJX DividendHelper contains `#N/A N/A` literals | Source template C24:D26 | Pre-existing company data; HAP copy preserves them — do not “fix” in fill |
| B4 | Historical failed AAPL analysis still visible in Active Analyses | Jul 19 CRF column error | Clutter; not a regression of this gate |
| B5 | Experimental `hap_workbook.xlsx` still written alongside completed template | Outputs folder | Product debt from M0; demote/stop later |

---

## 4. Technical Debt (before M1.5 — non-blocking)

1. **M1.5 must produce formal Writable / Read-only / Hybrid classification** — M1 only has formula-ratio hints.
2. **Period windows differ by ticker** (esp. TJX FY2017–2026) — mapping must bind columns per workbook headers (M5).
3. **Preserve exact sheet name** `IC & NOPAT & ROIC ` (trailing space).
4. **Fingerprint both** filename `v27.6` and sheet `v27.7`.
5. **Do not trust** broken `SpreadsheetBuilder_*` named ranges (`#REF!`).
6. **openpyxl `max_column=16382` artifact** — never use as write bounds.
7. **Margins module** completion is independent of workbook classification.
8. **Dashboard interactive upload path** not re-exercised end-to-end in this gate for every ticker (harness covers pipeline; optional follow-up UX pass).

---

## 5. Conclusion

| Gate question | Answer |
|---------------|--------|
| Can another developer understand the Industrial Template without Excel? | **Yes** (with inventory + dependency map + JSON) |
| Enough to begin M1.5 classification? | **Yes** |
| Enough foundation for M2 mapping later? | **Yes**, after M1.5 write policy |
| Suite regression green? | **Yes (4/4)** with documented warnings |

### Final recommendation (required wording)

**M1 PASSED WITH MINOR ISSUES — proceed while tracking listed issues**

Do **not** start the workbook mapping engine.  
Do **not** implement M1.5 in this gate task — wait for explicit go-ahead, then begin Workbook Classification only.

---

## Appendix — Commands used

```text
cd backend
python -m validation --input ../validation_campaign/universe --output ../validation_campaign/runs/m1_release_gate/results --log-level INFO

python validation_campaign/runs/m1_release_gate/_inspect_artifacts.py
```

Backend: `uvicorn main:app --host 127.0.0.1 --port 8000`  
Frontend: `npm run dev` → `http://localhost:3000`
