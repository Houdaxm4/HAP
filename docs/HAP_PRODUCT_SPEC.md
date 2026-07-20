# HAP Product Specification (Frozen)

**Status:** Official product vision — frozen 2026-07-20  
**Supersedes conflicting earlier sketches** where they disagree with this document.

---

## Purpose

HAP is an end-to-end equity research platform.

It analyzes any public company and produces professional analyst deliverables.

- The analytical engine is **deterministic**.
- **`CompanyFinancialModel` is the single source of truth** for financial inputs to analysis.
- Every output is generated from:
  - `CompanyFinancialModel`
  - Analysis Engine
  - Validation
  - Provenance
- **No presentation layer** (Excel fill, Word, email, UI) may perform independent financial calculations.

---

## Analysis modes

| Mode | Inputs |
|------|--------|
| **A** | Industrial Template + Custom Run Filter + SEC EDGAR (+ public sources when needed) |
| **B** | Company ticker + SEC EDGAR + Yahoo Finance + other reliable public sources |

Both modes build **exactly the same** `CompanyFinancialModel` and run **exactly the same** Analysis Engine.  
Only the **data source** changes.

---

## Deliverables (every completed analysis)

### 1. Excel workbook — the financial model

| Mode | Deliverable |
|------|-------------|
| **A** | The **completed Industrial Template** (preserve structure/formulas; populate inputs; validate) |
| **B** | A workbook that **closely follows** the Industrial Template structure and analyst workflow, using only public data |

The workbook is the model. It is **not** a separate HAP-only redesign for Mode A.

### 2. Word report — the investment thesis

Professional equity research narrative (not an Excel dump). Explains business, history, performance, risks, opportunities, then answers:

1. **Is this a high-quality company with strong long-term fundamentals?** → Business Quality analysis  
2. **Should we buy today or is it overpriced?** → primarily **Owner Earnings Projection** vs current market price  

Other valuation methods may support; OE drives the decision. Compare **Current Market Price vs Estimated Intrinsic Value** and justify the recommendation.

### 3. Email (after both deliverables)

Draft using one of: New Company / Annual Update / Quarterly Update.  
Summary of the report only — **no new analysis**.

---

## Current development priority

**Complete Mode A first.** Do not start Word, email, or Mode B until Mode A Excel completion is done.

Mode A sequence:

1. Completed Industrial Template is the real Excel deliverable  
2. Workbook Mapping Specification  
3. Workbook Mapping Engine  
4. Populate template from `CompanyFinancialModel` (preserve formulas)  
5. Validate against the official regression suite  

Then: Word → Email → Mode B.

---

## Official validation suite

**AAPL, MSFT, AMZN, TJX** are HAP’s official regression suite (not examples).

Every major milestone must pass: AAPL first → fix → MSFT → AMZN → TJX → all four successful, before continuing.

Full workflow and checklist: [`VALIDATION_SUITE.md`](VALIDATION_SUITE.md)

---

## Related implementation docs

- Validation suite: [`VALIDATION_SUITE.md`](VALIDATION_SUITE.md)
- Mode A milestones: [`MODE_A_IMPLEMENTATION_PLAN.md`](MODE_A_IMPLEMENTATION_PLAN.md)
- Ingestion: `docs/INGESTION_ARCHITECTURE.md`
- Prior deliverables note: `docs/HAP_DELIVERABLES_CONTRACT.md` (aligned with this freeze)
