# HAP Validation Campaign

Version: 5.1  
Status: Review process (no engine changes)

---

## Purpose

HAP feature development is paused for this campaign.

The goal is to **validate the analytical engine** against real companies: confirm that scores, valuations, expected returns, and recommendations are coherent, evidence-backed, and usable — without changing methodology, scoring, weights, valuation logic, or recommendation rules.

This document defines:

1. Campaign workflow
2. Per-company review checklist
3. Anomaly definitions (what to flag)
4. How to use the review templates

Related artifacts from Sprint 5:

- `validation_results.csv` — batch numeric snapshot
- `validation_summary.md` — batch counts and coverage
- `validation_failures.log` — pipeline failures

Review templates:

- [COMPANY_REVIEW_TEMPLATE.md](./COMPANY_REVIEW_TEMPLATE.md) — one file (or copy) per company
- [BATCH_REVIEW_LOG.md](./BATCH_REVIEW_LOG.md) — campaign-level tracker

---

## Principles

1. **Do not modify code** during this campaign unless a separate engineering ticket is opened after review consensus.
2. **Do not “fix” scores by hand.** Record disagreements as review notes and anomalies.
3. **Separate pipeline failure from analytical doubt.** A failed run is not the same as a suspicious score.
4. **Confidence qualifies reliability; it does not change the score.** Low confidence + high score must be treated carefully.
5. **Business Quality ≠ Investment Attractiveness.** Excellent businesses can rightly get weak recommendations at rich prices.

---

## Campaign workflow

### Phase A — Prepare the batch

1. Assemble company packages (workbook + `custom_run_filter`) per Sprint 5 layout.
2. Run the validation harness:

   ```text
   cd backend
   python -m validation --input <companies_dir> --output <results_dir>
   ```

3. Confirm `validation_results.csv` and `validation_summary.md` exist.
4. Open `validation_failures.log` and list hard failures (no engine result).

### Phase B — Triage

Sort companies into buckets before deep review:

| Bucket | Criteria | Action |
|--------|----------|--------|
| **Hard fail** | Status ≠ success / pipeline error | Log root cause; no score review until re-run succeeds |
| **Empty / thin** | Success but missing BQ, IA, recommendation, FV, or price | Flag Empty outputs; prioritize |
| **Incomplete modules** | Failed or skipped modules | Flag Failed module executions |
| **Review queue** | Success with full headline fields | Full company review template |
| **Hold for later** | Low priority / incomplete filings | Note and defer |

### Phase C — Per-company review

For every company in the review queue (and for thin/incomplete cases once data allows):

1. Copy [COMPANY_REVIEW_TEMPLATE.md](./COMPANY_REVIEW_TEMPLATE.md).
2. Fill headline fields from engine outputs / CSV.
3. Walk the checklist (below).
4. Mark anomalies using the definitions in this document.
5. Assign a **manual verdict**: Accept / Accept with caveats / Reject for re-run / Escalate methodology question.
6. Log the company in [BATCH_REVIEW_LOG.md](./BATCH_REVIEW_LOG.md).

### Phase D — Campaign synthesis

After the batch:

1. Count Accept / Caveats / Reject / Escalate.
2. Group anomalies by type (suspicious scores, contradictions, missing series, etc.).
3. Write a short campaign memo: patterns that look like data issues vs. patterns that look like engine behavior worth a future ticket.
4. **Do not change the engine** in this sprint; open tickets only.

---

## Required fields per company review

Every reviewed analysis must record:

| Field | Source guidance |
|-------|-----------------|
| **Company** | Analysis / manifest / folder name |
| **Industry** | Manual (workbook cover, filings, or analyst knowledge) — not invent if unknown; mark `Unknown` |
| **Business Quality score** | Engine `business_quality.score` (+ rating/label) |
| **Investment Attractiveness score** | Engine `investment_attractiveness.score` (+ rating/label) |
| **Recommendation** | Engine recommendation code/label |
| **Valuation summary** | Fair value (base), current price, margin of safety, method notes if visible |
| **Expected Return** | Expected CAGR / IRR from engine metrics |
| **Missing data** | Gaps that reduced coverage (see checklist) |
| **Failed modules** | Modules with `status` = `error` (and note `skipped`) |
| **Confidence** | Module / recommendation / overall confidence as available in artifacts |
| **Manual review notes** | Free-text analyst judgment |

Use the company template; do not leave required fields blank — use `N/A`, `Unknown`, or `Not produced`.

---

## Review checklist

Complete in order. Check each item when done.

### 1. Identity and run integrity

- [ ] Company name and ticker match the intended package
- [ ] Industry recorded (or explicitly `Unknown`)
- [ ] Pipeline status = success (else stop and treat as hard fail)
- [ ] Engine version recorded
- [ ] Analysis duration noted (extreme runtimes may indicate data/network issues)

### 2. Headline analytical outputs

- [ ] Business Quality score and rating present
- [ ] Investment Attractiveness score and rating present
- [ ] Recommendation present
- [ ] Valuation summary filled (FV, price, MoS at minimum)
- [ ] Expected Return present
- [ ] Confidence recorded (or explicitly `Not produced`)

### 3. Empty outputs screen

- [ ] No required headline field is blank when status = success
- [ ] Modules that should have run are not empty shells (no metrics, no findings, no score)
- [ ] Recommendation is not silently missing when BQ and IA exist

→ If any fail: mark **Empty outputs**.

### 4. Failed modules screen

- [ ] List modules with `status = error`
- [ ] List modules with `status = skipped` and note reason if available
- [ ] Confirm failed modules are reflected in confidence / coverage notes

→ If any errors: mark **Failed module executions**.

### 5. Missing financial series screen

