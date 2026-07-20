# HAP Enterprise Valuation Module Specification

Version: 1.0  
Status: **Specification only** (not implemented)  
Module ID: `valuation`  
Display name: **Enterprise Valuation**  
Parent specs: `docs/FINANCIAL_ANALYSIS_SPEC.md`, `docs/SCORING_SYSTEM.md`, `docs/RULE_LIBRARY.md`, `docs/INVESTMENT_NETHODOLOGY.md`, `docs/HAP_ANALYST_PLAYBOOK.md`, `docs/PROJECT.md`

---

## 0. Compliance Constraints

This specification must not introduce new architectural layers or change existing contracts unless explicitly approved in `FINANCIAL_ANALYSIS_SPEC.md`.

| Constraint | Requirement |
|---|---|
| Input contract | Module consumes **only** `CompanyFinancialModel` |
| Output contract | Module returns standard `AnalysisModuleResult` |
| Forbidden access | No Excel, workbook cells, SEC APIs, Yahoo Finance, or raw JSON parsing |
| Scoring philosophy | Deterministic valuation math + deterministic rules; **no LLM judgment** |
| Role of LLM | Explains results later; never invents valuation conclusions |
| Quality vs attractiveness | Enterprise Valuation estimates **economic worth** and **workbook reasonableness**. It does **not** issue Buy / Sell / Hold recommendations |
| Workbook immutability | HAP computes its own valuation; compares to workbook; **never overwrites** workbook formulas or values |
| Golden rules | Never invent financial data; preserve provenance; human judgment overrides via documented analyst adjustments |

### Relationship to other modules

| Module | Relationship |
|---|---|
| Business Quality modules | Provide historical fundamentals used as valuation **inputs** (margins, FCF, ROIC, leverage). Valuation does **not** recompute BQ scores |
| Business Outlook | Forward assumptions (growth, margins, risks) may inform forecast overlays via `metadata.valuation` |
| Expected Return | Consumes valuation outputs (fair value, MOS) for forward return math — **out of scope here** |
| Recommendation | Combines Business Quality + Investment Attractiveness — **out of scope here** |

---

## 1. Purpose

### Business question

**What is this business worth on an enterprise and per-share basis, and is the analyst workbook’s valuation economically reasonable given reported facts and stated assumptions?**

Enterprise Valuation answers **Stage 3 — Enterprise Valuation** from `INVESTMENT_NETHODOLOGY.md`:

- What is the estimated **Enterprise Value** and **Equity Value**?
- What is **Intrinsic Value per Share** and a defensible **Fair Value Range**?
- What **Margin of Safety** (or premium) exists versus observable market price?
- Are workbook valuation outputs **consistent** with HAP’s independently computed valuation?
- Are key assumptions (**WACC**, **terminal growth**, **forecast margins**, **reinvestment**) within reasonable bounds?

### What this module does **not** answer

- Whether to buy, sell, or hold the stock (Recommendation Module).
- Expected IRR / CAGR versus the S&P 500 (Expected Return Module).
- Whether the company is a high-quality business (Business Quality Aggregator).
- Narrative report writing (Report Generator).

### Single responsibility

One concern only: **independent enterprise and equity valuation synthesis, assumption discipline, and workbook valuation comparison**.

---

## 2. Inputs

The module reads historical `FinancialSeries`, `MarketData`, `ValuationInputs`, `WorkbookMetricCatalog`, and analyst overlays in `metadata` only.

### 2.1 Required context fields

| Field | Type | Requirement |
|---|---|---|
| `analysis_id` | `str` | Required |
| `ticker` | `str` | Required |
| `company` | `str \| None` | Optional |
| `reporting_currency` | `str` | Required (default USD) |
| `periods` | `list[str]` | Preferred (union of statement periods) |
| `market_data.as_of_date` | `str \| None` | Required for market-relative outputs when price-based metrics are computed |
| `metadata` | `dict` | Optional overlays listed in §2.4 |

### 2.2 Required `CompanyFinancialModel` fields for module `ok` status

At minimum, the module requires enough data to compute **at least one** primary valuation method and a market anchor:

| Path | Role | Requirement |
|---|---|---|
| `cash_flow_statement.free_cash_flow` **or** derived FCF from OCF − CapEx | DCF / Owner Earnings base | **Required** for cash-based methods |
| `cash_flow_statement.operating_cash_flow` | Owner Earnings fallback | Required if FCF missing |
| `income_statement.revenue` | Multiple denominators, forecast scaling | **Required** |
| `income_statement.ebit` or `operating_income` | EBIT/EBITDA multiples, NOPAT proxy | Preferred |
| `income_statement.ebitda` | EV/EBITDA multiples | Preferred |
| `income_statement.net_income` | P/E cross-check | Preferred |
| `income_statement.tax_expense` | NOPAT / tax rate derivation | Preferred |
| `balance_sheet.total_debt` | Enterprise ↔ equity bridge | Preferred |
| `balance_sheet.cash` | Net debt | Preferred |
| `balance_sheet.shareholders_equity` | Book-based sanity checks | Optional |
| `market_data.share_price` | Premium/discount, MOS vs market | **Required** for market-relative valuation score components |
| `market_data.shares_outstanding` | Per-share values | **Required** for per-share outputs |
| `valuation_inputs.wacc` | DCF discount rate | **Required** for DCF; if missing, module may run multiples-only with confidence penalty |
| `valuation_inputs.terminal_growth_rate` | DCF terminal value | Required for DCF terminal stage |
| `valuation_inputs.tax_rate` | NOPAT, WACC tax shield | Preferred (derive from statements if absent) |
| `valuation_inputs.forecast_years` | Explicit forecast horizon | Preferred (default **5** documented in coverage) |
| `valuation_inputs.net_debt` | Equity bridge override | Optional (derive from debt − cash if absent) |

If `share_price` or `shares_outstanding` is missing, the module may still emit enterprise-level values but **cannot** compute Margin of Safety vs market; status may be `ok` with reduced coverage or `skipped` if no valuation anchor exists.

### 2.3 `ValuationInputs` fields (assumption registry)

All fields on `ValuationInputs` are treated as **explicit analyst assumptions** with provenance:

