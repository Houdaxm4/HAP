# HAP Growth Module Specification

Version: 1.0  
Status: Implemented  
Module ID: `growth`
Parent specs: `docs/FINANCIAL_ANALYSIS_SPEC.md`, `docs/SCORING_SYSTEM.md`, `docs/RULE_LIBRARY.md`, `docs/INVESTMENT_NETHODOLOGY.md`, `docs/HAP_ANALYST_PLAYBOOK.md`, `docs/PROJECT.md`

---

## 0. Compliance Constraints

This specification must not introduce new architectural layers or change existing contracts.

| Constraint | Requirement |
|---|---|
| Input contract | Module consumes **only** `CompanyFinancialModel` |
| Output contract | Module returns standard `AnalysisModuleResult` |
| Forbidden access | No Excel, workbook cells, SEC APIs, Yahoo Finance, or raw JSON parsing |
| Scoring philosophy | Deterministic rules + weighted metrics; **no LLM judgment** |
| Role of LLM | Explains results later; never invents growth conclusions |
| Quality vs attractiveness | Growth contributes to **Business Quality** only (15% of BQ). It does **not** encode valuation or buy/sell decisions |
| Golden rules | Never invent financial data; preserve provenance; human judgment overrides via documented analyst adjustments |

Existing Growth Score weights from `SCORING_SYSTEM.md` are authoritative and must sum to **100%**:

| Component | Weight |
|---|---|
| Revenue CAGR | 30% |
| EPS CAGR | 25% |
| FCF CAGR | 25% |
| Growth Stability | 10% |
| Organic Growth | 10% |
| **Total** | **100%** |

---

## 1. Purpose

### Business question

**Does the company grow in a durable, economically valuable way that creates long-term shareholder value — independent of today’s stock price?**

The Growth Module answers Stage 1 / Stage 2 questions from the investment methodology relating to growth quality:

- Is growth sustainable across a multi-year window (prefer 10 years; minimum 5)?
- Is growth profitable (earnings and cash grow with, or faster than, revenue)?
- Is growth accelerating, stable, or decelerating?
- Is reported growth organic, or inflated by acquisitions / one-time items / share issuance?

### What this module does **not** answer

- Whether the stock is cheap or expensive today (Valuation / Expected Return).
- Final Buy / Watch / Avoid recommendations (Recommendation Module).
- Narrative report writing (Report Generator).

### Single responsibility

One concern only: **growth durability and economic quality of growth**.

---

## 2. Inputs

### 2.1 Required context fields

| Field | Type | Requirement |
|---|---|---|
| `analysis_id` | `str` | Required |
| `ticker` | `str` | Required |
| `company` | `str \| None` | Optional |
| `reporting_currency` | `str` | Required (default USD) |
| `periods` | `list[str]` | Preferred (union of statement periods) |
| `valuation_inputs.wacc` | `float \| None` | Optional (used only for interpretive context vs cost of capital; **not** a Growth Score weight) |
| `metadata` | `dict` | Optional overlays listed below |

### 2.2 Required / preferred `CompanyFinancialModel` series

The module reads historical `FinancialSeries` / `FinancialPoint` objects only.

| Series path | Role | Requirement for scoring |
|---|---|---|
| `income_statement.revenue` | Revenue CAGR, YoY, organic base | **Required** for module `ok` status |
| `income_statement.diluted_eps` | EPS CAGR / EPS growth | **Required** for EPS component; if missing, EPS weight is renormalized away and confidence falls |
| `cash_flow_statement.free_cash_flow` | FCF CAGR / quality of growth | **Required** for FCF component; if missing, FCF weight is renormalized away and confidence falls |
| `income_statement.operating_income` (or `ebit` fallback) | Operating income CAGR / operating leverage | Preferred |
| `income_statement.net_income` | Cross-check vs EPS; earnings growth persistence | Preferred |
| `income_statement.gross_profit` | Optional margin-linked growth quality checks | Optional |
| `balance_sheet.shareholders_equity` | Book value CAGR | Preferred |
| `market_data.shares_outstanding` | Latest share count only | Insufficient alone for CAGR |
| Share-count history | Share Count CAGR / dilution rules | Preferred via `metadata["share_count_series"]` (period → shares) until a first-class series exists — **no new model layer** |
| Acquisition / inorganic revenue | Organic growth estimation | Preferred via `metadata["acquired_revenue_by_period"]` or `metadata["organic_revenue_series"]` |
| Inflation reference | GR003 vs inflation | Optional via `metadata["inflation_rate"]` (default assumption documented if absent) |

### 2.3 Provenance requirements

Every metric evidence object must retain, when available:

