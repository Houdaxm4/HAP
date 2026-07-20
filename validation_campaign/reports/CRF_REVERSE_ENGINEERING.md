# Custom_Run_Filter Reverse-Engineering Report

**Source of truth:** production workbooks under `validation_campaign/universe/`

Companies inspected:
- `AAPL` — `Custom_Run_Filter_2026-05-04-(19-46)-AAPL.xlsx`
- `MSFT` — `Custom_Run_Filter_2026-05-27-(15-48)-MSFT.xlsx`
- `AMZN` — `Custom_Run_Filter_2026-05-04-(17-30)-AMZN.xlsx`
- `TJX` — `Custom_Run_Filter_2026-04-06-(16-43)-TJX.xlsx`

No worksheet names or layouts were invented; all findings below were observed in these files.

## 1. Worksheets

| Company | Sheet order | Ticker sheet |
|---------|-------------|--------------|
| AAPL | `['AAPL', 'Summary']` | `AAPL` |
| MSFT | `['MSFT', 'Summary']` | `MSFT` |
| AMZN | `['AMZN', 'Summary']` | `AMZN` |
| TJX | `['TJX', 'Summary']` | `TJX` |

### Common schema

- Every workbook has exactly two worksheets: **`<TICKER>`** then **`Summary`**.
- The ticker worksheet name matches the equity ticker (AAPL, MSFT, AMZN, TJX).
- `Summary` is always present and is the second sheet.

## 2. Ticker sheet table layout (observed anchors)

| Company | date row | Fiscal Quarter row | Fiscal Year row | period width | scalar start | numeric trailer start | rows × max width |
|---------|----------|--------------------|-----------------|--------------|--------------|----------------------|------------------|
| AAPL | 15 | 16 | 146 | 102 | 158 | 265 | 4172 × 103 |
| MSFT | 15 | 16 | 146 | 102 | 158 | 265 | 4180 × 103 |
| AMZN | 15 | 16 | 146 | 102 | 158 | 265 | 4169 × 103 |
| TJX | 15 | 16 | 146 | 102 | 158 | 265 | 4195 × 103 |

**Anchors are identical across all four companies:** `{'date': 15, 'Fiscal Quarter': 16, 'Fiscal Year': 146}`.

### Observed regions (from anchors)

1. **Title** — row 1 (Bloomberg equity title string).
2. **Meta key/value block** — rows 2 through just above `date` (observed meta labels common to all four: ['Company', 'Ticker', 'Fiscal Year Closing', 'Current Price (Live Price)', 'Industry Sector', 'Industry Subgroup', 'Current Enterprise Value (not-diluted)', 'Current Market Capitalization', 'Expected Next Earnings Report Datetime', 'Latest Fiscal Quarter', 'Latest Annual Earnings Date']).
3. **Period axes** — `date` at row 15, `Fiscal Quarter` at row 16, `Fiscal Year` at row 146.
4. **Historical series block** — metric labels in column A with quarterly values across columns B… between Fiscal Quarter and Fiscal Year, plus a short post-Fiscal-Year series band (common labels: 128 pre-FY, 7 post-FY).
5. **Scalar key/value block** — column A labels + column B values after the series band (common scalar labels: 104).
6. **Numeric trailer** — long run of numeric column-A indices (ignore for product parsing); starts at row 265 on AAPL.

## 3. Summary sheet layout

- Row 1: field headers
- Row 2: values
- Header catalog is **byte-for-byte identical** across all four (111 fields).

### Required fields (populated on all four)

