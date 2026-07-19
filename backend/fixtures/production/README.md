# Production Bloomberg Custom_Run_Filter workbooks

Place the **real** HAP production workbooks here. These files are the contract for the parser.

## Required for Sprint 5 completion

| File | Purpose |
|------|---------|
| `custom_run_filter_aapl.xlsx` | Production AAPL Bloomberg Custom_Run_Filter workbook |
| `custom_run_filter_aapl.profile.json` | Evidence-based layout profile derived from the AAPL workbook |

Optional cross-ticker evidence (only after AAPL profile is verified):

- `custom_run_filter_msft.xlsx`
- `custom_run_filter_amzn.xlsx`
- `custom_run_filter_tjx.xlsx`

## How to generate the profile

```bash
cd backend
python3 scripts/inspect_custom_run_workbook.py \
  fixtures/production/custom_run_filter_aapl.xlsx \
  -o fixtures/production/custom_run_filter_aapl.introspection.json
```

Review the introspection output, then author `custom_run_filter_aapl.profile.json` from that evidence.

The parser **must not** assume worksheet names. It reads only from the committed profile JSON.

## Do not use synthetic fixtures here

`backend/fixtures/custom_run_filter_aapl.example.xlsx` is a rejected Sprint 5 artifact with invented sheet names. It is not a production workbook and must not be used to validate the parser.