- value, period, currency  
- source, confidence, audited  
- provenance (cell_ref / xbrl_tag / source_document as already stored on `FinancialPoint`)

The module must never invent missing history. Missing periods reduce coverage and confidence; they do not invent interpolated “fake” years unless an analyst adjustment explicitly authorizes a normalized series.

### 2.4 Minimum history windows

Aligned with `HAP_ANALYST_PLAYBOOK.md`:

| Window | Use |
|---|---|
| 10 years | Preferred CAGR / persistence window when available |
| 5 years | Standard scoring window (`TREND_WINDOW = 5`) |
| < 5 years | Module may still run with reduced confidence; CAGR components use available intervals; Stability may be `skipped` |

---

## 3. Metrics

All metrics are machine-readable (`MetricResult` codes). Units are ratios unless noted.

### 3.1 Core growth rates

| Code | Name | Definition |
|---|---|---|
| `REV_CAGR` | Revenue CAGR | CAGR of `revenue` over scoring window |
| `REV_YOY` | Revenue YoY Growth | Latest period vs prior period revenue change |
| `EPS_CAGR` | EPS CAGR | CAGR of `diluted_eps` over scoring window |
| `EPS_YOY` | EPS Growth (YoY) | Latest vs prior diluted EPS change |
| `OI_CAGR` | Operating Income CAGR | CAGR of operating income / EBIT |
| `OI_YOY` | Operating Income YoY | Latest vs prior operating income change |
| `FCF_CAGR` | FCF CAGR | CAGR of free cash flow |
| `FCF_YOY` | FCF YoY Growth | Latest vs prior FCF change |
| `BV_CAGR` | Book Value CAGR | CAGR of shareholders’ equity |
| `NI_CAGR` | Net Income CAGR | CAGR of net income (supporting metric) |

### 3.2 Growth quality / structure

| Code | Name | Definition |
|---|---|---|
| `ORGANIC_REV_CAGR` | Organic Revenue CAGR | CAGR of organic revenue if provided; else estimated as reported revenue CAGR adjusted for disclosed acquired revenue |
| `INORGANIC_REV_SHARE` | Inorganic Revenue Share | Acquired / one-time revenue ÷ total revenue (latest or average window) |
| `SHARE_COUNT_CAGR` | Share Count CAGR | CAGR of diluted shares outstanding |
| `SHARE_COUNT_YOY` | Share Count YoY | Latest vs prior share count change |
| `REV_PER_SHARE_CAGR` | Revenue per Share CAGR | CAGR of revenue ÷ shares (anti-dilution view) |
| `FCF_PER_SHARE_CAGR` | FCF per Share CAGR | CAGR of FCF ÷ shares |

### 3.3 Stability, volatility, persistence, trend

| Code | Name | Definition |
|---|---|---|
| `GROWTH_STABILITY` | Growth Stability | `1 / (1 + CV)` of trailing revenue YoY growth rates over window (0–1) |
| `GROWTH_VOLATILITY` | Growth Volatility | Coefficient of variation of trailing revenue YoY growth rates |
| `GROWTH_PERSISTENCE` | Growth Persistence | Fraction of periods in window with positive revenue YoY growth |
| `GROWTH_TREND` | Growth Trend Direction | Encoded score: up = +1, flat = 0, down = −1 from revenue YoY sequence / CAGR sign |
| `GROWTH_ACCELERATION` | Growth Acceleration | Latest 2Y revenue CAGR − prior 2Y revenue CAGR (same-length windows) |
| `EPS_VS_REV_SPREAD` | EPS vs Revenue Growth Spread | `EPS_CAGR − REV_CAGR` (operating leverage signal) |
| `FCF_VS_REV_SPREAD` | FCF vs Revenue Growth Spread | `FCF_CAGR − REV_CAGR` (cash quality of growth) |
| `OI_VS_REV_SPREAD` | Op. Income vs Revenue Spread | `OI_CAGR − REV_CAGR` |

### 3.4 Coverage / confidence diagnostics (not scored directly)

| Code | Name | Definition |
|---|---|---|
| `REV_HISTORY_YEARS` | Revenue History Length | Count of revenue points |
| `EPS_HISTORY_YEARS` | EPS History Length | Count of EPS points |
| `FCF_HISTORY_YEARS` | FCF History Length | Count of FCF points |
| `ORGANIC_DATA_AVAILABLE` | Organic Data Flag | 1 if organic/acquisition overlays present, else 0 |

---

## 4. Financial Interpretation