- `Company`
- `Ticker`
- `Current Price (Live Price)`
- `Industry Sector`
- `Industry Subgroup`
- `Current Status without PE10 Percentile`
- `Current Status with PE10 Percentile`
- `Current PE10 (PFFO10 for REITS) Percentile`
- `Expected Next Earnings Report Datetime`
- `Latest Fiscal Quarter`
- `Latest Annual Earnings Date`
- `Max Current Price to Buy`
- `1st Exit Price`
- `2nd Exit Price`
- `Latest Quarter Assets/ Liabilities`
- `Current 3 year EPS 10 years Av Growth`
- `Current 3 year EPS 10 years Av Growth Direction`
- `Current 3 year Revenue 10 years Av Growth`
- `Current TBV per Share`
- `Current TBV/Price`
- `Current Dividend Rate`
- `Current Dividend Yield`
- `Dividend Policy Satisfied`
- `Expected Return Price Plus Dividends - Given Current Price`
- `Expected Return Price Plus Dividends - Given Max Entry Price`
- `ROCE`
- `ROCE Fiscal Year`
- `ROCE 5 Fiscal Years`
- `ROCE 10 Fiscal Years`
- `Approximate Residual Earnings Value`
- `Extrapolated Price Plus Dividends`
- `Current Total Debt to (EBITDA 3 Year Average)`
- `Current Funds from Operations 10 Year Growth Direction`
- `EPS Latest Fiscal Year`
- `EPS Current Yield`
- `EPS Growth Direction Last Decade`
- `EPS Growth Last Decade`
- `Retained Earnings Average`
- `Book Value per Share Growth per Year`
- `ROE Average`
- `Latest Owners Earnings to Equity (Fiscal Year)`
- `Latest Owners Earnings per Share (Fiscal Year)`
- `Current E10`
- `Current PE10`
- `Current Max PE10 to Enter (Lowest PE10 or 7PE10)`
- `Expected Return @ Current Price`
- `% Shares to sell to recoup FV @ 1st Exit price`
- `High Price in 10 years`
- `Low Price in 10 years`
- `SNOA (Scaled Net Operating Assets)`
- `ROA10`
- `ROC10`
- `CFOA`
- `Number of Consecutive Positive Growth Margins`
- `Profit Margin Growth`
- `Profit Margin Stability`
- `P_FS`
- `Current Enterprise Value (not-diluted)`
- `Current Market Capitalization`
- `EBIT TTM`
- `EBIT 5 year average`
- `EBIT TTM/EV`
- `EBIT 5 year average/EV`
- `Debt/Total Assets`
- `ROC Greenblatt`
- `WACC`
- `ROC - WACC`
- `Current Book Value Per Share`
- `ROE`
- `Total Assets`
- `Six Month Price Change`
- `Gross Margin Fiscal Year`
- `Gross Margin TTM`
- `Operating Margin Fiscal Year`
- `Operating Margin 10 Fiscal Years`
- `Operating Margin TTM`
- `Cash Conversion Fiscal Year`
- `Cash Conversion TTM`
- `Interest Coverage Ratio Fiscal Year`
- `Current Graham Instrinsic Value`
- `Graham Instrinsic Value in 7 Years`
- `Graham Expected Annualized Return`
- `Six Month Price Change Rank`
- `EBIT TTM/EV Rank`
- `ROC - WACC Rank`
- `Final Score`
- `P_SNOA`
- `P_ROA10`
- `P_ROC10`
- `P_CFOA10`
- `P_MG`
- `P_MS`
- `Maximum Margin`
- `P_MM`
- `Franchise Power`
- `Quality_FPFS`

### Optional fields (present in header on all four, empty on at least one)

- `Current Debt to Gross Book Value Ratio`
- `Current Gross Book Value`
- `Dividends Since`
- `Current FFO10`
- `Current PFFO10`
- `Price/Book Value Per Share`
- `Non-Performing Assets`
- `Tier 1 Common Equity Ratio`
- `Tier 1 Capital Ratio`
- `Basel III Total Capital Ratio Fully Loaded`
- `Efficiency Ratio`
- `Net Interest Margin TTM`
- `Non-Performing Assets Growth QOQ`
- `Non-Performing Assets to Total Assets`
- `Interest Coverage Ratio TTM`

### Full common Summary header list (order from AAPL)