| Field | Use |
|---|---|
| `risk_free_rate` | CAPM / WACC build-up |
| `equity_risk_premium` | CAPM |
| `cost_of_equity` | WACC, residual income (future) |
| `cost_of_debt` | WACC |
| `tax_rate` | NOPAT, after-tax WACC |
| `wacc` | DCF discount rate |
| `terminal_growth_rate` | Gordon terminal value |
| `forecast_years` | Explicit forecast period count |
| `net_debt` | EV → equity bridge |
| `minority_interest` | Equity bridge |
| `preferred_equity` | Equity bridge |
| `extras` | Extension slot for documented custom assumptions (e.g. `fade_rate`) |

### 2.4 Optional `metadata` overlays

Namespace: `metadata["valuation"]` (flat keys accepted as fallback).

#### Forecast & operating assumptions

| Key | Type | Purpose |
|---|---|---|
| `forecast_revenue_growth` | `list[float]` or `dict[period, float]` | Explicit revenue growth by forecast year |
| `forecast_operating_margin` | `list[float]` or `dict` | Operating margin path |
| `forecast_fcf_margin` | `list[float]` or `dict` | FCF margin path |
| `forecast_capex_to_revenue` | `list[float]` | Reinvestment intensity |
| `forecast_working_capital_change` | `list[float]` | WC investment per year |
| `fade_years` | `int` | Years to fade abnormal growth to terminal |
| `maintenance_capex` | `float` or series | Owner Earnings maintenance capex |
| `owner_earnings_adjustments` | `dict` | One-time adjustments to owner earnings |

#### Market & peer context

| Key | Type | Purpose |
|---|---|---|
| `peer_ev_to_ebitda` | `float` or `{p25, median, p75}` | Peer multiple range |
| `peer_ev_to_revenue` | `float` or range | Peer range |
| `peer_pe` | `float` or range | Peer range |
| `peer_group` | `list[str]` | Tickers used (evidence only) |
| `historical_ev_to_ebitda` | `dict[period, float]` | Company’s own history |
| `historical_pe` | `dict[period, float]` | Company’s own history |
| `gdp_nominal_growth` | `float` | Terminal growth sanity bound (default 0.04 if absent, flagged) |
| `risk_free_rate_source` | `str` | Assumption provenance |

#### Scenario definitions

| Key | Type | Purpose |
|---|---|---|
| `scenarios` | `dict` | Bull / Base / Bear assumption bundles (see §6) |
| `scenario_weights` | `dict` | Optional probability weights for fair value range |

#### Assumption provenance (required when overlays used)

| Key | Type | Purpose |
|---|---|---|
| `assumption_evidence` | `dict[field → {source, source_document, confidence}]` | Per-assumption provenance |
| `workbook_valuation_cells` | `dict` | Optional mapping of workbook cell refs for comparison audit |

#### Cross-module context (read-only, not recomputed)

| Key | Type | Purpose |
|---|---|---|
| `business_quality_score` | `float` | Interpretive context only — **not** a valuation input weight |
| `latest_roic` | `float` | Reinvestment / terminal return sanity |
| `cyclicality_flag` | `bool` | Normalize through-cycle earnings for multiples |

### 2.5 Workbook metrics consumed (read-only)

From `CompanyFinancialModel.workbook_metrics` when present:

| Workbook code | Comparison target |
|---|---|
| `ENTERPRISE_VALUE` | HAP Enterprise Value |
| `EQUITY_VALUE` | HAP Equity Value |
| `INTRINSIC_VALUE` | HAP Intrinsic Value per Share |
| `FAIR_VALUE` | HAP Fair Value (base case) |
| `MARGIN_OF_SAFETY` | HAP Margin of Safety |
| `EV_TO_EBITDA` | HAP implied / observed multiple |
| `PE_RATIO` | HAP implied / observed multiple |
| `OWNER_EARNINGS` | HAP Owner Earnings run-rate |
| `WACC` | HAP / stated WACC assumption |
| `TERMINAL_GROWTH` | HAP terminal growth assumption |

Workbook metrics **never** feed valuation formulas directly. They are compared post-computation.

### 2.6 Provenance requirements

Every HAP valuation metric, assumption record, and finding must include:

- value, period, currency/unit  
- source (`hap_derived`, `valuation_inputs`, `metadata.valuation`, `market_data`)  
- confidence  
- provenance (`cell_ref`, `source_document`, assumption key)

Missing inputs reduce coverage and confidence; they do **not** justify silent invention of forecast paths.

---

## 3. Valuation Methodologies

HAP computes **independent** valuations per method, then synthesizes a **Fair Value Range** and **Base Case Fair Value**. Methods disagreeing materially reduce confidence (§9).

### 3.1 Discounted Cash Flow (DCF)

| Item | Specification |
|---|---|
| **Purpose** | Intrinsic enterprise value from explicit forecast FCF and terminal value |
| **Required inputs** | Latest FCF or OCF + CapEx; `valuation_inputs.wacc`; `valuation_inputs.terminal_growth_rate`; `forecast_years`; forecast path or deterministic default path from historical FCF CAGR with fade |
| **Assumptions** | Forecast revenue growth, margins, reinvestment, tax rate, WACC, terminal growth, net debt bridge |
| **Outputs** | `DCF_ENTERPRISE_VALUE`, `DCF_EQUITY_VALUE`, `DCF_VALUE_PER_SHARE`, `DCF_TERMINAL_VALUE_SHARE`, `DCF_PV_FORECAST_SHARE` |
| **Limitations** | Highly sensitive to terminal value and WACC; weak for negative FCF runways without explicit turnaround forecast |
| **Confidence** | High when ≥5-year audited FCF history, explicit forecast overlays, WACC sourced, terminal growth ≤ GDP bound |

**Method sketch (deterministic):**

1. Build explicit forecast FCF series for `N = forecast_years` (default 5).  
2. Discount each year: `PV_t = FCF_t / (1 + WACC)^t`.  
3. Terminal value: `TV = FCF_N × (1 + g) / (WACC − g)`; discount to present.  
4. Enterprise Value = sum of PVs.  
5. Equity Value = EV − net debt − minority interest − preferred equity.  
6. Per share = Equity Value / diluted shares.

### 3.2 Owner Earnings Valuation