| Metric | Why it matters (HAP methodology) |
|---|---|
| **Revenue CAGR** | Top-line durability is the foundation of long-term business compounding. Per playbook, multi-year windows matter more than one quarter. |
| **Revenue YoY** | Detects near-term inflection (acceleration / stall) without replacing long-term CAGR. |
| **EPS CAGR / EPS Growth** | Shows whether growth reaches shareholders after costs, interest, tax, and share count. EPS rising faster than revenue can indicate operating leverage (GR004). |
| **Operating Income CAGR** | Bridges revenue and net earnings; isolates operating performance from financing / tax noise. |
| **FCF CAGR** | Cash is harder to manipulate (Playbook Principle 5). Growth that does not produce cash is low-quality (GR005). |
| **Book Value CAGR** | Tracks accumulated capital / retained earnings trajectory; useful when EPS is noisy but equity compounds. |
| **Organic Growth** | Distinguishes real franchise expansion from acquisition stacking (methodology: growth must create value, not just scale). |
| **Share Count CAGR** | Dilution can erase per-share value even when consolidated revenue rises (GR006). |
| **Growth Stability** | Smooth compounding is more investable than boom/bust “growth” that does not persist. |
| **Growth Volatility** | High volatility raises forecast risk and lowers confidence in forward assumptions. |
| **Growth Persistence** | Counts how often growth is actually positive — a durability check beyond average CAGR. |
| **Acceleration** | Separates improving franchises from decelerating mature businesses (Watch vs Buy context later — not scored as recommendation here). |
| **EPS/FCF vs Revenue spreads** | Encode Playbook Principle 7: growth only matters if economically valuable. |

---

## 5. Deterministic Rules (GR001+)

Rules produce **findings / risks / opportunities** only.  
They **never** produce Buy/Sell recommendations (`RULE_LIBRARY.md` principle).

Severity scale: `INFO` | `POSITIVE` | `WARNING` | `CRITICAL`

Default inflation assumption when `metadata.inflation_rate` is absent: **3.0%**.  
Default scoring / rule window: **5 years** unless a rule specifies otherwise.  
“Consistently” means every year in the evaluated window.

### Foundational rules (extend existing GR001–GR007)

#### GR001 — Exceptional Revenue Growth
- **Trigger:** `REV_CAGR > 15%` over scoring window (≥3 periods)
- **Severity:** POSITIVE  
- **Finding:** Exceptional Revenue Growth  
- **Explanation:** Multi-year revenue compounding exceeds the exceptional growth threshold.  
- **Suggested Analyst Action:** Confirm growth is organic and cash-backed; no automatic adjustment.

#### GR002 — Healthy Revenue Growth
- **Trigger:** `8% ≤ REV_CAGR ≤ 15%`
- **Severity:** POSITIVE  
- **Finding:** Healthy Revenue Growth  
- **Explanation:** Revenue compounds at a healthy long-term rate.  
- **Suggested Analyst Action:** None.

#### GR003 — Weak Real Growth vs Inflation
- **Trigger:** `REV_CAGR < inflation_rate` (metadata or 3% default)
- **Severity:** WARNING  
- **Finding:** Weak Organic Growth  
- **Explanation:** Top-line growth fails to outpace inflation, implying weak real expansion.  
- **Suggested Analyst Action:** Check pricing power, volume trends, and discontinued operations.

#### GR004 — Operating Leverage Improving
- **Trigger:** `EPS_CAGR > REV_CAGR` by ≥ 2 percentage points AND `REV_CAGR > 0`
- **Severity:** POSITIVE  
- **Finding:** Operating Leverage Improving  
- **Explanation:** Earnings are compounding faster than revenue.  
- **Suggested Analyst Action:** Verify margin expansion is sustainable, not one-time cost cuts.

#### GR005 — Low Quality Growth (Revenue up, FCF down)
- **Trigger:** `REV_CAGR > 0` AND `FCF_CAGR < 0` over same window
- **Severity:** WARNING  
- **Finding:** Low Quality Growth  
- **Explanation:** Sales expand while free cash flow contracts.  
- **Suggested Analyst Action:** Inspect WC, CapEx intensity, and cash conversion.

#### GR006 — Shareholder Dilution
- **Trigger:** Share count increases in every year of a ≥3-year window
- **Severity:** WARNING  
- **Finding:** Shareholder Dilution  
- **Explanation:** Persistent share issuance dilutes ownership.  
- **Suggested Analyst Action:** Review equity compensation and issuance; prefer per-share metrics.

#### GR007 — Acquisition-Driven Growth
- **Trigger:** `INORGANIC_REV_SHARE ≥ 30%` of revenue growth over window **OR** analyst metadata flags acquisition-primary growth
- **Severity:** WARNING  
- **Finding:** Acquisition Driven Growth  
- **Explanation:** Reported growth appears dependent on acquisitions rather than organic demand.  
- **Suggested Analyst Action:** Separate organic growth; normalize acquisition effects.

### Extended growth-rate rules