1. `Company`
2. `Ticker`
3. `Current Price (Live Price)`
4. `Industry Sector`
5. `Industry Subgroup`
6. `Current Status without PE10 Percentile`
7. `Current Status with PE10 Percentile`
8. `Current PE10 (PFFO10 for REITS) Percentile`
9. `Expected Next Earnings Report Datetime`
10. `Latest Fiscal Quarter`
11. `Latest Annual Earnings Date`
12. `Max Current Price to Buy`
13. `1st Exit Price`
14. `2nd Exit Price`
15. `Latest Quarter Assets/ Liabilities`
16. `Current 3 year EPS 10 years Av Growth`
17. `Current 3 year EPS 10 years Av Growth Direction`
18. `Current 3 year Revenue 10 years Av Growth`
19. `Current TBV per Share`
20. `Current TBV/Price`
21. `Current Dividend Rate`
22. `Current Dividend Yield`
23. `Dividend Policy Satisfied`
24. `Expected Return Price Plus Dividends - Given Current Price`
25. `Expected Return Price Plus Dividends - Given Max Entry Price`
26. `ROCE`
27. `ROCE Fiscal Year`
28. `ROCE 5 Fiscal Years`
29. `ROCE 10 Fiscal Years`
30. `Approximate Residual Earnings Value`
31. `Extrapolated Price Plus Dividends`
32. `Current Total Debt to (EBITDA 3 Year Average)`
33. `Current Funds from Operations 10 Year Growth Direction`
34. `Current Debt to Gross Book Value Ratio`
35. `Current Gross Book Value`
36. `EPS Latest Fiscal Year`
37. `EPS Current Yield`
38. `EPS Growth Direction Last Decade`
39. `EPS Growth Last Decade`
40. `Retained Earnings Average`
41. `Book Value per Share Growth per Year`
42. `ROE Average`
43. `Latest Owners Earnings to Equity (Fiscal Year)`
44. `Latest Owners Earnings per Share (Fiscal Year)`
45. `Dividends Since`
46. `Current E10`
47. `Current PE10`
48. `Current Max PE10 to Enter (Lowest PE10 or 7PE10)`
49. `Expected Return @ Current Price`
50. `% Shares to sell to recoup FV @ 1st Exit price`
51. `High Price in 10 years`
52. `Low Price in 10 years`
53. `SNOA (Scaled Net Operating Assets)`
54. `ROA10`
55. `ROC10`
56. `CFOA`
57. `Number of Consecutive Positive Growth Margins`
58. `Profit Margin Growth`
59. `Profit Margin Stability`
60. `P_FS`
61. `Current Enterprise Value (not-diluted)`
62. `Current Market Capitalization`
63. `EBIT TTM`
64. `EBIT 5 year average`
65. `EBIT TTM/EV`
66. `EBIT 5 year average/EV`
67. `Debt/Total Assets`
68. `ROC Greenblatt`
69. `WACC`
70. `ROC - WACC`
71. `Current FFO10`
72. `Current PFFO10`
73. `Current Book Value Per Share`
74. `Price/Book Value Per Share`
75. `Non-Performing Assets`
76. `Tier 1 Common Equity Ratio`
77. `Tier 1 Capital Ratio`
78. `Basel III Total Capital Ratio Fully Loaded`
79. `Efficiency Ratio`
80. `Net Interest Margin TTM`
81. `Non-Performing Assets Growth QOQ`
82. `Non-Performing Assets to Total Assets`
83. `ROE`
84. `Total Assets`
85. `Six Month Price Change`
86. `Gross Margin Fiscal Year`
87. `Gross Margin TTM`
88. `Operating Margin Fiscal Year`
89. `Operating Margin 10 Fiscal Years`
90. `Operating Margin TTM`
91. `Cash Conversion Fiscal Year`
92. `Cash Conversion TTM`
93. `Interest Coverage Ratio Fiscal Year`
94. `Interest Coverage Ratio TTM`
95. `Current Graham Instrinsic Value`
96. `Graham Instrinsic Value in 7 Years`
97. `Graham Expected Annualized Return`
98. `Six Month Price Change Rank`
99. `EBIT TTM/EV Rank`
100. `ROC - WACC Rank`
101. `Final Score`
102. `P_SNOA`
103. `P_ROA10`
104. `P_ROC10`
105. `P_CFOA10`
106. `P_MG`
107. `P_MS`
108. `Maximum Margin`
109. `P_MM`
110. `Franchise Power`
111. `Quality_FPFS`

## 4. Common historical series labels (pre–Fiscal Year)