| Item | Specification |
|---|---|
| **Purpose** | Buffett-style intrinsic value from sustainable cash earnings |
| **Required inputs** | `operating_cash_flow`; maintenance capex (metadata overlay or total CapEx proxy); `wacc` or earnings capitalization rate |
| **Assumptions** | Maintenance vs growth capex split; owner earnings growth fade; capitalization rate = WACC unless metadata specifies `owner_earnings_cap_rate` |
| **Outputs** | `OWNER_EARNINGS_RUN_RATE`, `OE_ENTERPRISE_VALUE`, `OE_EQUITY_VALUE`, `OE_VALUE_PER_SHARE` |
| **Limitations** | Maintenance capex ambiguity; less suited to financials and early-stage loss-makers |
| **Confidence** | High when maintenance capex overlay provided; medium when using total CapEx proxy |

**Method sketch:**

`Owner Earnings = OCF − Maintenance CapEx`  
Capitalize: `EV ≈ Owner Earnings × (1 + g_oe) / (WACC − g_oe)` with conservative `g_oe` (default min(historical FCF CAGR, terminal growth)).

### 3.3 Enterprise Value Multiples

| Item | Specification |
|---|---|
| **Purpose** | Cross-sectional worth vs peers using operating metrics |
| **Required inputs** | LTM or normalized EBITDA, revenue, EBIT; peer multiples from `metadata.valuation.peer_*` |
| **Assumptions** | Normalized through-cycle earnings if `cyclicality_flag`; peer median as base, p25/p75 as range |
| **Outputs** | `MULTIPLE_EV_EBITDA`, `MULTIPLE_EV_REVENUE`, `MULTIPLE_EQUITY_VALUE_MID`, `MULTIPLE_VALUE_PER_SHARE` |
| **Limitations** | Peer selection bias; multiples ignore balance sheet risk and growth differences |
| **Confidence** | High when ≥3 peers with documented source; low when peer data absent (method skipped) |

### 3.4 Historical Multiples

| Item | Specification |
|---|---|
| **Purpose** | Worth vs company’s own trading/transaction history |
| **Required inputs** | Historical EV/EBITDA or P/E series (`metadata` or derived from market snapshots); current LTM denominators |
| **Assumptions** | Use median historical multiple over 5–10 years; exclude crisis spikes via winsorization |
| **Outputs** | `HIST_EV_EBITDA_IMPUTED_EV`, `HIST_PE_IMPUTED_EQUITY`, `HIST_VALUE_PER_SHARE` |
| **Limitations** | Past multiples may not reflect structural regime change |
| **Confidence** | Medium; requires sufficient history |

### 3.5 Reverse DCF

| Item | Specification |
|---|---|
| **Purpose** | Implied market expectations — what growth/WACC the **current price** requires |
| **Required inputs** | `market_data.share_price`; shares; net debt; base FCF; `wacc` (held constant) or terminal growth (held constant) |
| **Assumptions** | Solve for implied terminal growth or implied 5-year FCF CAGR that reconciles DCF to current EV |
| **Outputs** | `REVERSE_DCF_IMPLIED_GROWTH`, `REVERSE_DCF_IMPLIED_FCF_CAGR`, `REVERSE_DCF_PLAUSIBILITY_SCORE` |
| **Limitations** | Not a fair value — a **reasonableness check** on market pricing |
| **Confidence** | Medium; highly sensitive to WACC held constant |

### 3.6 Residual Income (future)

| Item | Specification |
|---|---|
| **Status** | **Not in v1 implementation** — documented for roadmap |
| **Purpose** | Equity value from excess returns over cost of equity |
| **Required inputs** | Book value; forecast NOPAT; cost of equity; terminal ROE fade |
| **Outputs** | `RI_EQUITY_VALUE`, `RI_VALUE_PER_SHARE` |
| **Limitations** | Book value quality; bank/insurance specialization needed |

### 3.7 Synthesis outputs (all methods)

| Output code | Description |
|---|---|
| `HAP_ENTERPRISE_VALUE` | Base-case synthesized EV |
| `HAP_EQUITY_VALUE` | Base-case equity value |
| `HAP_INTRINSIC_VALUE_PER_SHARE` | Base-case per share |
| `FAIR_VALUE_LOW` | Bear / conservative synthesis |
| `FAIR_VALUE_BASE` | Probability-weighted or median of available methods |
| `FAIR_VALUE_HIGH` | Bull synthesis |
| `MARGIN_OF_SAFETY` | `(FAIR_VALUE_BASE − PRICE) / FAIR_VALUE_BASE` |
| `PREMIUM_DISCOUNT` | `(PRICE − FAIR_VALUE_BASE) / FAIR_VALUE_BASE` |
| `METHOD_SPREAD` | `(max_method − min_method) / FAIR_VALUE_BASE` |
| `VALUATION_CONFIDENCE` | Module confidence snapshot |

**Base-case synthesis rule (deterministic):**

1. Collect per-method `VALUE_PER_SHARE` where confidence ≥ method threshold.  
2. If ≥3 methods: `FAIR_VALUE_BASE` = weighted median (weights: DCF 35%, Owner Earnings 25%, Multiples 25%, Historical 15%).  
3. If 2 methods: equal-weighted average.  
4. If 1 method: that method; confidence penalized.  
5. `FAIR_VALUE_LOW` / `HIGH` from Bear/Bull scenarios (§6), not raw min/max of unrelated methods.

---

## 4. Workbook Comparison

HAP **always** computes its own valuation first. Workbook values are read from `workbook_metrics` only.

### 4.1 Comparable workbook codes

| Metric code | HAP equivalent |
|---|---|
| `ENTERPRISE_VALUE` | `HAP_ENTERPRISE_VALUE` |
| `EQUITY_VALUE` | `HAP_EQUITY_VALUE` |
| `INTRINSIC_VALUE` | `HAP_INTRINSIC_VALUE_PER_SHARE` |
| `FAIR_VALUE` | `FAIR_VALUE_BASE` |
| `MARGIN_OF_SAFETY` | `MARGIN_OF_SAFETY` |
| `WACC` | `WACC_ASSUMPTION` |
| `TERMINAL_GROWTH` | `TERMINAL_GROWTH_ASSUMPTION` |

### 4.2 Comparison record (per `FINANCIAL_ANALYSIS_SPEC.md`)

Each comparison is stored under `coverage["metric_comparisons"]` using the existing `MetricComparison` contract:

| Field | Rule |
|---|---|
| **Workbook Value** | From `workbook_metrics` — never modified |
| **HAP Value** | Independently computed |
| **Difference** | `HAP − Workbook` |
| **Tolerance** | See §4.3 |
| **Status** | `match`, `within_tolerance`, `divergent`, `workbook_only`, `hap_only`, `not_comparable` |
| **Recommended Analyst Action** | Deterministic mapping from status + metric type |