#### GR008 — Exceptional EPS Growth
- **Trigger:** `EPS_CAGR > 20%`
- **Severity:** POSITIVE  
- **Finding:** Exceptional Earnings Growth  
- **Explanation:** Diluted EPS compounds at an exceptional rate.  
- **Suggested Analyst Action:** Confirm not driven solely by buybacks or one-time tax items.

#### GR009 — Negative Earnings Growth
- **Trigger:** `EPS_CAGR < 0` over window with ≥3 EPS points
- **Severity:** WARNING  
- **Finding:** Negative Earnings Growth  
- **Explanation:** Shareholder earnings are contracting on a multi-year basis.  
- **Suggested Analyst Action:** Separate cyclical vs structural decline.

#### GR010 — Exceptional FCF Growth
- **Trigger:** `FCF_CAGR > 15%` AND latest FCF > 0
- **Severity:** POSITIVE  
- **Finding:** Exceptional Cash Flow Growth  
- **Explanation:** Free cash flow is compounding strongly.  
- **Suggested Analyst Action:** None.

#### GR011 — FCF Collapse Despite Scale
- **Trigger:** Latest FCF < 0 AND `REV_CAGR > 5%`
- **Severity:** CRITICAL  
- **Finding:** Cash-Consuming Expansion  
- **Explanation:** The business is growing sales while burning cash.  
- **Suggested Analyst Action:** Stress-test funding needs and reinvestment returns.

#### GR012 — Stagnant Revenue
- **Trigger:** `abs(REV_CAGR) < 0.02` over 5Y window
- **Severity:** INFO  
- **Finding:** Revenue Stagnation  
- **Explanation:** Top line is roughly flat in nominal terms.  
- **Suggested Analyst Action:** Evaluate whether maturity is acceptable given returns on capital (other modules).

#### GR013 — Severe Revenue Decline
- **Trigger:** `REV_CAGR ≤ −5%`
- **Severity:** CRITICAL  
- **Finding:** Structural Revenue Decline  
- **Explanation:** Multi-year revenue contraction indicates franchise pressure.  
- **Suggested Analyst Action:** Assess disruption, share loss, and turnaround credibility.

### Quality, leverage, and per-share rules

#### GR014 — Cash-Backed Growth
- **Trigger:** `FCF_CAGR ≥ REV_CAGR − 0.02` AND `REV_CAGR > 0` AND latest FCF > 0
- **Severity:** POSITIVE  
- **Finding:** Cash-Backed Growth  
- **Explanation:** Cash generation keeps pace with top-line expansion.  
- **Suggested Analyst Action:** None.

#### GR015 — Earnings Growth Without Cash
- **Trigger:** `EPS_CAGR > 5%` AND `FCF_CAGR < 0`
- **Severity:** WARNING  
- **Finding:** Accrual Growth Risk  
- **Explanation:** Accounting earnings grow while free cash flow does not.  
- **Suggested Analyst Action:** Review receivables, capitalization policies, and non-cash earnings.

#### GR016 — Anti-Dilutive Growth
- **Trigger:** `SHARE_COUNT_CAGR < 0` AND `REV_CAGR > 0`
- **Severity:** POSITIVE  
- **Finding:** Anti-Dilutive Expansion  
- **Explanation:** Revenue grows while share count shrinks — supportive of per-share value.  
- **Suggested Analyst Action:** Confirm buybacks are not debt-funded beyond prudence (Balance Sheet module).

#### GR017 — Per-Share Revenue Erosion
- **Trigger:** `REV_CAGR > 0` AND `REV_PER_SHARE_CAGR < 0`
- **Severity:** WARNING  
- **Finding:** Dilution Exceeds Top-Line Growth  
- **Explanation:** Consolidated growth is negated on a per-share basis.  
- **Suggested Analyst Action:** Recast growth on per-share metrics for investment debate.

#### GR018 — Book Value Compounding
- **Trigger:** `BV_CAGR ≥ 8%` over window
- **Severity:** POSITIVE  
- **Finding:** Strong Book Value Compounding  
- **Explanation:** Equity book value compounds at a healthy rate.  
- **Suggested Analyst Action:** Check whether AOCI / buybacks distort book trends.

### Stability / persistence / acceleration rules

#### GR019 — Stable Growth Profile
- **Trigger:** `GROWTH_STABILITY ≥ 0.70` AND `REV_CAGR > 0`
- **Severity:** POSITIVE  
- **Finding:** Stable Growth  
- **Explanation:** Positive growth with low volatility of yearly growth rates.  
- **Suggested Analyst Action:** None.