- `Shares Outstanding Diluted Average (MM)`
- `Preferred Stock`
- `Total Assets`
- `Intangible Assets`
- `Total Liabilities`
- `Net Income`
- `Diluted Net Income`
- `Dividends per Share`
- `Total Current Assets`
- `Total Current Liabilities`
- `Interest Expense`
- `Depreciation, Depletion and Amortization`
- `Total Equity`
- `Revenue`
- `Earnings Announcement Date`
- `EBIT`
- `Income Taxes`
- `Net Fixed Assets`
- `Weighted Average Cost of Capital`
- `Enterprise Value (not-diluted)`
- `Cash and Cash Equivalents`
- `Short Term Debt`
- `Free Cash Flow`
- `Long Term Debt`
- `Minority Non-Controlling Interest`
- `Cost of Revenue`
- `Non-Performing Assets`
- `Tier 1 Common Equity Ratio`
- `Tier 1 Capital Ratio`
- `Basel III Total Capital Ratio Fully Loaded`
- `Efficiency Ratio`
- `Net Interest Margin TTM`
- `Capital Expenditures`
- `Retained Earnings`
- `Total Operating Lease Liabilities`
- `Total Operating Lease Assets`
- `Net Income GAAP (used for RAROE calc)`
- `Funds from Operations`
- `Accumulated Depreciation`
- `EBITDA`
- `Rental Income`
- `Property Operating Expense - As Reported`
- `Cash from Operations`
- `Closing Stock Price (Q. Average)`
- `Month Used for CPI`
- `CPI for fiscal month`
- `Earnings per Share (diluted)`
- `Market Value of Common`
- `Total Capitalization at Market`
- `Tangible Book Value per Share`
- `Tangible Book Value per Share/Price`
- `Net Margin`
- `Current Assets/ Total Liabilities`
- `Working Capital`
- `Working Capital/Debt`
- `ROE`
- `ROA`
- `Assets/Liabilities`
- `EBIT TTM`
- `Working Capital For ROC`
- `ROC Greenblatt`
- `ROC - WACC`
- `EPS TTM`
- `Dividend Rate (TTM)`
- `Gross Margin TTM`
- `Operating Margin TTM`
- `Interest Coverage Ratio TTM`
- `Cash Conversion TTM`
- `ROCE`
- `PE (TTM)`
- `Dividend Yield TTM`
- `EPS Fiscal Year`
- `Net Margin Fiscal Year`
- `Gross Margin Fiscal Year`
- `Gross Margin Growth YOY`
- `Operating Margin Fiscal Year`
- `Operating Margin 10 Fiscal Years`
- `Cash Conversion Fiscal Year`
- `Interest Coverage Ratio Fiscal Year`
- `Assets/Liabilities Fiscal Year`
- `ROA Fiscal Year`
- `ROE Fiscal Year`
- `Revenue Fiscal Year`
- `Net Income Fiscal Year`
- `EBIT Fiscal Year`
- `Free Cash Flow Fiscal Year`
- `WACC Fiscal Year`
- `ROC Greenblatt Fiscal Year`
- `Owners Earnings to Equity (Fiscal Year)`
- `Owners Earnings per Share (Fiscal Year)`
- `Average Shares Outstanding Diluted Average (MM) Fiscal Year`
- `EPS Year 10 Extrapolation`
- `Sum of 10 Years of Extrapolated Dividends`
- `BV per Share Year 10`
- `RAROE (Risk Adjusted Return on Equity`
- `Ten Year Dividend Payout Ratio Average`
- `EBITDA 3 Fiscal Year Average`
- `EBITDA Fiscal Year`
- `Total Debt Fiscal Year`
- `ROCE Fiscal Year`
- `ROCE 5 Fiscal Years`
- `ROCE 10 Fiscal Years`
- `3 years Av EPS Growth (10 Years) TTM`
- `3 years Av EPS Growth (10 Years) TTM Direction`
- `3 years Av Revenue Growth (10 Years) TTM`
- `Funds from Operations 10 Year Growth`
- `Funds from Operations 10 Year Growth Direction`
- `Funds from Operations per Share`
- `Gross Book Value`
- `Debt to Gross Book Value Ratio`
- `Total Debt to EBITDA 3 Year Ratio`
- `Book Value Per Share`
- `Non-Performing Assets Growth QOQ`
- `Non-Performing Assets to Total Assets`
- `E10`
- `PE10`
- `Min PE10`
- `Max PE10`
- `Min 7PE10`
- `Max 7PE10`
- `PE10 20th Percentile (Interpolation)`
- `7PE10 20th Percentile (Interpolation)`
- `PE10 Quantile Satisfied (Interpolation)`
- `7PE10 Quantile Satisfied (Interpolation)`
- `PE10 45th Percentile (Interpolation)`
- `7PE10 45th Percentile (Interpolation)`
- `Lowest of 45th Percentile PE10 or 7PE10`
- `Lowest of 20th Percentile PE10 or 7PE10`