### 4.3 Default tolerances

| Metric type | Tolerance mode | Default tolerance |
|---|---|---|
| Enterprise / Equity Value (absolute) | relative | **5%** |
| Intrinsic / Fair Value per share | relative | **5%** |
| Margin of Safety | absolute | **3 percentage points** |
| WACC | absolute | **75 bps** |
| Terminal growth | absolute | **50 bps** |
| Multiples | relative | **8%** |

Large divergences trigger rules VA031–VA035 (§7).

### 4.4 Recommended actions

| Status | Typical action |
|---|---|
| `match` | `no_action` |
| `within_tolerance` | `no_action` |
| `divergent` (valuation level) | `reconcile_inputs` or `request_analyst_review` |
| `divergent` (WACC / terminal growth) | `investigate_workbook_formula` |
| `workbook_only` | `request_analyst_review` (HAP could not reproduce) |
| `hap_only` | `no_action` (workbook missing — informational) |

---

## 5. Valuation Assumptions

Every assumption used in valuation must be emitted as a structured **assumption record** in `coverage["assumptions"]` and referenced in metric `evidence`.

### 5.1 Assumption record schema

```json
{
  "code": "WACC",
  "value": 0.09,
  "unit": "ratio",
  "source": "valuation_inputs",
  "source_document": "Analyst WACC worksheet",
  "confidence": 0.85,
  "provenance": {
    "field": "valuation_inputs.wacc",
    "cell_ref": "WACC!B12"
  }
}
```

### 5.2 Documented assumptions

| Assumption code | Description | Primary source | Default if missing |
|---|---|---|---|
| `WACC` | Discount rate for DCF / capitalization | `valuation_inputs.wacc` | None — DCF skipped |
| `TERMINAL_GROWTH` | Perpetuity growth | `valuation_inputs.terminal_growth_rate` | None — DCF terminal skipped |
| `FORECAST_YEARS` | Explicit forecast horizon | `valuation_inputs.forecast_years` | 5 (documented, confidence −0.05) |
| `FORECAST_REVENUE_GROWTH` | Year-by-year revenue growth | `metadata.valuation.forecast_revenue_growth` | Derived from historical revenue CAGR with fade |
| `FORECAST_FCF_MARGIN` | FCF margin path | metadata or historical average | Historical 5Y average |
| `REINVESTMENT_RATE` | CapEx + ΔWC as % NOPAT | Derived or metadata | Derived from statements |
| `OPERATING_MARGIN` | Forecast EBIT margin | metadata or historical | Latest or 5Y mean |
| `TAX_RATE` | Cash tax rate | `valuation_inputs.tax_rate` or derived | Derived from tax/EBIT |
| `NET_DEBT` | EV → equity bridge | `valuation_inputs.net_debt` or debt − cash | Derived |
| `COST_OF_EQUITY` | CAPM / RI (future) | `valuation_inputs.cost_of_equity` | Optional WACC build-up |
| `COST_OF_DEBT` | WACC build-up | `valuation_inputs.cost_of_debt` | Optional |
| `RISK_FREE_RATE` | CAPM | `valuation_inputs.risk_free_rate` | Optional |
| `ERP` | Equity risk premium | `valuation_inputs.equity_risk_premium` | Optional |
| `PEER_MEDIAN_EV_EBITDA` | Multiple anchor | `metadata.valuation.peer_ev_to_ebitda` | Method skipped |
| `GDP_NOMINAL_GROWTH` | Terminal growth ceiling | `metadata.valuation.gdp_nominal_growth` | 4% (flagged as default) |

### 5.3 Assumption source hierarchy (confidence impact)

| Source rank | Source type | Default confidence cap |
|---|---|---|
| 1 | Audited statements / market observables | 0.90 |
| 2 | `valuation_inputs` (analyst workbook mapped) | 0.85 |
| 3 | `metadata.valuation` with `assumption_evidence` | per evidence |
| 4 | Deterministic derived defaults | 0.60 |
| 5 | Global defaults (GDP, forecast years) | 0.50 |

---

## 6. Sensitivity Analysis

HAP emits **Bull**, **Base**, and **Bear** scenarios deterministically. Scenarios adjust assumptions — not rules.

### 6.1 Scenario definitions

| Scenario | Revenue growth | Operating / FCF margin | Terminal growth | WACC | Multiple peer anchor |
|---|---|---|---|---|---|
| **Bear** | −30% relative to base path (floor −10% CAGR) | −100 bps | −50 bps (floor 0%) | +75 bps | Peer **p25** |
| **Base** | Analyst / derived base forecast | Base | `terminal_growth_rate` | `wacc` | Peer **median** |
| **Bull** | +25% relative to base (cap +30% CAGR) | +100 bps | +25 bps (cap GDP) | −50 bps | Peer **p75** |

Overrides: `metadata.valuation.scenarios.bull|base|bear` may specify any field; overrides must include `assumption_evidence`.

### 6.2 Scenario outputs

| Output | Description |
|---|---|
| `SCENARIO_BEAR_VALUE_PER_SHARE` | Bear fair value |
| `SCENARIO_BASE_VALUE_PER_SHARE` | Base fair value (= `FAIR_VALUE_BASE`) |
| `SCENARIO_BULL_VALUE_PER_SHARE` | Bull fair value |
| `FAIR_VALUE_RANGE` | `[BEAR, BULL]` |
| `SCENARIO_MOS_BEAR` | MOS using bear value vs price |
| `SCENARIO_MOS_BULL` | MOS using bull value vs price |

### 6.3 Use in rules & score

- Wide bear–bull range increases `METHOD_SPREAD` and reduces confidence.  
- Base case drives `MARGIN_OF_SAFETY` for VA001–VA004.  
- Bear case used for conservative risk rules (VA018).

---

## 7. Deterministic Valuation Rules

Target: **38 rules** (`VA001`–`VA038`).  
Rules produce **findings only** — never buy/sell recommendations.

Severity enum: `POSITIVE`, `INFO`, `WARNING`, `CRITICAL`.

### 7.1 Margin of safety & price vs value (RULE_LIBRARY.md)

#### VA001 — Highly Attractive Valuation
- **Trigger:** `MARGIN_OF_SAFETY > 30%` (base case)
- **Severity:** POSITIVE
- **Finding:** Highly Attractive Valuation
- **Explanation:** Base-case intrinsic value exceeds market price by more than 30%.
- **Suggested Analyst Action:** None.