#### GR020 — Unstable Growth Profile
- **Trigger:** `GROWTH_VOLATILITY > 0.80` (CV of revenue YoY) OR `GROWTH_STABILITY < 0.40`
- **Severity:** WARNING  
- **Finding:** Unstable Growth  
- **Explanation:** Growth rates swing widely, reducing forecast reliability.  
- **Suggested Analyst Action:** Prefer longer windows; normalize one-time spikes.

#### GR021 — High Growth Persistence
- **Trigger:** `GROWTH_PERSISTENCE ≥ 0.80` over ≥5 YoY observations
- **Severity:** POSITIVE  
- **Finding:** Persistent Growth  
- **Explanation:** Revenue rose in most observed years.  
- **Suggested Analyst Action:** None.

#### GR022 — Growth Deceleration
- **Trigger:** `GROWTH_ACCELERATION ≤ −5 percentage points`
- **Severity:** WARNING  
- **Finding:** Growth Deceleration  
- **Explanation:** Recent growth is materially slower than the prior sub-period.  
- **Suggested Analyst Action:** Update outlook assumptions; avoid extrapolating old CAGR.

#### GR023 — Growth Acceleration
- **Trigger:** `GROWTH_ACCELERATION ≥ +5 percentage points` AND latest `REV_YOY > 0`
- **Severity:** POSITIVE  
- **Finding:** Growth Acceleration  
- **Explanation:** Recent growth is materially faster than the prior sub-period.  
- **Suggested Analyst Action:** Test durability vs easy comps / temporary stimulus.

#### GR024 — Boom-Bust Pattern
- **Trigger:** At least one `REV_YOY > 25%` and at least one `REV_YOY < −10%` within same 5Y window
- **Severity:** WARNING  
- **Finding:** Boom-Bust Growth Pattern  
- **Explanation:** Extreme positive and negative years appear in the same window.  
- **Suggested Analyst Action:** Normalize cycle; do not treat peak CAGR as base case.

### Special-situation and integrity rules

#### GR025 — Hypergrowth Sustainability Risk
- **Trigger:** `REV_CAGR > 30%` over ≥3 years
- **Severity:** WARNING  
- **Finding:** Hypergrowth Sustainability Risk  
- **Explanation:** Extremely high compounding rarely persists; fade risk is elevated.  
- **Suggested Analyst Action:** Use fade assumptions in outlook/valuation; stress-test.

#### GR026 — COVID / Base-Effect Distortion
- **Trigger:** Metadata flag `normalize_covid=true` **OR** (window includes FY2020–FY2021 and `|REV_YOY| > 40%` in any of those years)
- **Severity:** INFO  
- **Finding:** Possible Base-Effect Distortion  
- **Explanation:** Pandemic-period base effects may distort CAGR.  
- **Suggested Analyst Action:** Propose COVID-normalized growth series via analyst adjustment.

#### GR027 — One-Time Revenue Spike
- **Trigger:** Latest `REV_YOY > 40%` AND prior 3Y average `REV_YOY < 10%`
- **Severity:** WARNING  
- **Finding:** One-Time Revenue Spike Suspected  
- **Explanation:** Latest growth far exceeds recent history.  
- **Suggested Analyst Action:** Remove one-time revenue; recompute organic CAGR.

#### GR028 — Discontinued Operations Distortion
- **Trigger:** `metadata.discontinued_operations_impact = true` OR notes flag material discontinued ops
- **Severity:** WARNING  
- **Finding:** Discontinued Operations Distortion  
- **Explanation:** Reported growth may be non-comparable across periods.  
- **Suggested Analyst Action:** Restate continuing-operations growth series.

#### GR029 — Negative Equity / Invalid Book Growth
- **Trigger:** Any shareholders’ equity point ≤ 0 in window while computing `BV_CAGR`
- **Severity:** INFO  
- **Finding:** Book Value Growth Not Meaningful  
- **Explanation:** Book CAGR is unreliable with zero/negative equity.  
- **Suggested Analyst Action:** Ignore BV_CAGR; rely on revenue/EPS/FCF growth.

#### GR030 — Insufficient History
- **Trigger:** Revenue points < 3
- **Severity:** WARNING  
- **Finding:** Insufficient Growth History  
- **Explanation:** Too little history for robust multi-year growth conclusions.  
- **Suggested Analyst Action:** Lower confidence; request longer series before high-conviction use.

#### GR031 — Organic Growth Leadership
- **Trigger:** `ORGANIC_REV_CAGR ≥ 8%` AND `INORGANIC_REV_SHARE < 20%`
- **Severity:** POSITIVE  
- **Finding:** Strong Organic Growth  
- **Explanation:** Growth is primarily organic at a healthy rate.  
- **Suggested Analyst Action:** None.

