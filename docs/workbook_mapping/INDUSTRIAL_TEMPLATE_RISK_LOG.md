# Industrial Template — Risk Log (M1)

Risks that may complicate Workbook Classification (M1.5) and Mapping (M2).

| ID | Risk | Evidence | Impact | Mitigation (later) |
|----|------|----------|--------|--------------------|
| R01 | Core statement 'label' fingerprint differs across suite | Almost entirely fiscal end-dates / FY window / year-embedded text — row counts match | Medium for period alignment (M5); Low for line-item skeleton | Map by stable line labels; resolve columns from each workbook's period headers |
| R02 | Sheet name sets identical across suite | All four share the same ordered sheet list | Low | Fingerprint on version upgrades |
| R07-Income - GAA | Core sheet `Income - GAAP` is data_heavy | formula_ratio=0.0605 | High for mapping — mix of inputs and formulas | M1.5 must mark writable regions cell-by-cell / by column band |
| R07-Balance Shee | Core sheet `Balance Sheet - Standardized` is data_heavy | formula_ratio=0.0201 | High for mapping — mix of inputs and formulas | M1.5 must mark writable regions cell-by-cell / by column band |
| R07-Cash Flow -  | Core sheet `Cash Flow - Standardized` is data_heavy | formula_ratio=0.009 | High for mapping — mix of inputs and formulas | M1.5 must mark writable regions cell-by-cell / by column band |
| R08 | Template version embedded in filenames (v27.6); quarters differ by ticker | AAPL Q2 / MSFT Q3 / AMZN Q1 / TJX Q4 — same v27.6 | Medium — period windows differ; structure should match | Period alignment milestone (M5); fingerprint on v27.8+ |
| R09 | openpyxl does not evaluate formulas; data_only=False inventory only | Cached values not treated as truth for formula cells | Medium for validation later | Excel-open checks in suite gate; never invent calculated values |
| R10 | Large used ranges / merged cells / freeze panes | See per-sheet summary in inventory MD | Low–Medium for writer address stability | Write by explicit addresses from mapping file only |
| R11 | Non-label structural diffs vs AAPL on some sheets | 4 sheets | Medium | Review suite_structural_diff.json before M2 |
| R12 | Sheet name `IC & NOPAT & ROIC ` has a trailing space | Exact name required in formula refs and openpyxl access | Medium — easy off-by-space bugs | Always use exact sheetnames from inventory JSON |
| R13 | openpyxl max_column can report 16382 (XFB) on statement sheets | Sparse dimension metadata; not a real 16k-column model | Low if scans/writes are bounded | Discover used period columns from header row, not max_column |
| R14 | Filename says Industrial Template v27.6 but Template Version sheet may say v27.7 | Observed on AAPL: Template Version!A2 = v27.7 | Medium — version identity ambiguous for regression | Fingerprint both filename token and Template Version sheet value |
| R15 | Annual control values live in C1:C3 (Ticker / Start Year / End Year), not B | Column B often blank/hidden on statement sheets | High if writer targets wrong column | M1.5/M2 treat C1–C3 as control cells on annual IS/BS/CF |

## Circular references

openpyxl cannot detect Excel iterative circulars reliably from static formulas alone. No CIRCULAR markers were required for inventory; treat potential circularity as **unknown / monitor** during Excel open tests in the suite gate.
