# Unmapped CFM Metrics (M2)

Statement and control fields without an explicit M2 v0.1 mapping, or explicitly deferred.

| CFM path | Reason | Suggested action |
|----------|--------|------------------|
| `balance_sheet.total_debt` | No single Total Debt line on Balance Sheet - Standardized | Future: composite ST Debt row 70 + LT Debt row 86 (not in M2 v0.1 single-cell map) |
| `balance_sheet.invested_capital` | Invested Capital is not a line on Balance Sheet - Standardized (lives on IC & NOPAT & ROIC sheet, Read-only) | Leave to Excel IC sheet; do not write statement grid |
