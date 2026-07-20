# Validation readiness guide (HAP v1 ingestion)

Official product inputs:

1. **Prefilled workbook** — Industrial Template (`.xlsx`)
2. **Bloomberg Custom_Run_Filter** — proprietary analytics workbook (`.xlsx`)

Plus: **SEC filings / companyfacts** fetched by the pipeline and optional market overlays from Custom_Run.

See also: [`docs/INGESTION_ARCHITECTURE.md`](../INGESTION_ARCHITECTURE.md).

## What is *not* a product input

Do **not** create or upload:

- worksheet / cell / concept / period mapping CSVs
- internal routing tables that tell HAP which template cell to write

Those were an engineering diversion. HAP v1 validates and imports the Bloomberg Custom_Run_Filter directly.

## Company package layout

```
TICKER/
  TICKER … Industrial Template ….xlsx
  Custom_Run_Filter_…-TICKER.xlsx
  manifest.json   # optional for the validation harness
```

Examples that share the same Custom_Run structure: AAPL, MSFT, AMZN, TJX.

## Custom_Run_Filter expectations

| Check | Expectation |
|-------|-------------|
| Format | `.xlsx` (Bloomberg-derived) |
| Sheets | Ticker sheet + `Summary` |
| Summary | Wide header + one company row (~111 fields) |
| History | Sufficient periods and series for proprietary analytics |
| Proprietary fields | PE10 / E10 / WACC / quality / expected-return style fields present when the Bloomberg export provides them |

HAP **imports** proprietary metrics and **never recomputes** them.

## Prefilled workbook expectations

- Official Industrial Template (or equivalent formal template)
- Statement sheets and formulas as designed by the analyst process
- No requirement that every SEC value be pre-written for ingestion to reach AnalysisEngine

## Pipeline gate

A package is ingestion-ready when:

1. Prefilled workbook is uploaded
2. Custom_Run_Filter `.xlsx` parses into `CustomRunData`
3. Custom_Run validation does not fatal on required structure/fields
4. SEC companyfacts resolve for the ticker

Failure modes that previously said “missing columns: worksheet, cell, concept, period” are obsolete — they indicated the wrong parser.

## Validation campaign tip

Prefer dropping the real Bloomberg Custom_Run_Filter next to the template. Do not synthesise mapping tables to “make the old parser happy.”