#### VA002 — Attractive Valuation
- **Trigger:** `15% ≤ MARGIN_OF_SAFETY ≤ 30%`
- **Severity:** POSITIVE
- **Finding:** Attractive Valuation
- **Explanation:** Meaningful but moderate margin of safety.
- **Suggested Analyst Action:** None.

#### VA003 — Limited Upside
- **Trigger:** `MARGIN_OF_SAFETY < 10%` AND `MARGIN_OF_SAFETY ≥ 0%`
- **Severity:** WARNING
- **Finding:** Limited Upside
- **Explanation:** Little room for error at current price.
- **Suggested Analyst Action:** Tighten assumption review; stress-test bear case.

#### VA004 — Potentially Overvalued
- **Trigger:** `FAIR_VALUE_BASE < share_price` (negative MOS)
- **Severity:** WARNING
- **Finding:** Potentially Overvalued
- **Explanation:** Base-case intrinsic value is below market price.
- **Suggested Analyst Action:** Review growth and margin assumptions; compare reverse DCF.

### 7.2 Reverse DCF & implied expectations

#### VA005 — Implied Growth Unrealistic
- **Trigger:** `REVERSE_DCF_IMPLIED_GROWTH > GDP_NOMINAL_GROWTH + 0.06` OR `REVERSE_DCF_IMPLIED_FCF_CAGR > 25%`
- **Severity:** WARNING
- **Finding:** Market Implies Aggressive Growth
- **Explanation:** Current price requires growth above plausible long-run bounds.
- **Suggested Analyst Action:** Challenge forecast; review competitive outlook.

#### VA006 — Implied Growth Conservative
- **Trigger:** `REVERSE_DCF_IMPLIED_GROWTH < 0%` while `MARGIN_OF_SAFETY > 15%`
- **Severity:** POSITIVE
- **Finding:** Market Pricing Pessimism
- **Explanation:** Price implies decline while base case shows material MOS.
- **Suggested Analyst Action:** Validate whether pessimism is warranted.

#### VA007 — Reverse DCF Unsolvable
- **Trigger:** WACC ≤ terminal growth OR negative base FCF without turnaround overlay
- **Severity:** INFO
- **Finding:** Reverse DCF Not Reliable
- **Explanation:** Inputs do not support a stable reverse DCF solution.
- **Suggested Analyst Action:** Rely on other methods; fix WACC/terminal spread.

### 7.3 WACC & discount rate discipline

#### VA008 — WACC Below Reasonable Range
- **Trigger:** `WACC < 0.06`
- **Severity:** WARNING
- **Finding:** WACC May Be Too Low
- **Explanation:** Discount rate below typical equity risk floor.
- **Suggested Analyst Action:** Revise WACC; document build-up.

#### VA009 — WACC Above Reasonable Range
- **Trigger:** `WACC > 0.14`
- **Severity:** WARNING
- **Finding:** WACC May Be Too High
- **Explanation:** Discount rate may over-penalize long-duration cash flows.
- **Suggested Analyst Action:** Revise WACC; review beta and capital structure.

#### VA010 — WACC Near Risk-Free Rate
- **Trigger:** `WACC < risk_free_rate + 0.03` when risk-free available
- **Severity:** CRITICAL
- **Finding:** WACC Inconsistent With Risk
- **Explanation:** Discount rate does not appear to price equity risk.
- **Suggested Analyst Action:** Revise WACC immediately.

### 7.4 Terminal growth discipline

#### VA011 — Terminal Growth Exceeds GDP
- **Trigger:** `TERMINAL_GROWTH > GDP_NOMINAL_GROWTH`
- **Severity:** WARNING
- **Finding:** Terminal Growth Above GDP
- **Explanation:** Perpetuity growth exceeds nominal GDP anchor.
- **Suggested Analyst Action:** Revise terminal growth.

#### VA012 — Terminal Growth Too High
- **Trigger:** `TERMINAL_GROWTH > 0.05`
- **Severity:** CRITICAL
- **Finding:** Unsustainable Terminal Growth
- **Explanation:** Terminal growth above 5% is rarely sustainable.
- **Suggested Analyst Action:** Revise terminal growth.

#### VA013 — Terminal Growth Negative
- **Trigger:** `TERMINAL_GROWTH < 0`
- **Severity:** WARNING
- **Finding:** Declining Terminal State
- **Explanation:** Valuation assumes perpetual decline.
- **Suggested Analyst Action:** Confirm structural decline narrative.

### 7.5 DCF structure & quality

#### VA014 — Terminal Value Dominates DCF
- **Trigger:** `DCF_TERMINAL_VALUE_SHARE > 0.75`
- **Severity:** WARNING
- **Finding:** DCF Dominated By Terminal Value
- **Explanation:** More than 75% of DCF value from terminal period.
- **Suggested Analyst Action:** Extend forecast; review terminal assumptions.

#### VA015 — Short Explicit Forecast
- **Trigger:** `FORECAST_YEARS < 5`
- **Severity:** INFO
- **Finding:** Short Forecast Horizon
- **Explanation:** Explicit forecast shorter than standard 5-year window.
- **Suggested Analyst Action:** Extend forecast or document rationale.

#### VA016 — Negative Explicit FCF Forecast
- **Trigger:** Any forecast year `FCF_t < 0` without `metadata.valuation.turnaround_plan`
- **Severity:** WARNING
- **Finding:** Negative FCF In Forecast
- **Explanation:** DCF relies on future cash flows not yet realized.
- **Suggested Analyst Action:** Document turnaround path; use bear weighting.

#### VA017 — DCF Not Computable
- **Trigger:** DCF method skipped (missing WACC or FCF)
- **Severity:** INFO
- **Finding:** DCF Valuation Unavailable
- **Explanation:** Insufficient inputs for DCF.
- **Suggested Analyst Action:** Supply WACC and FCF forecast inputs.

### 7.6 Scenario & method dispersion

#### VA018 — Bear Case Below Market
- **Trigger:** `SCENARIO_BEAR_VALUE_PER_SHARE < share_price`
- **Severity:** WARNING
- **Finding:** Bear Case Does Not Support Margin Of Safety
- **Explanation:** Even conservative scenario below current price.
- **Suggested Analyst Action:** Revisit assumptions or acknowledge limited downside cushion.