#### GR032 — Acquisition Masking Decline
- **Trigger:** `REV_CAGR > 0` AND `ORGANIC_REV_CAGR < 0` (when organic series available)
- **Severity:** CRITICAL  
- **Finding:** Acquisitions Masking Organic Decline  
- **Explanation:** Reported growth hides contracting organic demand.  
- **Suggested Analyst Action:** Treat organic decline as primary growth truth; normalize.

---

### Rule → output mapping

| Rule severity | Typical `findings[].severity` | Also emit |
|---|---|---|
| POSITIVE | `positive` | `opportunities` |
| INFO | `info` | optional finding only |
| WARNING | `warning` | `risks` |
| CRITICAL | `critical` | `risks` |

Every finding **must** include evidence (metric, value, period, source/provenance/confidence when available). Findings without evidence are invalid per `FINANCIAL_ANALYSIS_SPEC.md`.

---

## 6. Scoring

### 6.1 Score definition

- **Name:** Growth Score  
- **Range:** 0–100  
- **Interpretation bands:** same as module score bands in `FINANCIAL_ANALYSIS_SPEC.md` (90–100 Exceptional … Below 40 Poor)  
- **Roll-up:** feeds Business Quality at **15%** weight (`SCORING_SYSTEM.md`)  
- **Determinism:** identical inputs ⇒ identical score

### 6.2 Component weights (must total 100%)

These match `SCORING_SYSTEM.md` exactly:

| Component code | Metric used | Weight | Justification |
|---|---|---|---|
| `REVENUE_CAGR` | `REV_CAGR` mapped to 0–100 | **30%** | Primary measure of franchise expansion; most comparable across business models |
| `EPS_CAGR` | `EPS_CAGR` mapped to 0–100 | **25%** | Captures whether growth reaches shareholders after costs and share count |
| `FCF_CAGR` | `FCF_CAGR` mapped to 0–100 | **25%** | Enforces cash reality; prevents rewarding low-quality accrual growth |
| `GROWTH_STABILITY` | `GROWTH_STABILITY` × 100 | **10%** | Durability / forecastability of the growth stream |
| `ORGANIC_GROWTH` | Organic score from `ORGANIC_REV_CAGR` + inorganic penalty | **10%** | Protects against acquisition-inflated “growth” |
| **Total** |  | **100%** |  |

No other component may be added to the Growth Score without updating `docs/SCORING_SYSTEM.md` first.

### 6.3 Raw → 0–100 component maps (deterministic)

Piecewise-linear maps (implementation detail to follow this spec):

**Revenue CAGR → score**

| REV_CAGR | Component score |
|---|---|
| ≤ −10% | 5 |
| −5% | 20 |
| 0% | 40 |
| 3% (≈ inflation) | 50 |
| 8% | 70 |
| 15% | 90 |
| ≥ 25% | 98 |

Hypergrowth above 30% does **not** score above 98 automatically; GR025 still warns on sustainability (score stays high but risks escalate).

**EPS CAGR → score**

| EPS_CAGR | Component score |
|---|---|
| ≤ −15% | 5 |
| −5% | 25 |
| 0% | 45 |
| 8% | 70 |
| 15% | 85 |
| 20% | 92 |
| ≥ 30% | 98 |

**FCF CAGR → score**

| FCF_CAGR | Component score |
|---|---|
| ≤ −15% | 5 |
| −5% | 25 |
| 0% | 45 |
| 8% | 70 |
| 15% | 90 |
| ≥ 25% | 98 |

Additional hard caps:
- If latest FCF < 0 and `REV_CAGR > 0`, FCF component score **capped at 35** (cash-consuming expansion).
- If FCF series missing, component unavailable (see renormalization).

**Growth Stability → score**

`score = GROWTH_STABILITY × 100` (already 0–1).  
If fewer than 3 YoY observations, component unavailable.

**Organic Growth → score**

1. Map `ORGANIC_REV_CAGR` with the same anchors as Revenue CAGR.  
2. Apply penalty: subtract `min(40, INORGANIC_REV_SHARE × 100)` points when inorganic share is known.  
3. If no organic/acquisition metadata exists: use reported `REV_CAGR` map with **confidence penalty** (not a silent invention of organic CAGR), and mark `ORGANIC_DATA_AVAILABLE = 0`.

### 6.4 Renormalization & missing data

If a component is unavailable:

1. Remove its weight.  
2. Renormalize remaining weights to 100%.  
3. Reduce module confidence (see §6.6).  
4. Record effective weights in `coverage.effective_weights`.

If `revenue` history is insufficient for any CAGR (`< 3` points): module status = `skipped` or `ok` with `score = null` only if literally no growth metric can be computed; prefer `ok` with partial score when revenue CAGR exists.

### 6.5 Supporting metrics vs score

