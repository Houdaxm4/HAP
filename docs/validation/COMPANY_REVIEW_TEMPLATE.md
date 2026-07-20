# Company Review Template

Sprint 5.1 — Validation Campaign  
Copy this file once per company (e.g. `reviews/AAPL.md`). Do not edit engine code during review.

---

## Header

| Field | Value |
|-------|-------|
| Company | |
| Ticker | |
| Industry | |
| Engine version | |
| Analysis ID | |
| Reviewer | |
| Review date | |
| Pipeline status | success / failed / other: |
| Source batch / CSV row | |

---

## Headline outputs

| Field | Value | Notes |
|-------|-------|-------|
| Business Quality score | | |
| Business Quality rating | | |
| Investment Attractiveness score | | |
| Investment Attractiveness rating | | |
| Recommendation (code) | | |
| Recommendation (label) | | |
| Expected Return | | metric used: CAGR / IRR / other |
| Confidence | | source: recommendation / modules / overall |
| Missing data | | summarize gaps; or `None noted` |
| Failed modules | | list `error` modules; or `None` |
| Skipped modules | | list; or `None` |

### Valuation summary

| Item | Value |
|------|-------|
| Fair value (base) | |
| Current price | |
| Margin of safety | |
| Fair value range (if available) | |
| Methods used / notes | |

**Valuation narrative (1–3 sentences):**



---

## Checklist (mark Y / N / N/A)

| # | Item | Y/N/N/A |
|---|------|---------|
| 1 | Identity matches intended company package | |
| 2 | Industry recorded or explicitly Unknown | |
| 3 | Pipeline success and engine result present | |
| 4 | All headline fields populated or explicitly Not produced | |
| 5 | Empty outputs screened | |
| 6 | Failed / skipped modules screened | |
| 7 | Missing financial series screened | |
| 8 | Suspicious scores screened | |
| 9 | Contradictory recommendation screened | |
| 10 | Valuation vs MoS vs Expected Return order-of-magnitude check | |

---

## Anomalies identified

Check all that apply:

- [ ] Suspicious scores
- [ ] Empty outputs
- [ ] Contradictory recommendations
- [ ] Missing financial series
- [ ] Failed module executions
- [ ] None

**Anomaly detail** (what, where in artifacts, why it matters):



---

## Module coverage snapshot

| Module | Status (ok / skipped / error) | Confidence (if any) | Reviewer note |
|--------|-------------------------------|---------------------|---------------|
| Profitability | | | |
| Growth | | | |
| Margins | | | |
| Cash flow | | | |
| Balance sheet | | | |
| Capital allocation | | | |
| Business outlook | | | |
| Valuation | | | |
| Expected return | | | |
| Recommendation | | | |
| Other: | | | |

---

## Coherence notes

**BQ vs IA:**  
*(Does the quality vs price split make sense?)*



**Recommendation vs matrix philosophy:**  
*(Aligned / Unclear / Contradictory — cite scores)*



**Data adequacy:**  
*(History length, price, key series)*



---

## Manual review notes



---

## Verdict

| Field | Value |
|-------|-------|
| Manual verdict | Accept / Accept with caveats / Reject for re-run / Escalate |
| Follow-up | none / re-run / fix data package / open ticket |
| Ticket / issue ID (if any) | |
| Ready to count in campaign totals? | Yes / No |

**Verdict rationale (required):**