#### VA019 — Wide Valuation Dispersion
- **Trigger:** `METHOD_SPREAD > 0.40`
- **Severity:** WARNING
- **Finding:** Valuation Methods Disagree Materially
- **Explanation:** Methods span more than 40% of base value.
- **Suggested Analyst Action:** Reconcile method inputs; prioritize most economic method.

#### VA020 — Single Method Dependency
- **Trigger:** Only one valuation method available
- **Severity:** INFO
- **Finding:** Valuation Based On Single Method
- **Explanation:** No triangulation across methods.
- **Suggested Analyst Action:** Add peer multiples or owner earnings cross-check.

### 7.7 Multiples & peer discipline

#### VA021 — Multiple Above Peer Range
- **Trigger:** Implied `EV/EBITDA > peer_p75 × 1.15` OR imputed value from peer median **below** price while current multiple above p75
- **Severity:** WARNING
- **Finding:** Multiple Materially Above Peers
- **Explanation:** Market or model multiple exceeds peer upper range.
- **Suggested Analyst Action:** Review peer set and growth differentials.

#### VA022 — Multiple Below Peer Range
- **Trigger:** Implied multiple `< peer_p25 × 0.85` AND `MARGIN_OF_SAFETY > 10%`
- **Severity:** POSITIVE
- **Finding:** Discount To Peers
- **Explanation:** Valuation below peer lower bound with positive MOS.
- **Suggested Analyst Action:** Verify peer comparability.

#### VA023 — Peer Data Missing
- **Trigger:** Multiples method skipped — no peer metadata
- **Severity:** INFO
- **Finding:** Peer Multiples Not Available
- **Explanation:** Cannot cross-check vs peers.
- **Suggested Analyst Action:** Request industry research / peer set.

#### VA024 — Historical Multiple Extreme
- **Trigger:** Current implied multiple > `historical_median × 1.50`
- **Severity:** WARNING
- **Finding:** Historical Multiple Extreme
- **Explanation:** Trading rich vs own history.
- **Suggested Analyst Action:** Review whether fundamentals justify premium.

#### VA025 — Historical Discount
- **Trigger:** Current implied multiple `< historical_median × 0.75` AND `MARGIN_OF_SAFETY > 10%`
- **Severity:** POSITIVE
- **Finding:** Historical Valuation Discount
- **Explanation:** Below company's own typical multiple band.
- **Suggested Analyst Action:** Confirm regime change not warranted.

### 7.8 Owner earnings & earnings quality

#### VA026 — Owner Earnings Below Net Income
- **Trigger:** `OWNER_EARNINGS_RUN_RATE < net_income × 0.70` (latest year)
- **Severity:** WARNING
- **Finding:** Owner Earnings Below Reported Earnings
- **Explanation:** Cash economic earnings lag accounting earnings.
- **Suggested Analyst Action:** Review capex intensity and working capital.

#### VA027 — Owner Earnings Supports Value
- **Trigger:** `OE_VALUE_PER_SHARE` within 10% of `DCF_VALUE_PER_SHARE` and `MARGIN_OF_SAFETY > 15%`
- **Severity:** POSITIVE
- **Finding:** Owner Earnings Confirms DCF
- **Explanation:** Independent methods agree with attractive MOS.
- **Suggested Analyst Action:** None.

### 7.9 Capital structure & bridge integrity

#### VA028 — Net Debt Uncertainty
- **Trigger:** `valuation_inputs.net_debt` missing AND debt/cash series incomplete
- **Severity:** WARNING
- **Finding:** Net Debt Bridge Uncertain
- **Explanation:** EV to equity conversion may be unreliable.
- **Suggested Analyst Action:** Reconcile net debt; review capital structure.

#### VA029 — High Leverage Skews Equity Value
- **Trigger:** `net_debt / EV > 0.50` AND `|equity_value_delta_from_10pct_ev_error| > 15%` of equity
- **Severity:** WARNING
- **Finding:** Leverage Amplifies Valuation Error
- **Explanation:** Small EV errors swing equity materially.
- **Suggested Analyst Action:** Review debt and cash; stress EV sensitivity.

### 7.10 Workbook reconciliation

#### VA030 — Workbook Intrinsic Value Divergent
- **Trigger:** Workbook `INTRINSIC_VALUE` comparison `status = divergent`
- **Severity:** WARNING
- **Finding:** Workbook Intrinsic Value Diverges From HAP
- **Explanation:** Analyst workbook IV differs materially from HAP computation.
- **Suggested Analyst Action:** Reconcile inputs; investigate workbook formula.

#### VA031 — Workbook MOS Divergent
- **Trigger:** Workbook `MARGIN_OF_SAFETY` divergent (>3pp absolute)
- **Severity:** WARNING
- **Finding:** Workbook Margin Of Safety Diverges
- **Explanation:** MOS formula or price input may differ.
- **Suggested Analyst Action:** Reconcile price, share count, and fair value cells.

#### VA032 — Workbook WACC Divergent
- **Trigger:** Workbook `WACC` divergent (>75 bps)
- **Severity:** WARNING
- **Finding:** Workbook WACC Diverges
- **Explanation:** Discount rate assumptions differ.
- **Suggested Analyst Action:** Revise WACC build-up; align assumptions.

#### VA033 — Workbook Terminal Growth Divergent
- **Trigger:** Workbook terminal growth divergent (>50 bps)
- **Severity:** WARNING
- **Finding:** Workbook Terminal Growth Diverges
- **Explanation:** Perpetuity assumptions differ.
- **Suggested Analyst Action:** Revise terminal growth; document rationale.

#### VA034 — Workbook Fair Value Matches HAP
- **Trigger:** Workbook `FAIR_VALUE` within tolerance
- **Severity:** POSITIVE
- **Finding:** Workbook Valuation Aligned With HAP
- **Explanation:** Independent HAP valuation confirms workbook fair value.
- **Suggested Analyst Action:** None.

#### VA035 — Workbook Value Without HAP Reproduction
- **Trigger:** Workbook valuation present; HAP cannot compute equivalent (hap_only inverse)
- **Severity:** INFO
- **Finding:** HAP Could Not Reproduce Workbook Valuation
- **Explanation:** Missing inputs prevent HAP from validating workbook.
- **Suggested Analyst Action:** Supply missing assumptions.

### 7.11 Cyclical, distressed & special situations

