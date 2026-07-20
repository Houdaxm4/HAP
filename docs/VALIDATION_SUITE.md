# HAP Official Validation Suite

**Status:** Official — approved 2026-07-20  
**These four companies are HAP’s regression suite.** They are not examples.

## Members

| Ticker | Package location |
|--------|------------------|
| **AAPL** | `validation_campaign/universe/AAPL/` |
| **MSFT** | `validation_campaign/universe/MSFT/` |
| **AMZN** | `validation_campaign/universe/AMZN/` |
| **TJX** | `validation_campaign/universe/TJX/` |

Each package must include the Mode A inputs required for a full dashboard run (Industrial Template + Custom Run Filter + manifest as applicable).

---

## Rule

**Every major milestone must pass the suite before development continues.**

If a milestone breaks any of the four companies, **fix that before moving on**.

A milestone is complete only when **all four** complete successfully under the checklist below.

---

## Development workflow (required)

1. **Implement ONE milestone.**
2. **Run AAPL first.**
3. **Verify for AAPL:**
   - Dashboard workflow
   - Pipeline
   - Deliverables
   - JSON artifacts
   - Excel workbook (`completed_workbook.xlsx`)
   - Recommendation
   - Validation report
4. **Fix any issues found.**
5. **Run:** MSFT → AMZN → TJX
6. **Confirm all four complete successfully.**

Only then is the milestone considered complete.

---

## Per-company verification checklist

Use this for each ticker in the suite:

| Check | Pass criteria |
|-------|----------------|
| **Dashboard workflow** | Create/open analysis; progress advances; status reaches Complete (or expected terminal state for that milestone) |
| **Pipeline** | All stages succeed; no unhandled stage failure |
| **Deliverables** | Expected downloads present in Deliverables (at minimum `completed_workbook.xlsx` for Mode A) |
| **JSON artifacts** | Core outputs present and readable (e.g. CFM / analysis engine result / provenance / validation as applicable to the milestone) |
| **Excel workbook** | Opens; structure intact; formulas preserved where required; mapped values correct when fill is in scope |
| **Recommendation** | Present and coherent with engine output (not blank/corrupt) |
| **Validation report** | Present; review for new failures vs pre-milestone baseline |

---

## Scope notes

- **Doc-only / inventory milestones** (e.g. M1, M1.5): still run the suite to prove the pipeline did not regress; Excel fill behavior may be unchanged. Structure/classification work must still be checked for consistency across all four templates where relevant.
- **Runtime milestones** (fill wiring, period alignment, mapping coverage, UI): full checklist is mandatory for all four.
- Expanding the suite later is allowed; these four remain the **minimum** gate until explicitly revised.

---

## Related docs

- Mode A milestones: [`MODE_A_IMPLEMENTATION_PLAN.md`](MODE_A_IMPLEMENTATION_PLAN.md)
- Product freeze: [`HAP_PRODUCT_SPEC.md`](HAP_PRODUCT_SPEC.md)
- Broader campaign process: [`validation/VALIDATION_CAMPAIGN.md`](validation/VALIDATION_CAMPAIGN.md)