## 5. Common post–Fiscal Year series labels

- `Number of years with dividends in past 10 years`
- `Dividend Policy Satisfied`
- `Fiscal Quarter for Earnings`
- `Min PE10 from Daily PE10s`
- `Max PE10 from Daily PE10s`
- `Min 7PE10 from Daily PE10s`
- `Max 7PE10 from Daily PE10s`

## 6. Common scalar labels

- `Current E10`
- `Current PE10`
- `Latest Quarter Assets/ Liabilities`
- `Dividends Since`
- `Current Max PE10 to Enter (Lowest PE10 or 7PE10)`
- `Max Current Price to Buy`
- `1st Exit Price`
- `2nd Exit Price`
- `Expected Return @ Current Price`
- `% Shares to sell to recoup FV @ 1st Exit price`
- `High Price in 10 years`
- `Low Price in 10 years`
- `Price change in 10 years`
- `High Price in 52 weeks`
- `Low Price in 52 weeks`
- `Price change in 52 weeks`
- `SNOA (Scaled Net Operating Assets)`
- `ROA10`
- `ROC10`
- `CFOA`
- `Number of Consecutive Positive Growth Margins`
- `Profit Margin Growth`
- `Profit Margin Stability`
- `FS_ROA`
- `FS_FCFTA`
- `FS_ACCRUAL`
- `FS_LEVER`
- `FS_LIQUID`
- `FS_NEQISS`
- `FS_DELTA_ROA`
- `FS_DELTA_FCFTA`
- `FS_DELTA_MARGIN`
- `FS_DELTA_TURN`
- `P_FS`
- `Current 3 year EPS 10 years Av Growth`
- `Current 3 year EPS 10 years Av Growth Direction`
- `Current 3 year Revenue 10 years Av Growth`
- `Current TBV/Price`
- `Dividend Policy Satisfied`
- `Expected Return Price Plus Dividends - Given Current Price`
- `Expected Return Price Plus Dividends - Given Max Entry Price`
- `ROCE`
- `ROCE Fiscal Year`
- `ROCE 5 Fiscal Years`
- `ROCE 10 Fiscal Years`
- `Approximate Residual Earnings Value`
- `Extrapolated Price Plus Dividends`
- `EPS Latest Fiscal Year`
- `EPS Current Yield`
- `EPS Growth Last Decade`
- `EPS Growth Direction Last Decade`
- `Retained Earnings Average`
- `Book Value per Share Growth per Year`
- `ROE Average`
- `Current Dividend Yield (TTM)`
- `Current Dividend Yield`
- `Current PE10 (PFFO10 for REITS) Percentile`
- `Current Enterprise Value (not-diluted)`
- `Current Market Capitalization`
- `EBIT TTM`
- `EBIT 5 year average`
- `EBIT TTM/EV`
- `EBIT 5 year average/EV`
- `Debt/Total Assets`
- `ROC Greenblatt`
- `WACC`
- `ROC - WACC`
- `Current Status without PE10 Percentile`
- `Current Status with PE10 Percentile`
- `Current FFO10`
- `Current PFFO10`
- `Current Book Value Per Share`
- `Price/Book Value Per Share`
- `Non-Performing Assets`
- `Tier 1 Common Equity Ratio`
- `Tier 1 Capital Ratio`
- `Basel III Total Capital Ratio Fully Loaded`
- `Efficiency Ratio`
- `Net Interest Margin TTM`
- `Non-Performing Assets Growth QOQ`
- `Non-Performing Assets to Total Assets`
- `ROE`
- `Total Assets`
- `Latest Owners Earnings to Equity (Fiscal Year)`
- `Latest Owners Earnings per Share (Fiscal Year)`
- `Six Month Price Change`
- `Current Funds from Operations 10 Year Growth Direction`
- `Current Debt to Gross Book Value Ratio`
- `Current Gross Book Value`
- `Current Total Debt to (EBITDA 3 Year Average)`
- `Fair Stock Price (REITS)`
- `NOI (Net Operating Income) reported for Q (REITS)`
- `Gross Margin TTM`
- `Gross Margin Fiscal Year`
- `Operating Margin TTM`
- `Operating Margin Fiscal Year`
- `Operating Margin 10 Fiscal Years`
- `Cash Conversion TTM`
- `Cash Conversion Fiscal Year`
- `Interest Coverage Ratio TTM`
- `Interest Coverage Ratio Fiscal Year`
- `Current Graham Instrinsic Value`
- `Graham Instrinsic Value in 7 Years`
- `Graham Expected Annualized Return`