#### VA036 — Cyclical Peak Earnings Risk
- **Trigger:** `metadata.valuation.cyclicality_flag = true` AND margins > 120% of 10Y median AND multiples method used
- **Severity:** WARNING
- **Finding:** Cyclical Peak Normalization Required
- **Explanation:** Normalized earnings may be lower than current.
- **Suggested Analyst Action:** Use through-cycle margins in valuation.

#### VA037 — Distressed Equity Optionality
- **Trigger:** `FAIR_VALUE_BASE < 0` OR `latest_FCF < 0` for ≥3 years AND positive `HAP_EQUITY_VALUE` only from optionality overlay
- **Severity:** CRITICAL
- **Finding:** Distressed Valuation Uncertainty
- **Explanation:** Equity value relies on turnaround not in base statements.
- **Suggested Analyst Action:** Model restructuring; widen bear case.

#### VA038 — Insufficient Valuation Inputs
- **Trigger:** `< 2` methods available AND no `share_price`
- **Severity:** CRITICAL
- **Finding:** Insufficient Valuation Evidence
- **Explanation:** Cannot form a reliable view of worth.
- **Suggested Analyst Action:** Request market data and valuation assumptions.

### Rule → output mapping

| Rule severity | `findings[].severity` | Also emit |
|---|---|---|
| POSITIVE | `positive` | `opportunities` |
| INFO | `info` | optional finding only |
| WARNING | `warning` | `risks` |
| CRITICAL | `critical` | `risks` |

Every finding **must** include evidence (metric, value, period, source, confidence).

---

## 8. Scoring

### 8.1 Score definition

- **Name:** Valuation Score (Enterprise Valuation Score)
- **Range:** 0–100
- **Interpretation:** Measures **reasonableness of valuation vs economic worth and market price** — **not** business quality and **not** a buy signal
- **Roll-up:** Feeds **Investment Attractiveness** (with Expected Return, Margin of Safety, Relative Valuation per `SCORING_SYSTEM.md`)
- **Determinism:** Identical inputs ⇒ identical score

**Score direction:** Higher = more attractive **pricing vs intrinsic worth** (larger margin of safety / less overvaluation).

### 8.2 Component weights (must total 100%)

`SCORING_SYSTEM.md` lists valuation **inputs** but not component weights. The following weights are authoritative for implementation until `SCORING_SYSTEM.md` is amended:

| Component code | Primary inputs | Weight | Justification |
|---|---|---|---|
| `MARGIN_OF_SAFETY` | `MARGIN_OF_SAFETY` mapped to 0–100 | **35%** | Primary economic question: how much worth exceeds price (Playbook Principle 10) |
| `DCF_REASONABLENESS` | Terminal share, WACC/g spread, forecast plausibility | **25%** | DCF is primary intrinsic method in methodology; score reflects **assumption quality**, not just output |
| `MULTIPLE_REASONABLENESS` | vs peers and vs history | **20%** | Cross-checks DCF; captures market-relative worth |
| `METHOD_CONVERGENCE` | `METHOD_SPREAD` inverse | **10%** | Triangulation reduces model risk |
| `WORKBOOK_ALIGNMENT` | Workbook comparison statuses | **10%** | Validates analyst model integrity without using workbook in formulas |
| **Total** | | **100%** | |

### 8.3 Component maps (deterministic)

**Margin of Safety → score**

| MOS | Score |
|---|---|
| ≤ −30% (deep premium) | 10 |
| −15% | 25 |
| 0% | 45 |
| +10% | 60 |
| +20% | 75 |
| +30% | 85 |
| ≥ +50% | 95 |

**DCF Reasonableness → score** (start 70, apply adjustments, clamp 0–100)

| Condition | Adjustment |
|---|---|
| Terminal value share > 75% | −20 |
| Terminal growth > GDP | −15 |
| WACC outside [6%, 14%] | −15 |
| Forecast years < 5 | −5 |
| Reverse DCF implied growth unrealistic (VA005) | −10 |
| All DCF checks pass | +10 |

**Multiple Reasonableness → score**

| Condition | Score band |
|---|---|
| Below peer p25 with positive MOS | 85–95 |
| Near peer median | 55–65 |
| Above peer p75 | 25–40 |
| Peer data missing | component unavailable |

**Method Convergence → score**

| METHOD_SPREAD | Score |
|---|---|
| ≤ 15% | 90 |
| 25% | 70 |
| 40% | 50 |
| ≥ 60% | 30 |

**Workbook Alignment → score**

| Comparison summary | Score |
|---|---|
| All comparable metrics `match` or `within_tolerance` | 90 |
| Any `divergent` on IV or MOS | 45 |
| Workbook-only valuation with no HAP reproduction | 50 |
| No workbook comparables | component unavailable |

### 8.4 Renormalization

If a component is unavailable, remove its weight, renormalize remaining weights to 100%, record `coverage.effective_weights`, and apply confidence penalties (§9).

If `MARGIN_OF_SAFETY` unavailable (no price), Valuation Score = `null` unless policy explicitly allows enterprise-only mode (document in coverage; default `score = null`).

---

## 9. Confidence

Confidence ∈ [0, 1] qualifies the Valuation Score; it **never** changes the score.

### 9.1 Base confidence

Weighted mean of:

- Method-level confidences (per §3)  
- Assumption source confidences (§5.3)  
- Component availability ratio

### 9.2 Confidence decreases when

| Condition | Penalty (indicative) |
|---|---|
| Assumptions primarily analyst-supplied without `assumption_evidence` | −0.10 |
| Forecast horizon < 5 years | −0.05 |
| `< 3` explicit forecast fields derived by default | −0.08 |
| Valuation methods disagree (`METHOD_SPREAD > 40%`) | −0.12 |
| Workbook WACC, terminal growth, or IV **divergent** | −0.08 each (cap −0.20) |
| Market data stale (`as_of_date` > 90 days vs analysis date) | −0.10 |
| Only one method available | −0.12 |
| DCF terminal value share > 75% | −0.06 |
| Peer / historical multiple data missing | −0.05 each |
| Cyclical peak not normalized when flag set | −0.08 |

### 9.3 Confidence increases when

| Condition | Boost (indicative) |
|---|---|
| ≥3 methods within 15% spread | +0.05 |
| Workbook IV and MOS align with HAP | +0.05 |
| Full `assumption_evidence` on WACC, terminal growth, forecast | +0.05 |
| Owner earnings confirms DCF (VA027) | +0.03 |