`OI_CAGR`, `BV_CAGR`, `SHARE_COUNT_CAGR`, acceleration, spreads, etc. inform **rules / risks / opportunities** and evidence.  
They do **not** receive explicit Growth Score weights unless `SCORING_SYSTEM.md` is revised.

### 6.6 Confidence (qualifies the score; never changes it)

Confidence ∈ [0, 1], independent of whether growth is “good” or “bad”.

Increase confidence when:
- ≥5 years audited revenue, EPS, and FCF history  
- Multiple sources agree (high point confidence)  
- Organic/acquisition overlays present  
- Low missing-component ratio  

Decrease confidence when:
- Short history (GR030)  
- Missing EPS or FCF components  
- High growth volatility  
- COVID/base-effect or discontinued-ops flags  
- Heavy analyst normalization pending  

Confidence must be emitted on `AnalysisModuleResult.confidence` and must not alter `score`.

---

## 7. Risks

Machine-readable risk codes (also linked to rules):

| Risk code | Signal |
|---|---|
| `ACQUISITION_DRIVEN_GROWTH` | GR007 / GR032 |
| `LOW_QUALITY_GROWTH` | GR005 / GR015 |
| `SHAREHOLDER_DILUTION` | GR006 / GR017 |
| `REVENUE_STAGNATION` | GR012 |
| `STRUCTURAL_REVENUE_DECLINE` | GR013 |
| `CASH_CONSUMING_EXPANSION` | GR011 |
| `GROWTH_DECELERATION` | GR022 |
| `UNSTABLE_GROWTH` | GR020 / GR024 |
| `HYPERGROWTH_FADE_RISK` | GR025 |
| `BASE_EFFECT_DISTORTION` | GR026 / GR027 / GR028 |
| `INSUFFICIENT_HISTORY` | GR030 |
| `ORGANIC_DECLINE_MASKED` | GR032 |

Risks appear in `AnalysisModuleResult.risks` with evidence and related finding IDs.

---

## 8. Opportunities

| Opportunity code | Signal |
|---|---|
| `EXCEPTIONAL_REVENUE_GROWTH` | GR001 |
| `HEALTHY_REVENUE_GROWTH` | GR002 |
| `STRONG_ORGANIC_GROWTH` | GR031 |
| `OPERATING_LEVERAGE_IMPROVING` | GR004 |
| `EXCEPTIONAL_EARNINGS_GROWTH` | GR008 |
| `EXCEPTIONAL_FCF_GROWTH` | GR010 |
| `CASH_BACKED_GROWTH` | GR014 |
| `ANTI_DILUTIVE_EXPANSION` | GR016 |
| `STABLE_GROWTH` | GR019 |
| `PERSISTENT_GROWTH` | GR021 |
| `GROWTH_ACCELERATION` | GR023 |
| `BOOK_VALUE_COMPOUNDING` | GR018 |

Opportunities appear in `AnalysisModuleResult.opportunities` with evidence.

---

## 9. Analyst Adjustments

Adjustments propose changes to **inputs used for growth analysis**.  
They never silently overwrite reported financial statements (`PROJECT.md` / Playbook).  
Each adjustment must record original value, proposed value, reason, impact, analyst, timestamp (Scoring System override requirements).

| Adjustment action code | Purpose | Typical targets |
|---|---|---|
| `normalize_acquisition_growth` | Remove inorganic revenue to estimate organic CAGR | `metadata.organic_revenue_series` / acquired revenue overlays |
| `separate_organic_growth` | Force organic vs reported dual metrics | organic overlays |
| `remove_one_time_revenue` | Strip one-time spikes (GR027) | affected revenue periods |
| `normalize_covid_effects` | Restate FY2020–FY2022 base effects (GR026) | revenue / EPS / FCF windows |
| `adjust_discontinued_operations` | Restate continuing-ops growth (GR028) | income/FCF series overlays |
| `normalize_share_count` | Adjust for mergers / reverse splits comparability | share_count_series |
| `exclude_hypergrowth_base_year` | Avoid misleading CAGR from tiny base | CAGR window start |
| `use_per_share_growth` | Emphasize diluted per-share growth when dilution material | derived per-share series |
| `request_more_data` | Ask for longer history or acquisition disclosure | coverage gaps |

Allowed adjustment actions must remain within the existing `AnalystAdjustmentProposal` contract (extend action enum only if absolutely necessary and documented in the financial analysis spec first).

---

## 10. Unit Test Scenarios

Each scenario should build a `CompanyFinancialModel` fixture (in future implementation tests) with ≥5 years of series unless noted. Assert score bands, key metrics, and specific rule hits.

### 10.1 Excellent growth — “Compounder Co” (e.g., high-quality SaaS / consumer franchise)