- [ ] Income / balance / cash flow history length adequate for the modules that scored (prefer 5–10 years per playbook)
- [ ] Critical series for scored components are present (e.g. revenue, FCF, shares, price where valuation/ER require them)
- [ ] Gaps are explained by missing data notes — not hidden by invented values

→ If material gaps: mark **Missing financial series**.

### 6. Suspicious scores screen

- [ ] BQ and IA are each in a plausible 0–100 band (or documented scale)
- [ ] Extreme scores (e.g. ~0 or ~100) have supporting module scores/findings
- [ ] High BQ with very low IA (or reverse) is consistent with valuation/ER narrative
- [ ] Confidence is not high when coverage is obviously thin

→ If doubtful: mark **Suspicious scores**.

### 7. Contradictory recommendation screen

- [ ] Recommendation is consistent with the published BQ × IA matrix philosophy (see below)
- [ ] Strong Buy / Buy is not paired with “Avoid at Current Price” IA without explanation
- [ ] Avoid is not paired with elite BQ *and* elite IA without explanation
- [ ] `Insufficient Data` appears only when scores/coverage truly insufficient
- [ ] Speculative / Watch cases include reasons aligned with methodology

→ If inconsistent with matrix or narrative: mark **Contradictory recommendations**.

### 8. Valuation and expected return coherence

- [ ] Fair value vs price implies MoS in the expected direction
- [ ] Expected return sign/magnitude roughly consistent with MoS and growth assumptions (order-of-magnitude check, not a re-price)
- [ ] Valuation confidence (if present) aligns with method coverage / assumption quality

### 9. Manual verdict

- [ ] Verdict selected
- [ ] Manual review notes written (even if “Looks consistent; no issues”)
- [ ] Anomalies listed in batch log
- [ ] Follow-up action noted (none / re-run / data fix / escalate)

---

## Anomaly definitions

Use these labels consistently in templates and the batch log.

### Suspicious scores

Flag when any of the following hold:

- Headline score extreme without matching module evidence
- Module scores imply a very different roll-up than BQ/IA shown
- High score with low confidence and sparse history presented as high conviction
- Score present while most contributing modules are skipped/error
- Implausible combinations (e.g. near-perfect profitability with empty income series)

**Not automatically suspicious:** High BQ + low IA (quality expensive) or low BQ + high IA (cheap low quality) — those can be correct; still verify narrative.

### Empty outputs

Flag when status is success (or engine result exists) but:

- BQ, IA, recommendation, fair value, current price, MoS, or expected return is missing/`Not produced` unexpectedly
- A module result exists with no metrics, no findings, and no usable score/status detail
- Aggregators empty while constituent modules claim `ok`

### Contradictory recommendations

Flag when recommendation conflicts with scores under HAP’s separation of quality vs price, including:

| Pattern | Why it is suspicious |
|---------|----------------------|
| Strong Buy / Buy with BQ clearly weak and IA not compensating per matrix | Matrix misalignment |
| Avoid with both BQ and IA in clearly strong bands | Matrix misalignment |
| Insufficient Data while BQ and IA both fully scored with high confidence | Over-use of insufficient path — *or* scores should not have been emitted |
| Recommendation text/reasons that reverse the scores (e.g. “overvalued” while IA is elite and MoS large) | Narrative contradiction |
| Watch/Wait for better price when MoS is already large *and* IA is elite | Possible inconsistency — verify matrix band |

Reference philosophy (`SCORING_SYSTEM.md`): wonderful business + insufficient margin of safety → Watch-type outcome is **expected**, not contradictory.

### Missing financial series

Flag when:

- History shorter than module needs for claimed CAGRs/stability
- Price, shares, FCF, revenue, or other method-critical series absent while valuation/ER/BQ components still score as complete
- Large holes mid-series without provenance/missing-data notes
- Industry/peer context required by a module is absent and the module still asserts full coverage

### Failed module executions

Flag when:

- Any module `status = error`
- Pipeline complete but one or more analytical modules never produced a result object
- Aggregator ran while a required upstream module failed without clear renormalization/coverage note

Skipped modules due to documented missing inputs are **coverage issues** (often also Missing financial series); they are not always “failed executions.” Record both when relevant.

---

## Recommendation sanity reference (review aid only)

This is a **review aid**, not a reimplementation. When in doubt, compare against `docs/SCORING_SYSTEM.md` Final Recommendation Matrix.

Illustrative expectations:

- Very high BQ + very high IA → Strong Buy / Buy family
- Very high BQ + modest IA → Watch / wait-for-price family is plausible
- Weak BQ → Avoid family is plausible regardless of cheapness
- High IA + mediocre BQ → Speculative / analyst review family is plausible
- Missing BQ or IA → Insufficient Data is plausible

Any Strong Buy on a business the reviewer judges low quality **must** be flagged even if the matrix formally allows the path — capture as manual doubt plus anomaly if matrix also fails.

---

## Manual verdicts

| Verdict | Meaning |
|---------|---------|
| **Accept** | Outputs coherent; anomalies none or immaterial |
| **Accept with caveats** | Usable, but missing data / low confidence / minor anomalies documented |
| **Reject for re-run** | Data package, upload, or pipeline issue; re-run after fix |
| **Escalate** | Possible methodology / engine behavior question; no code change in this campaign — ticket only |

---

## Campaign exit criteria

The campaign may close when:

1. Every successful company in the batch has a completed company review template **or** an explicit deferral reason in the batch log.
2. Every hard failure is logged with cause.
3. Anomaly counts by type are summarized.
4. Escalations (if any) are listed as future tickets — **engine unchanged**.

---

## What this campaign does not do

- Does not change scoring, weights, valuation, or recommendation rules
- Does not treat reviewer preference as a score override
- Does not require fixing the product mid-campaign
- Does not replace unit tests; it validates real-company behavior