## 7. Company-specific differences

### AAPL

- Ticker sheet name: `AAPL`
- Period width: `102`
- Scalar start row: `158`
- Trailer start row: `265`
- summary_only_here: _(none)_
- meta_only_here: _(none)_
- series_only_here: _(none)_
- post_fy_only_here: _(none)_
- scalars_only_here: _(none)_

### MSFT

- Ticker sheet name: `MSFT`
- Period width: `102`
- Scalar start row: `158`
- Trailer start row: `265`
- summary_only_here: _(none)_
- meta_only_here: _(none)_
- series_only_here: _(none)_
- post_fy_only_here: _(none)_
- scalars_only_here: _(none)_

### AMZN

- Ticker sheet name: `AMZN`
- Period width: `102`
- Scalar start row: `158`
- Trailer start row: `265`
- summary_only_here: _(none)_
- meta_only_here: _(none)_
- series_only_here: _(none)_
- post_fy_only_here: _(none)_
- scalars_only_here: _(none)_

### TJX

- Ticker sheet name: `TJX`
- Period width: `102`
- Scalar start row: `158`
- Trailer start row: `265`
- summary_only_here: _(none)_
- meta_only_here: _(none)_
- series_only_here: _(none)_
- post_fy_only_here: _(none)_
- scalars_only_here: _(none)_

## 8. Industrial Template worksheets (companion input)

- **AAPL** `AAPL 2026 Q2 - Industrial Template v27.6.xlsx` sheets: `['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios', 'Final Metrics', 'Expected Returns & Buybacks', 'Enterprise Value', 'Template Version']`
- **MSFT** `MSFT 2026 Q3 - Industrial Template v27.6.xlsx` sheets: `['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios', 'Final Metrics', 'Expected Returns & Buybacks', 'Enterprise Value', 'Template Version']`
- **AMZN** `AMZN 2026 Q1 - Industrial Template v27.6.xlsx` sheets: `['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios', 'Final Metrics', 'Expected Returns & Buybacks', 'Enterprise Value', 'Template Version']`
- **TJX** `TJX 2026 Q4 - Industrial Template v27.6.xlsx` sheets: `['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios', 'Final Metrics', 'Expected Returns & Buybacks', 'Enterprise Value', 'Template Version']`

## 9. Parser contract implied by evidence

A production-faithful parser must:

1. Require worksheets `[TICKER, Summary]` as observed.
2. Use observed anchors: date=15, Fiscal Quarter=16, Fiscal Year=146 (identical on all four).
3. Parse meta as A/B pairs above the `date` row.
4. Parse period axes from `date`, `Fiscal Quarter`, and `Fiscal Year` rows.
5. Parse historical series from labeled rows between Fiscal Quarter and the scalar region (including the short post–Fiscal Year band), skipping axis header rows.
6. Parse scalars as A/B pairs until the numeric trailer.
7. Parse Summary as header row + value row; preserve Bloomberg spellings exactly (including observed typo `Graham Instrinsic Value`).
8. Ignore the numeric trailer matrix.