- Revenue CAGR ~12%, EPS CAGR ~15%, FCF CAGR ~14%, organic share high, stability high, share count flat/down  
- **Expect:** Growth Score **80–92**  
- **Rules:** GR002 or GR001 borderline, GR004, GR014, GR019, GR031  
- **Risks:** minimal  

### 10.2 Average growth — “Mature Industrial Inc”

- Revenue CAGR ~4%, EPS CAGR ~5%, FCF CAGR ~4%, moderate stability  
- **Expect:** Growth Score **55–70**  
- **Rules:** possibly GR003 if below inflation; else few positives  
- **Risks:** limited  

### 10.3 Deteriorating growth — “Fading Retailer”

- Revenue CAGR ~−6%, EPS CAGR ~−10%, FCF CAGR ~−8%, deceleration negative  
- **Expect:** Growth Score **15–40**  
- **Rules:** GR013, GR009, GR022  
- **Risks:** structural decline, deceleration  

### 10.4 Hypergrowth — “Blitzscale AI Ltd”

- Revenue CAGR ~40%, EPS still negative or sparse, FCF negative, high volatility  
- **Expect:** Revenue component very high but FCF/EPS weak ⇒ overall **45–70** depending on missing-component renormalization; **not** an automatic 95  
- **Rules:** GR001/GR025, GR011, GR020  
- **Risks:** hypergrowth fade, cash-consuming expansion  

### 10.5 Acquisition-driven growth — “Serial Acquirer PLC”

- Reported revenue CAGR ~18%, organic CAGR ~1%, inorganic share ~60%, FCF flat  
- **Expect:** Reported revenue looks strong; organic component weak ⇒ Growth Score **50–75** with organic penalty  
- **Rules:** GR007, GR032 if organic negative, GR001 may still fire on reported CAGR — evidence must show acquisition context  
- **Adjustments:** `normalize_acquisition_growth`, `separate_organic_growth`  

### 10.6 Declining business — “Legacy Hardware Co”

- Revenue CAGR ~−12%, dilution rising, FCF negative 3 of 5 years, persistence low  
- **Expect:** Growth Score **< 35**  
- **Rules:** GR013, GR006, GR011/GR005, GR030 if history short  
- **Risks:** structural decline, dilution, cash burn  

### 10.7 Additional fixtures (recommended)

| Fixture | Intent |
|---|---|
| `cash_backed_moderate` | GR014 + mid score |
| `dilution_trap` | Revenue up, revenue/share down (GR017) |
| `covid_base_effect` | GR026 triggers; score stable but confidence lower |
| `insufficient_history` | 2 revenue points → GR030; skipped/partial |
| `boom_bust_cyclical` | GR024; stability component low |

For each fixture, tests must assert:
1. Deterministic score equality on rerun  
2. Weights used sum to 1.0 after renormalization  
3. Every finding has evidence  
4. No recommendation language in module outputs  
5. No Excel/cell access  

---

## 11. Output Contract (unchanged architecture)

`AnalysisModuleResult` fields to populate:

| Field | Growth Module content |
|---|---|
| `module_name` | `"growth"` |
| `score` | Growth Score 0–100 or `null` if impossible |
| `confidence` | 0–1 reliability qualifier |
| `metrics` | Section 3 codes |
| `findings` | Triggered GR rules |
| `risks` | Section 7 |
| `opportunities` | Section 8 |
| `evidence` | Aggregated metric/rule evidence |
| `analyst_adjustments` | Section 9 proposals |
| `component_scores` | Five weighted components with raw values |
| `status` | `ok` / `skipped` / `error` |
| `coverage` | History lengths, effective weights, organic data flag |

---

## 12. Open Items for Review (before implementation)

1. Confirm default inflation rate **3%** for GR003 when metadata absent.  
2. Confirm organic growth penalty formula when acquisition overlays are missing (confidence penalty vs neutral organic component).  
3. Confirm whether hypergrowth revenue map should soft-cap below 98 (currently 98 at ≥25%).  
4. Confirm share-count history via `metadata["share_count_series"]` is acceptable until a first-class series is added **through a future spec update** (not in this change).  
5. Decide if GR001 should be suppressed when GR007 fires (recommended: **do not suppress** — both findings can coexist; organic score handles weighting).

---

## 13. Implementation Gate

Accepted. Implementation checklist:

1. Mirror net-new rules into `docs/RULE_LIBRARY.md` — done (GR001–GR032)
2. Implement module following Profitability’s patterns — `backend/analysis_engine/modules/growth.py`
3. Add unit tests for Section 10 scenarios — `backend/tests/test_growth_module.py`

No other architectural changes are authorized by this specification.
