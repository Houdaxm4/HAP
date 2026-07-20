# Sprint 5.3 — Validation Campaign Execution

Status: **Blocked on real workbook inputs** (analytical engine unchanged)

## What was completed

1. **Validation universe assembled:** 91 companies across 10 sectors and 5 sampling quality tiers  
   - Catalog: `VALIDATION_UNIVERSE.csv`  
   - Packages: `universe/<TICKER>/manifest.json`

2. **Input readiness verified before execution**  
   - Report: `reports/INPUT_READINESS_REPORT.md`  
   - Detail: `reports/INPUT_READINESS.csv`  
   - Result: **0 READY / 91 INCOMPLETE** (missing `workbook` + `custom_run_filter` for every package)

3. **Validation harness executed** (continue-on-failure path exercised)  
   - Output: `results/validation_results.csv`  
   - Summary: `results/validation_summary.md`  
   - Result: **0 runnable cases** (discovery skipped all packages lacking workbooks)

4. **Validation campaign report + manual review priority list produced**  
   - `reports/VALIDATION_CAMPAIGN_REPORT.md`  
   - `reports/MANUAL_REVIEW_PRIORITY_LIST.md`  
   - `reports/MANUAL_REVIEW_PRIORITY_LIST.csv`

## What was not modified

- Analytical modules, scoring, weights, valuation methodology, recommendation thresholds, aggregation

## Required inputs to unblock analytical validation

Place files in each `universe/<TICKER>/` folder:

| File | Required |
|------|----------|
| `workbook.xlsx` (or `prefilled*.xlsx`) | Yes |
| `custom_run_filter.csv` (or `.xlsx`) | Yes |
| `manifest.json` | Already present |

Then re-run:

```text
python validation_campaign/_check_inputs.py
cd backend
python -m validation --input ../validation_campaign/universe --output ../validation_campaign/results
python ../validation_campaign/_rank_results.py
```

After successful runs, the ranking report will prioritize failed modules, missing series, low confidence, contradictions, and recommendation anomalies from harness outputs.

## Universe coverage

| Sector | Count |
|--------|------:|
| Technology | 11 |
| Financials | 10 |
| Consumer Staples | 10 |
| Consumer Discretionary | 10 |
| Industrials | 10 |
| Healthcare | 10 |
| Energy | 8 |
| Utilities | 8 |
| REITs | 8 |
| Telecommunications | 6 |
| **Total** | **91** |

| Sampling quality tier | Count |
|-----------------------|------:|
| Exceptional | 4 |
| Excellent | 38 |
| Average | 38 |
| Weak | 9 |
| Distressed | 2 |

Sampling tiers are campaign design labels only — not HAP engine scores.

## Current manual review priority (top)

Highest priority until workbooks arrive: **incomplete inputs** in methodology-sensitive sectors (Financials, REITs, Utilities, Energy, Telecom) and extreme sampling tiers (Weak / Distressed / Exceptional). See `reports/MANUAL_REVIEW_PRIORITY_LIST.md`.
