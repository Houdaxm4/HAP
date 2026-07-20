# Validation dataset strategy

Goal: assemble a large validation dataset (100+ real companies) **without fabricating financial data**, using official HAP v1 inputs.

## Official inputs per company

| Artifact | Required | Notes |
|----------|----------|-------|
| Prefilled Industrial Template (`.xlsx`) | Yes | Same family as production analyst workbooks |
| Bloomberg `Custom_Run_Filter_…-TICKER.xlsx` | Yes | Proprietary analytics; identical structure across tickers |
| Mapping CSV / cell routing file | **No** | Not a product input |

SEC companyfacts are fetched by the pipeline (network / cache), not assembled as static mapping rows.

## Package layout

```
validation_campaign/universe/TICKER/
  *Template*.xlsx
  Custom_Run_Filter*.xlsx
  manifest.json
```

## Do not fabricate

- Do not invent PE10 / quality scores / expected returns
- Do not convert Bloomberg workbooks into intermediate mapping CSVs
- Do not invent statement values to pad missing SEC tags — leave gaps; HAP must not fabricate

## Scaling approach

1. Prefer real Bloomberg Custom_Run exports already used by the analyst process
2. Pair each with the matching Industrial Template when available
3. Run the validation harness (`python -m validation`) which discovers workbook + Custom_Run pairs
4. Review failures for ingestion (parse/validate) vs analytical disagreement (engine scores)

## Documentation

- Architecture: [`docs/INGESTION_ARCHITECTURE.md`](../INGESTION_ARCHITECTURE.md)
- Campaign ops: [`docs/validation/VALIDATION_CAMPAIGN.md`](VALIDATION_CAMPAIGN.md)
- Readiness checklist: [`docs/validation/VALIDATION_READINESS_GUIDE.md`](VALIDATION_READINESS_GUIDE.md)
