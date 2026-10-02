# Annual Update Production Certification

Recommendation: **READY_FOR_PRODUCTION**

Regression: 515 passed, 1 skipped, 0 failed.

## Four-company matrix

| Company | FY | Factual | CRF | Tax | R&D | Leases | Formulas | HAP circ | COM | ER | OE | Graham | Base | Research | Disclosure | selected_normalized_base | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| JBSS | FY2026 | PASS | PASS | ok | ok | VALIDATED | PASS | 0 | genuine | KEEP_EXISTING | INSUFFICIENT_EVIDENCE | KEEP_EXISTING | materially_distorted | RESEARCHED | DISCLOSE_DISTORTED_BASE | None | ok |
| ETD | FY2026 | PASS | PASS | ok | ok | VALIDATED | PASS | 0 | genuine | ADJUST | KEEP_EXISTING | ADJUST | usable | NO_EXTERNAL_RESEARCH_REQUIRED | NO_DISCLOSURE_REQUIRED | None | ok |
| CSCO | FY2026 | PASS | PASS | ok | ok | VALIDATED | PASS | 0 | genuine | ADJUST | KEEP_EXISTING | KEEP_EXISTING | usable | NO_EXTERNAL_RESEARCH_REQUIRED | NO_DISCLOSURE_REQUIRED | None | ok |
| MZTI | FY2026 | PASS | PASS | ok | ok | VALIDATED | PASS | 0 | genuine | KEEP_EXISTING | KEEP_EXISTING | KEEP_EXISTING | potentially_distorted | NO_EXTERNAL_RESEARCH_REQUIRED | NO_DISCLOSURE_REQUIRED | None | ok |

## Cross-company invariants

- `no_historical_analyst_fs_overwritten_because_sec_differs`: PASS
- `no_formula_cells_source_filled`: PASS
- `no_hap_introduced_circulars`: PASS
- `no_stale_cache_valuation_conclusions`: PASS
- `no_hard_coded_valuation_growth_fallback`: PASS
- `er_oe_graham_independent_judgments`: PASS
- `base_normalization_independent_of_growth`: PASS
- `research_cannot_source_fill`: PASS
- `research_respects_analysis_as_of_date`: PASS
- `disclosure_cannot_select_normalized_base`: PASS
- `original_valuation_authoritative`: PASS
- `hap_analytical_changes_adjacent_and_labeled`: PASS

## Warnings / non-blocking notes

- JBSS output-gate warnings (4): PE10_PERIOD_NOTE: FY2026 fiscal-year PE10=13.9210 as of fiscal-year-end FY2026; current PE10=13.7473 as of CRF as-of / current. Distinct metrics — not PE10_CROSS_SHEET_MISMATCH.; OWNER_EARNINGS_GROWTH_IMPLAUSIBLE: owner-earnings growth -95.0% is economically extreme; verify tax/R&D/cash-flow inputs.; OWNER_EARNINGS_GROWTH_IMPLAUSIBLE: annualized owner-earnings growth -28.3% requires review.; Distinct metrics: Inputs!B69 Bloomberg Expected Return @ Current Price (57.13%) != Expected Returns!E14 (6.18%).
- ETD output-gate warnings (2): PE10_PERIOD_NOTE: FY2026 fiscal-year PE10=9.6782 as of fiscal-year-end FY2026; current PE10=9.1420 as of CRF as-of / current. Distinct metrics — not PE10_CROSS_SHEET_MISMATCH.; Distinct metrics: Inputs!B69 Bloomberg Expected Return @ Current Price (38.34%) != Expected Returns!E14 (1.73%).
- CSCO output-gate warnings (2): PE10_PERIOD_NOTE: FY2026 fiscal-year PE10=39.4003 as of fiscal-year-end FY2026; current PE10=38.9034 as of CRF as-of / current. Distinct metrics — not PE10_CROSS_SHEET_MISMATCH.; Distinct metrics: Inputs!B69 Bloomberg Expected Return @ Current Price (-40.89%) != Expected Returns!E14 (246.86%).
- MZTI output-gate warnings (2): PE10_PERIOD_NOTE: FY2026 fiscal-year PE10=18.0089 as of fiscal-year-end FY2026; current PE10=16.7503 as of CRF as-of / current. Distinct metrics — not PE10_CROSS_SHEET_MISMATCH.; Distinct metrics: Inputs!B69 Bloomberg Expected Return @ Current Price (96.07%) != Expected Returns!E14 (13.86%).

## Known limitations

- JBSS remains INSUFFICIENT_EVIDENCE on the OE base; HAP discloses the distortion and does not substitute a normalized base.
- FY2027 subsequent CapEx guidance is used in disclosure only when present in extracted research evidence.
- Normalized-base substitution and parallel EV are intentionally not implemented.

## JBSS disclosure text

Reported owner earnings of $2.0m are materially affected by elevated capital spending ($28.3m -> $50.7m -> $88.1m). Latest net income is about $61.9m and operating income about $89.2m, so the decline is not a collapse in earnings. Company filings identify an approximately $90 million equipment/infrastructure expansion program extending through early FY2027. HAP treats management's characterization of the program as evidence, not as an independently established conclusion about sustainable capital spending. HAP can infer that spending is elevated in connection with a disclosed investment program. HAP cannot determine sustainable post-project capital spending with sufficient confidence. HAP therefore retains the reported base and flags the resulting valuation for interpretation. HAP does not substitute a normalized owner-earnings figure. The current enterprise-value calculation begins from reported owner earnings of $2.0m. Because that base is materially affected by elevated investment spending, valuation outputs that extrapolate it should be interpreted cautiously. HAP has not changed the original valuation.