### 9.4 Confidence cap

`VALUATION_CONFIDENCE_CAP = 0.85` — valuation remains assumption-forward.

Emit on `AnalysisModuleResult.confidence`.

---

## 10. Analyst Adjustments

Adjustments propose changes to **valuation inputs and overlays**. They never silently overwrite workbook cells or reported statements.

| Adjustment action | `rationale_code` (examples) | Typical targets |
|---|---|---|
| `review_assumption` | `REVISE_WACC` | `valuation_inputs.wacc` |
| `review_assumption` | `REVISE_TERMINAL_GROWTH` | `valuation_inputs.terminal_growth_rate` |
| `adjust_forecast` | `REVISE_FORECAST_MARGINS` | `metadata.valuation.forecast_operating_margin` |
| `adjust_forecast` | `REVISE_FORECAST_GROWTH` | `metadata.valuation.forecast_revenue_growth` |
| `review_assumption` | `REVIEW_PEER_MULTIPLES` | `metadata.valuation.peer_ev_to_ebitda` |
| `review_assumption` | `REVIEW_CAPITAL_STRUCTURE` | `valuation_inputs.net_debt` |
| `review_assumption` | `NORMALIZE_CYCLICAL_EARNINGS` | `metadata.valuation.normalized_ebitda` |
| `request_more_data` | `MISSING_MARKET_DATA` | `market_data.share_price` |
| `request_more_data` | `MISSING_PEER_DATA` | `metadata.valuation.peer_ev_to_ebitda` |
| `request_more_data` | `MISSING_MAINTENANCE_CAPEX` | `metadata.valuation.maintenance_capex` |
| `reconcile_inputs` | `WORKBOOK_HAP_DIVERGENCE` | divergent workbook metric |
| `investigate_workbook_formula` | `WORKBOOK_FORMULA_REVIEW` | workbook metric `cell_ref` |
| `request_analyst_review` | `VALUATION_UNCERTAINTY` | module-level |

Each adjustment records: original value, proposed direction, related finding IDs, confidence, priority.

---

## 11. Unit Test Scenarios

Each scenario builds a `CompanyFinancialModel` fixture (future `tests/test_enterprise_valuation_module.py`). Assert score bands, key metrics, rule hits, workbook comparisons, and deterministic replay.

### 11.1 Deeply undervalued — “Cigar Butt Industrials”

- Price implies MOS **+40%**; peer/historical multiples low; reverse DCF implies modest growth  
- **Expect:** Valuation Score **85–95**; VA001, VA022 or VA025, VA006  
- **Workbook:** Aligned MOS — VA034  
- **Confidence:** High if peer data present  

### 11.2 Fairly valued — “Steady Compounder”

- MOS **+8–12%**; methods within 15% spread; multiples near peer median  
- **Expect:** Valuation Score **55–70**; VA003 borderline; few warnings  
- **Confidence:** Medium-high  

### 11.3 Expensive quality compounder — “Premium Franchise”

- MOS **negative**; price above peer p75; reverse DCF implies aggressive growth (VA005)  
- **Expect:** Valuation Score **20–40**; VA004, VA021, VA024  
- **Risks:** overvaluation, implied growth  
- **Note:** Business Quality may be high — valuation score must still be low  

### 11.4 Distressed — “Turnaround Steel Co”

- Negative FCF 4 years; equity value only with explicit turnaround overlay; bear case below price  
- **Expect:** Valuation Score **< 35** or `null`; VA016, VA037, VA018  
- **Confidence:** Low  

### 11.5 Cyclical — “Peak Cycle Chemicals”

- Margins 130% of 10Y median; `cyclicality_flag=true`; normalized EBITDA overlay lowers value  
- **Expect:** VA036 fires; score lower when normalized; confidence reduced without normalization  
- **Adjustment:** `NORMALIZE_CYCLICAL_EARNINGS` proposed  

### 11.6 Inconsistent workbook — “Model Mismatch Corp”

- Workbook IV 20% above HAP; workbook WACC 200 bps below HAP; workbook MOS divergent  
- **Expect:** VA030, VA031, VA032; `WORKBOOK_ALIGNMENT` component weak; adjustments `reconcile_inputs`  
- **Golden rule:** workbook values unchanged in model  

### 11.7 DCF dominated by terminal value

- Terminal share **80%**; VA014; DCF reasonableness component penalized  
- **Expect:** Score capped despite positive MOS  

### 11.8 Single-method / missing price

- No `share_price` — MOS unavailable; only multiples method  
- **Expect:** `MARGIN_OF_SAFETY` component skipped; VA020; confidence ≤0.60  

### 11.9 Deterministic replay

- Run module twice on identical model — **identical** `score`, `confidence`, `metrics`, `findings`, comparisons  

### 11.10 Skipped module

- Missing FCF and price — `status = skipped`, `score = null`, VA038 or skip reason in coverage  

---

## 12. Module Output Contract

Returns standard `AnalysisModuleResult`:

| Field | Content |
|---|---|
| `module_name` | `valuation` |
| `score` | Valuation Score 0–100 or `null` |
| `confidence` | Per §9 |
| `metrics` | All HAP valuation metrics (§3.7) |
| `findings` | VA001+ rule hits |
| `risks` / `opportunities` | Mapped from rules |
| `evidence` | Union of metric and finding evidence |
| `analyst_adjustments` | Per §10 |
| `component_scores` | Five components per §8 |
| `coverage` | `assumptions`, `scenarios`, `metric_comparisons`, `effective_weights`, `methods_used` |

No narrative text. No recommendation field.

---

## 13. Implementation Checklist (future)

- [ ] `backend/analysis_engine/modules/valuation.py` — replace scaffold  
- [ ] `backend/scoring_engine/valuation.py` — component scoring  
- [ ] `backend/scoring_engine/weights.py` — `VALUATION_WEIGHTS` constant  
- [ ] `backend/rule_library/valuation.py` — VA001–VA038  
- [ ] `backend/tests/test_enterprise_valuation_module.py` — §11 scenarios  
- [ ] Optional: extend `_WORKBOOK_METRIC_ROUTES` for `ENTERPRISE_VALUE`, `EQUITY_VALUE`, `FAIR_VALUE` (builder change — separate PR)

---

## 14. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-15 | Initial Enterprise Valuation module specification |
