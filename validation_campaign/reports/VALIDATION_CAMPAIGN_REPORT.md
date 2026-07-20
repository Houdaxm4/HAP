# Validation Campaign Report — Sprint 5.3

## Execution status

- Universe size: **91**
- Harness result rows: **0**
- Ready input packages: **0**

> **Harness produced no company result rows.**
> Analytical anomaly rankings (failed modules, low confidence, contradictions)
> require successful pipeline runs. See Input Readiness Report.

## Ranking criteria (objective)

When harness outputs exist, companies are ranked using:

1. Pipeline / analysis failure
2. Failed modules
3. Incomplete module coverage
4. Missing financial series / empty analytical fields
5. Low confidence
6. Contradictory outputs / recommendation anomalies

Additional campaign triage factors (not HAP scores):

- Methodology-sensitive sectors (Financials, REITs, Utilities, Energy, Telecom)
- Extreme sampling tiers (Exceptional / Weak / Distressed)

## Ranked companies

| Rank | Priority | Ticker | Sector | Tier | Harness | Reasons |
|-----:|---------:|--------|--------|------|---------|---------|
| 1 | 113 | APA | Energy | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy; extreme_sampling_tier:Weak |
| 2 | 113 | KEY | Financials | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials; extreme_sampling_tier:Weak |
| 3 | 113 | NYCB | Financials | Distressed | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials; extreme_sampling_tier:Distressed |
| 4 | 113 | PCG | Utilities | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities; extreme_sampling_tier:Weak |
| 5 | 108 | AEP | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 6 | 108 | AMT | REITs | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 7 | 108 | ARE | REITs | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 8 | 108 | BAC | Financials | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 9 | 108 | BLK | Financials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 10 | 108 | C | Financials | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 11 | 108 | CHTR | Telecommunications | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 12 | 108 | CMCSA | Telecommunications | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 13 | 108 | COP | Energy | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 14 | 108 | CVX | Energy | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 15 | 108 | D | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 16 | 108 | DUK | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 17 | 108 | DVN | Energy | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 18 | 108 | EQIX | REITs | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 19 | 108 | EXC | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 20 | 108 | GS | Financials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 21 | 108 | HAL | Energy | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 22 | 108 | JPM | Financials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 23 | 108 | MS | Financials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 24 | 108 | NEE | Utilities | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 25 | 108 | O | REITs | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 26 | 108 | OXY | Energy | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 27 | 108 | PLD | REITs | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 28 | 108 | SCHW | Financials | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 29 | 108 | SLB | Energy | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 30 | 108 | SO | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 31 | 108 | SPG | REITs | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 32 | 108 | SRE | Utilities | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Utilities |
| 33 | 108 | T | Telecommunications | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 34 | 108 | TMUS | Telecommunications | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 35 | 108 | TU | Telecommunications | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 36 | 108 | VICI | REITs | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 37 | 108 | VZ | Telecommunications | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Telecommunications |
| 38 | 108 | WELL | REITs | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:REITs |
| 39 | 108 | WFC | Financials | Average | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Financials |
| 40 | 108 | XOM | Energy | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter; methodology_sensitive_sector:Energy |
| 41 | 105 | AAPL | Technology | Exceptional | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Exceptional |
| 42 | 105 | AMC | Consumer Discretionary | Distressed | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Distressed |
| 43 | 105 | BA | Industrials | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 44 | 105 | COST | Consumer Staples | Exceptional | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Exceptional |
| 45 | 105 | CVS | Healthcare | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 46 | 105 | INTC | Technology | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 47 | 105 | LLY | Healthcare | Exceptional | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Exceptional |
| 48 | 105 | MRNA | Healthcare | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 49 | 105 | MSFT | Technology | Exceptional | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Exceptional |
| 50 | 105 | SNAP | Technology | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 51 | 105 | WBA | Consumer Staples | Weak | not_run | incomplete_inputs:workbook;custom_run_filter; extreme_sampling_tier:Weak |
| 52 | 100 | ABBV | Healthcare | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 53 | 100 | ADBE | Technology | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 54 | 100 | AMZN | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 55 | 100 | BMY | Healthcare | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 56 | 100 | CAT | Industrials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 57 | 100 | CL | Consumer Staples | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 58 | 100 | CMG | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 59 | 100 | CRM | Technology | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 60 | 100 | DE | Industrials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 61 | 100 | FDX | Industrials | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 62 | 100 | GE | Industrials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 63 | 100 | GIS | Consumer Staples | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 64 | 100 | GOOGL | Technology | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 65 | 100 | HD | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 66 | 100 | HON | Industrials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 67 | 100 | IBM | Technology | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 68 | 100 | ISRG | Healthcare | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 69 | 100 | JNJ | Healthcare | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 70 | 100 | KHC | Consumer Staples | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 71 | 100 | KO | Consumer Staples | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 72 | 100 | LOW | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 73 | 100 | MCD | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 74 | 100 | MDLZ | Consumer Staples | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 75 | 100 | META | Technology | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 76 | 100 | MMM | Industrials | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 77 | 100 | MRK | Healthcare | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 78 | 100 | NKE | Consumer Discretionary | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 79 | 100 | NVDA | Technology | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 80 | 100 | ORCL | Technology | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 81 | 100 | PEP | Consumer Staples | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 82 | 100 | PFE | Healthcare | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 83 | 100 | PG | Consumer Staples | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 84 | 100 | RTX | Industrials | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 85 | 100 | SBUX | Consumer Discretionary | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 86 | 100 | TJX | Consumer Discretionary | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 87 | 100 | TSLA | Consumer Discretionary | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 88 | 100 | UNH | Healthcare | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 89 | 100 | UNP | Industrials | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
| 90 | 100 | UPS | Industrials | Average | not_run | incomplete_inputs:workbook;custom_run_filter |
| 91 | 100 | WMT | Consumer Staples | Excellent | not_run | incomplete_inputs:workbook;custom_run_filter |
