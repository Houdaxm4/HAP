# HAP Methodology Audit

Version: 5.2  
Status: Documentation audit only — **no code, scoring, or weight changes**

Sources reviewed:

- `docs/INVESTMENT_NETHODOLOGY.md` (Investment Methodology)
- `docs/RULE_LIBRARY.md`
- `docs/SCORING_SYSTEM.md`
- `docs/HAP_ANALYST_PLAYBOOK.md`
- Module specs under `docs/modules/`
- Module / scoring / rule implementations under `backend/` (inspected for fidelity to the documented methodology; not modified)

---

## 1. Executive summary

HAP’s stated philosophy is coherent and investor-sound:

1. Separate **business quality** from **price attractiveness**.
2. Prefer **economic reality** (ROIC vs WACC, cash, capital allocation) over single ratios.
3. Require **evidence-backed**, deterministic findings before recommendations.
4. Compare opportunities to **peers and the index** (documented intent).

The implemented analytical stack largely follows that philosophy for Business Quality (six modules + aggregator) and Investment Attractiveness (valuation + expected return + aggregator + recommendation matrix).

The audit finds **three structural gaps** between the written investment thesis and the operating methodology:

| Gap | Methodology intent | Operating reality |
|-----|--------------------|-------------------|
| **Financial Strength** | Separate score in `SCORING_SYSTEM.md` | No dedicated aggregator; resilience mostly inside Balance Sheet |
| **Peer / moat / index as first-class BQ evidence** | Methodology Stage 2 + Rule Library MOAT/PEER/IDX | Peer/index largely live in Expected Return overlays; moat largely in Outlook metadata |
| **Four IA conceptual weights** | Intrinsic value / ER / MOS / relative (35/30/20/15) | Rolled up as Valuation **70%** + Expected Return **30%** (MOS/relative folded into valuation score) |

None of these are “bugs” for this sprint; they are methodology consistency items for future design review. This document does **not** propose weight or score changes.

Cross-cutting methodological traits:

- **Industry-agnostic absolute thresholds** (margins, leverage, CAGRs, WACC bands, GDP, S&P hurdle).
- **Missing-data renormalization** (available components absorb skipped weight) — correct for robustness, but can silently change what a score means.
- **Metadata dependence** for organic growth, share history, peers, outlook, maintenance CapEx — without overlays, proxies or skips dominate.
- **FCF / invested-capital framing** — strong for industrials and many corporates; weaker for banks, insurers, some REITs, and intentional early-stage cash burn.

---

## 2. Cross-cutting methodology assumptions

These assumptions recur across modules and should be treated as part of the investment framework:

| Assumption | Typical default / practice |
|------------|----------------------------|
| Analysis window | Prefer 10 years; practical scoring often uses ~5-year windows |
| Currency / reporting | Single reporting currency (default USD framing) |
| Cost of capital | Explicit WACC when present; capital allocation may assume ~8% if missing |
| Tax for NOPAT | Derived or ~25% proxy |
| Inflation (growth rules) | ~3% when not supplied |
| Terminal / GDP anchor (valuation) | ~4% GDP-style cap on terminal growth reasonableness |
| Holding period (expected return) | ~5 years |
| Index opportunity cost | ~8% S&P expected return unless overlay supplied |
| Forecast horizon (DCF) | ~5 years |
| Maintenance CapEx | Explicit overlay, else total CapEx as proxy |
| Score scale | 0–100; confidence separate and does not change the score |
| Renormalization | Missing components redistribute weight among available ones |

---

## 3. Module audits

Each module is reviewed against the seven required lenses. “Margins” is included because it appears in the module surface even though it is scaffold-only.

---

### 3.1 Profitability

**Business question:** Is the company economically profitable and durable (especially ROIC vs WACC), independent of price?

#### Assumptions

- ROIC is the primary capital-efficiency signal; operating/net margins and ROE/ROA are secondary.
- ROIC below WACC is treated as economic value destruction (critical finding path).
- Margin stability over a multi-year window is a quality signal.
- Tax rate for NOPAT can be derived or defaulted.
- Absolute margin / ROIC bands (e.g. ROIC &gt;20% “exceptional”) are universal.

#### Strengths

- Aligns with Playbook Principles 6 and 3 (returns on capital; economic reality).
- Explicit WACC comparison operationalizes Methodology Stage 2.
- Stability component resists single-year spikes.
- Heavy ROIC weight (40%) matches HAP’s stated philosophy better than earnings-only screens.

#### Blind spots

- Gross margin and pricing-power structure are weakly represented in the score (often heuristic/adjustment only).
- Segment / geographic mix ROIC not modeled.
- One-time items and non-GAAP noise handled mainly via analyst adjustments, not automatic normalization.
- No industry-relative profitability (a 8% operating margin can be excellent or poor by sector).

#### Metrics that may be missing

- Gross margin (scored)
- NOPAT / invested capital definition transparency (lease-adjusted IC, R&D capital, goodwill)
- Through-cycle normalized EBIT / margins
- Accrual quality beyond cash-flow module cross-checks
- Peer-relative ROIC / margin spreads (Rule Library MOAT/PEER intent)

#### Potential biases

- Favors capital-light models with high reported ROIC (and can overstate “moat” without peer context).
- ROE can reward leverage; weight is low but non-zero.
- Absolute high-margin bias may underrate efficient low-margin compounders (grocery, distribution).
- Tax default can distort NOPAT for unusual tax regimes.

#### Edge cases

- Negative equity / negative invested capital → ROE/ROIC meaningless or unstable.
- Cyclical peak margins scored as structural excellence.
- Turnarounds with one good year inside a short window.
- High goodwill from acquisitions inflating or distorting invested capital.

#### Industries where methodology may not generalize well

- Banks and insurers (invested capital / ROIC definitions differ)
- REITs (FFO/AFFO economics)
- Commodity producers (margin/ROIC cycle-dominated)
- Early-stage growth firms with intentionally deferred profitability

---

### 3.2 Growth

**Business question:** Does the company grow in a durable, economically valuable way (cash-backed, not dilution/acquisition theater)?

#### Assumptions

- Multi-year CAGRs on revenue, EPS, and FCF are the core growth evidence.
- Growth quality matters as much as growth rate (cash conversion of growth, organic vs inorganic, dilution).
- Inflation is a floor for “real” growth judgment when supplied or defaulted.
- Organic growth can fall back to reported revenue growth when organic series is absent (with confidence penalty).

#### Strengths

- Strong alignment with Playbook Principle 7 (growth only if value-creating).
- Rich rule set for low-quality growth (FCF decline with revenue growth, dilution exceeding top-line, acquisition masking).
- Stability / volatility / acceleration diagnostics support humility about extrapolating CAGRs.
- Separates growth from valuation (BQ only) — correct architectural philosophy.

#### Blind spots

- Without organic/acquisition overlays, “organic” component can proxy reported growth.
- Share-count history often metadata-dependent.
- Nominal CAGR in high-inflation or currency-volatile settings can mislead.
- Unit economics / cohort retention (SaaS) not first-class.

#### Metrics that may be missing

- Organic revenue as a first-class series (not only metadata)
- Same-store / volume vs price split
- Backlog / RPO for contracted growth businesses
- Per-share revenue/FCF as primary scored series (rules exist; scoring still CAGR-centric)
- Industry-relative growth (PEER002 intent)

#### Potential biases

- Absolute CAGR bands (e.g. &gt;15% exceptional) favor high-growth sectors over mature cash compounders.
- EPS CAGR can be flattered by buybacks or tax items (rules warn; score may still benefit).
- Hypergrowth warnings exist, but high CAGRs still score well if other components cooperate.

#### Edge cases

- Negative base years and sign-change CAGRs.
- COVID / base-effect distortions (rules flag; scoring may still use raw series).
- Discontinued operations and restatements.
- Fewer than three revenue points → insufficient history path.

#### Industries where methodology may not generalize well

- Banks (loan growth ≠ revenue quality)
- Insurers (premium growth vs underwriting cycle)
- Cyclicals and commodities (peak-to-trough CAGR artifacts)
- Platform / marketplace businesses where GMV ≠ recognized revenue quality

---

### 3.3 Margins (scaffold)

**Business question (intended):** What is the quality and trajectory of the margin structure?

#### Assumptions

- Documented as a distinct analytical concern in architecture / module list.
- In practice, margin content is largely embedded in **Profitability** (and Outlook guidance fields).

#### Strengths

- Avoids double-counting if intentionally deferred (profitability already weights margins).

#### Blind spots

- No dedicated margin-structure module (gross vs operating vs contribution, mix shift, operating leverage decomposition).
- Reviewers may expect a margins module result and instead see `skipped` / not implemented.

#### Metrics that may be missing

- Gross, contribution, and incremental margins as a scored family
- Margin bridge (price/volume/mix/cost)
- Peer margin percentiles

#### Potential biases

- N/A as standalone; bias transfers into Profitability’s absolute margin thresholds.

#### Edge cases

- Companies where gross margin is the primary moat signal (brand / IP) but operating margin is masked by reinvestment.

#### Industries where methodology may not generalize well

- Retail and distribution (thin margins, high turnover)
- Software (high gross, high S&M investment)
- Manufacturing with large mix shifts

**Audit note:** Treat Margins as a **methodology documentation / coverage gap**, not an independent pillar today.

---

### 3.4 Cash flow

**Business question:** Does the firm convert earnings into durable free cash / owner earnings?

#### Assumptions

- Cash is harder to manipulate than earnings (Playbook Principle 5).
- FCF, cash conversion (OCF vs earnings), owner earnings, and FCF stability capture cash quality.
- Owner earnings may use maintenance CapEx overlay; otherwise total CapEx is a conservative proxy.
- FCF scoring often uses margin-style normalization (size-aware ratios), not raw dollar levels alone.

#### Strengths

- Directly implements Methodology Stage 1 cash questions and Playbook cash primacy.
- Persistent cash burn is treated as critical.
- Owner-earnings lens supports economic earnings vs accounting NI.

#### Blind spots

- Working-capital quality (receivables, inventory, payables days) is thinner than OCF/NI conversion.
- Growth CapEx vs maintenance CapEx distinction depends on overlays.
- Cash flow timing and one-time working-capital releases can inflate conversion.

#### Metrics that may be missing

- Cash conversion cycle / WC days
- Maintenance vs growth CapEx as first-class series
- SBC-adjusted FCF / diluted economic cash
- Interest and tax cash vs accrual splits
- Lease principal payments in “true FCF” for IFRS16/US GAAP lease regimes

#### Potential biases

- CapEx-heavy compounding industries (industrials, telecom, energy) can look weaker than asset-light peers even when ROIC is excellent.
- Rewards FCF-margin richness over reinvestment that is value-accretive but cash-consuming near term.

#### Edge cases

- Negative FCF during deliberate high-ROIC expansion.
- Financial companies where “FCF” is not the right economic cash concept.
- Large one-time asset sales boosting OCF/FCF.

#### Industries where methodology may not generalize well

- Banks, insurers, brokers
- REITs (AFFO frameworks)
- High-growth SaaS (SBC and capitalized software nuances)
- Utilities and infrastructure (regulated CapEx cycles)

---

### 3.5 Balance sheet

**Business question:** Is the balance sheet resilient enough to survive stress and preserve strategic flexibility?

#### Assumptions

- Liquidity (current ratio), leverage (Debt/EBITDA), interest coverage, net cash, and WC trend summarize strength.
- Absolute thresholds (e.g. current &gt;2, Debt/EBITDA &gt;4, coverage &lt;3) are meaningful across companies.
- Net cash is a strong positive flexibility signal.

#### Strengths

- Aligns with Playbook Principle 9 (financial strength).
- Multi-factor resilience view (liquidity + leverage + coverage).
- Critical leverage / coverage findings support Avoid-type discipline upstream of recommendations.

#### Blind spots

- **Financial Strength** as a separate score in `SCORING_SYSTEM.md` is not a distinct synthesis layer — balance sheet carries most of that burden inside BQ.
- Off-balance-sheet obligations, pensions, litigation, minimum cash needs are limited.
- Debt maturity profile weight exists in Financial Strength docs but is thin in practice.
- Liquidity ratios misread businesses with structurally negative working capital.

#### Metrics that may be missing

- Debt maturity ladder / refinancing wall
- Lease-adjusted leverage
- Contingent liabilities / pension underfunding
- Credit rating / CDS / interest-rate reset risk
- Liquidity runway (months of cash burn) for non-profitable firms
- Regulatory capital ratios for financials

#### Potential biases

- Prefers fortress net-cash corporates over optimally levered firms in stable cash businesses.
- Punishes retailers and platforms with negative WC by design if current-ratio logic dominates.
- EBITDA leverage favors EBITDA-positive firms; early losses look “infinite leverage.”

#### Edge cases

- Negative EBITDA / EBIT → coverage and leverage undefined or explosive.
- Going-concern stress with adequate trailing ratios.
- Holding companies with structural debt at HoldCo vs OpCo.

#### Industries where methodology may not generalize well

- Banks (asset-liability, capital ratios)
- Insurers (float, reserving)
- Utilities / infrastructure (high leverage, regulated)
- REITs (property-level LTV, AFFO coverage)
- Retail / airlines (industry-specific liquidity patterns)

---

### 3.6 Capital allocation

**Business question:** Does management allocate capital in ways that raise ROIC and per-share intrinsic value?

#### Assumptions

- ROIC trend is the primary allocation quality signal.
- Buybacks, dividends, reinvestment, and acquisitions are the main deployment channels.
- Buybacks are value-creating primarily when executed below intrinsic value (often metadata-gated).
- Missing WACC can be approximated (e.g. ~8%) for spread interpretation.

#### Strengths

- Excellent alignment with Playbook Principle 4.
- Couples payout policy to ROIC outcomes (not yield-chasing alone).
- Flags acquisition-driven empire building and debt-funded buybacks.

#### Blind spots

- Intrinsic-value timing of buybacks is hard without reliable FV history.
- R&D / intangible reinvestment quality under-captured if CapEx-centric.
- Dividend “friendliness” can be scored positively even when suboptimal vs reinvestment.
- Without share-count and acquisition overlays, several components weaken or skip.

#### Metrics that may be missing

- Buyback price vs trailing/fair value time series
- Acquisition ROIC / IRR post-deal
- Internal reinvestment rate vs marginal ROIC
- Dilution from SBC net of buybacks
- Project-level capital discipline indicators

#### Potential biases

- Cultural bias toward buyback-heavy US large caps vs dividend or reinvestment cultures.
- May under-appreciate high-ROIC firms that retain and reinvest rather than repurchase.
- Acquisition quality difficult without deal metadata → silent neutrality or skip.

#### Edge cases

- Controlled companies / dual class where “shareholder friendly” is ambiguous.
- Spinoffs and major portfolio reshaping.
- Financials where “buybacks” interact with capital regulation.

#### Industries where methodology may not generalize well

- Conglomerates and serial acquirers (deal quality dominates)
- VC-style growth firms (dilution is the funding model)
- Regulated utilities (capex mandates)
- Family-controlled firms with atypical payout preferences

---

### 3.7 Business outlook

**Business question:** Are future prospects constructive enough to support durable returns (industry, competitive position, guidance, risks)?

#### Assumptions

- Forward outlook is inherently uncertain → capped contribution to BQ (10%).
- Outlook inputs are primarily structured analyst/metadata fields, not auto-extracted filings.
- Competitive position / moat can be scored from provided overlays.
- Confidence should remain tempered even when outlook scores are strong.

#### Strengths

- Matches Methodology Stage 4 intent and Playbook humility (Principle 15).
- Explicitly limited weight reduces forecast worship.
- Separates structural risk and guidance from historical score inflation.

#### Blind spots

- **Not statement-derived** — if metadata is empty, module skips and BQ renormalizes without forward view.
- Moat evidence in Rule Library (10-year peer ROIC, etc.) is not fully automated here.
- Industry trend scores can be absolute rather than relative to cost of capital or peers.
- Narrative risks (regulation, disruption) depend on human tagging quality.

#### Metrics that may be missing

- Filing-derived guidance changes (automated)
- Market share time series
- Product pipeline / cohort metrics
- Scenario probabilities (bull/base/bear) linked to valuation overlays
- Crowding / positioning risk

#### Potential biases

- Optimistic analyst overlays can lift BQ without new hard evidence (mitigated by 10% weight and confidence caps).
- Silent skip when overlays missing can make historically strong firms look “complete” without Stage 4.

#### Edge cases

- Turnarounds where history is poor but outlook is the whole thesis.
- Disruptors where historical ROIC is low by design.
- Highly regulated regime shifts.

#### Industries where methodology may not generalize well

- Deep tech / biotech (binary pipelines)
- Crypto / speculative platforms
- Policy-sensitive sectors (energy, healthcare reimbursement)
- Hyper-competitive retail with thin forward visibility

---

### 3.8 Valuation (Enterprise Valuation)

**Business question:** What is the business worth, and what margin of safety exists versus today’s price?

#### Assumptions

- Intrinsic value is estimated from multiple methods (DCF, owner earnings, peer/historical multiples) then synthesized.
- DCF often grows an FCF path with fade assumptions; terminal value uses Gordon growth with WACC &gt; g discipline.
- Margin of safety is central to valuation scoring.
- Workbook valuation is compared, never overwritten.
- Method disagreement reduces confidence / convergence score.
- GDP-like terminal growth caps and WACC reasonableness bands constrain exuberance.

#### Strengths

- Directly implements Methodology Stage 3.
- Multi-method synthesis and reverse-DCF style checks support explainability.
- Clear separation from Buy/Sell decisions (recommendation is downstream).
- Scenario bands encourage humility.

#### Blind spots

- Highly **FCF-path dependent**; limited full three-statement forecast model (revenue → margins → reinvestment → FCF).
- Peer multiples depend on supplied peer sets — otherwise thin relative valuation.
- Accounting distortions (leases, SBC, capitalized software) can flow into FCF without automatic repair.
- Cyclical normalization depends on flags/overlays.

#### Metrics that may be missing

- Explicit revenue and margin forecast triangulation
- Residual income / P/B for financials
- Sum-of-the-parts for conglomerates
- Optionality / NOI frameworks for REITs
- Probability-weighted scenario FV (beyond simple bear/base/bull adjustments)

#### Potential biases

- Gordon-growth + GDP anchor bias against high-growth compounders (fade) and for mature FCF farms.
- WACC band assumptions reflect equity-market heuristics, not firm-specific CAPM always.
- MOS-heavy scoring can dominate “valuation quality” even when methods are fragile.
- Asset-light high reinvestment firms with low near-term FCF look optically expensive/cheap incorrectly.

#### Edge cases

- WACC ≤ terminal growth
- Negative or near-zero FCF base year
- Single method only → synthesis fragile
- Distressed equity option-value situations
- Share count changes between FV and market cap bridge

#### Industries where methodology may not generalize well

- Banks and insurers
- REITs and asset managers
- Pre-profit growth companies
- Commodity cyclicals without mid-cycle normalization
- Holding companies / NPVs of projects

---

### 3.9 Expected return

**Business question:** What annualized shareholder return does today’s price imply, and is it superior to alternatives (index/peers)?

#### Assumptions

- Expected CAGR ≈ growth + dividend yield + buyback yield + valuation reversion (+ optional multiple expansion).
- Valuation reversion uses fair value vs price over a holding period.
- Index hurdle (~8% unless overlay) is the opportunity-cost benchmark.
- Growth contributions are capped to limit absurd extrapolation.
- Expected return informs IA, not BQ.

#### Strengths

- Operationalizes Methodology “beat the S&P / alternatives” and Playbook Principle 11.
- Links price to FV via reversion — coherent with MOS philosophy.
- Explicit dividend and buyback yield channels match total-shareholder-return thinking.

#### Blind spots

- **Additive decomposition can double-count** (growth embedded in FV path and again as a CAGR component).
- Historical growth extrapolation is not a forecast engine.
- Peer expected-return comparison depends on overlays (PEER003/IDX intent partially covered).
- Multiple expansion as a scored positive can reward multiple speculation if enabled.

#### Metrics that may be missing

- Risk-adjusted expected return (Sharpe / downside / drawdown)
- Inflation-real returns
- Currency-hedged returns for ADRs / multi-currency cash flows
- Explicit fade path for growth in the ER identity
- Probability of permanent capital loss

#### Potential biases

- Favors cheapness (reversion) and yield (div/buyback) mechanically.
- Fixed index hurdle may be wrong in regime shifts (rate world).
- Buyback yield estimated from share change can misread issuance cycles.

#### Edge cases

- FV &lt;&lt; 0 or nonsensical FV
- Price missing → cannot score market-relative ER
- Very short or very long holding period overlays
- Negative equity / restructuring stubs

#### Industries where methodology may not generalize well

- Deep cyclicals (mid-cycle vs spot growth)
- Financials (earnings yield frameworks differ)
- High-dilution growth firms (buyback yield meaningless)
- Markets where index composition differs from S&P 500 assumption (non-US)

---

### 3.10 Recommendation (decision layer)

**Business question:** Given Business Quality and Investment Attractiveness, what action label follows?

#### Assumptions

- Recommendations are a **deterministic matrix** on BQ and IA scores — not a new financial model.
- Quality floor: weak businesses should not become buys merely because they are cheap.
- Excellent businesses can be Watch / wait-for-better-price when IA is insufficient.
- Insufficient data is a first-class outcome when aggregators lack scores.
- Confidence qualifies reliability; it does not rewrite the matrix.

#### Strengths

- Cleanly enforces Playbook Principle 1 and Scoring System separation of quality vs price.
- Avoid-on-weak-quality discipline matches Methodology “Avoid” philosophy.
- Explainability path via matrix + supporting findings.

#### Blind spots

- Documented labels (e.g. Speculative, Hold bands) may not perfectly match operating labels (e.g. Watch-family outcomes for cheap/low-quality).
- Four methodology pillars (Fundamentals, Economic Value Creation, Valuation, Outlook) are **compressed** into BQ + IA; Outlook is only 10% of BQ; Financial Strength is not independent.
- No explicit “prefer index” recommendation label — index preference surfaces via ER findings/warnings.

#### Metrics that may be missing

- Explicit opportunity-cost decision output (“Index preferred”)
- Position-sizing / confidence-tiered actions
- Separate “Speculative” action when cheap + low quality (docs mention; operating path may fold into Watch)

#### Potential biases

- Cliff effects at score thresholds (59 vs 60, 49 vs 50).
- Speculative cheapness may be overly suppressed (good risk control) or under-labeled (communication gap).
- Strong Buy rarity depends on simultaneous elite BQ and IA — conservative bias (generally desirable).

#### Edge cases

- High BQ, mid IA → Watch / wait-for-better-price (correct philosophically; easy to misread as engine failure)
- Low BQ, high IA → not a Buy (correct; needs clear reviewer language)
- One aggregator missing → Insufficient Data even if many modules ran

#### Industries where methodology may not generalize well

- Same as upstream modules: if BQ/IA are systematically mis-scaled for banks/REITs/cyclicals, the matrix will be consistently wrong in those sectors even when internally coherent.

---

## 4. Aggregation methodology review

### 4.1 Business Quality aggregator

**Design:** Weighted roll-up of profitability, growth, cash flow, balance sheet, capital allocation, business outlook (25/15/20/15/15/10). Skipped modules renormalize; low confidence is tracked and can reduce aggregate confidence. Classification bands map scores to business-quality labels. No recalculation of financial metrics; no direct Rule Library BQ001–BQ003 evaluation at aggregator level.

#### Assumptions

- Module scores are commensurate on a 0–100 scale.
- Skipping a module should not invent a substitute score — redistribute weight.
- Outlook deserves less weight because it is forward-looking and softer.

#### Strengths

- Faithful to `SCORING_SYSTEM.md` BQ weights.
- Preserves module explainability (contributions retained).
- Confidence separation matches Scoring System doctrine.

#### Blind spots

- Renormalization changes economic meaning: a firm missing outlook + capital allocation is scored on a different mix than a full-coverage peer.
- Double-counting across modules (margins/ROIC appear in profitability and again via capital allocation / cash quality themes).
- Peer-relative and moat rules in the Rule Library are not a BQ aggregation input.
- Classification may collapse finer doc bands (e.g. below-average vs poor) into broader weak labels depending on implementation bands.

#### Potential biases

- Historically complete, FCF-rich corporates get fuller coverage and more stable BQ than metadata-poor names.
- Modules with easier data availability can dominate after renormalization.

#### Edge cases

- All soft modules skipped → BQ becomes a pure historical profitability/cash/leverage machine.
- One failed critical module still allows a high BQ if others are strong (depends on error vs skip handling).

---

### 4.2 Investment Attractiveness aggregator

**Design:** Valuation **70%** + Expected Return **30%**, mapping the conceptual IA weights (intrinsic + MOS + relative ≈ 70; expected return 30). Classification labels describe opportunity attractiveness, not the final recommendation action.

#### Assumptions

- Valuation module score already embeds MOS and relative/reasonableness components.
- Expected return is complementary but should not dominate price discipline.
- Same renormalization / confidence philosophy as BQ.

#### Strengths

- Keeps IA price-centric and quality-agnostic (as documented).
- Avoids a third parallel valuation engine at aggregation time.
- Clear two-module explainability for reviewers.

#### Blind spots

- Conceptual four-way IA weights are not independently observable in the aggregator — reviewers must inspect valuation internals for MOS/relative.
- Correlation between valuation score and ER (both use FV/price) can **amplify cheapness** twice.
- Relative valuation still weak if peer metadata missing — yet IA can look “complete.”

#### Potential biases

- Cheapness cascade: high MOS → high valuation score → high reversion ER → high IA.
- Yield-heavy ER can buoy IA when MOS is only mediocre.

#### Edge cases

- Valuation ok, ER skipped (or reverse) → 100% weight on one module after renormalization.
- High IA with low-confidence valuation methods still can pass matrix gates if scores clear thresholds.

---

### 4.3 Recommendation matrix (aggregation of aggregators)

**Design:** Final action from BQ score × IA score with quality and attractiveness floors.

#### Assumptions

- Discrete bands are preferable to continuous utility for auditability.
- Weak quality should dominate cheapness (Avoid).
- Elite quality with insufficient IA should not force a Buy (Watch / wait).

#### Strengths

- Best expression of HAP’s core philosophy in the stack.
- Prevents “cigar-butt on terrible businesses” from becoming automatic buys.
- Prevents “wonderful company at any price” from becoming automatic buys.

#### Blind spots / doc fidelity

- Investment Methodology’s four pillars and “all pillars must support Strong Buy” are **stricter in prose** than the two-score matrix.
- Financial Strength and explicit peer/index victory are not independent gates.
- Label taxonomy differences between docs and operating codes can confuse validation reviewers (see Validation Campaign).

#### Potential biases

- Threshold cliffs.
- Conservative on Strong Buy (generally aligned with humility).

---

## 5. Rule Library vs scoring philosophy

### What works well

- Rules as **evidence generators**, not recommenders — correct separation.
- Severity taxonomy supports explainability.
- Growth and profitability rule depth is comparatively strong.

### Methodology tensions

| Rule family | Intent | Operating tension |
|-------------|--------|-------------------|
| MOAT001–003 | Peer-relative durable advantage | Requires peer series; not central to BQ score |
| PEER001–003 | Industry opportunity set | Partially reflected in ER overlays; weak in BQ |
| IDX001–002 | Index opportunity cost | Present in ER thinking; not a named recommendation |
| BQ001–003 | Cross-cutting quality patterns | Aggregator does not evaluate these as a layer |
| VA005–006 (as documented) | Expected return / vs S&P language under Valuation rules | Expected-return concerns belong conceptually with ER; naming/placement can confuse audits |

**Audit conclusion:** The Rule Library describes a richer relative-value and moat methodology than the score roll-ups currently emphasize. Absolute thresholds do more of the daily work than peer-relative rules.

---

## 6. Philosophy fidelity scorecard

| Playbook / methodology principle | Fidelity | Notes |
|----------------------------------|----------|-------|
| Buy businesses, not stocks | High | BQ vs IA separation |
| Long-term window | Medium–High | Preferred 10y; many scores use ~5y |
| Economic reality over accounting | Medium | Adjustments supported; defaults still accounting-heavy |
| Capital allocation matters | High | Dedicated module |
| Cash harder to manipulate | High | Cash module + growth cash filters |
| ROIC vs WACC | High | Profitability + CA |
| Growth only if value-creating | High | Growth rules/score design |
| Competitive advantage | Medium | Outlook/metadata + ROIC persistence; peer moat thin |
| Financial strength | Medium | Balance sheet yes; separate FS score no |
| Valuation determines returns | High | Valuation + ER + IA |
| Compare vs alternatives | Medium | ER index hurdle; peer often overlay-dependent |
| Explainability | High | Findings, evidence, deterministic scores |
| Facts vs judgment | High | Valuation inputs / outlook labeled as judgment |
| Consistency across companies | High within model; Medium across industries | Absolute thresholds |
| Humility / confidence | High in design | Must be respected in review, not ignored |

---

## 7. Highest-priority methodology risks (for future design debate only)

These are **not** change requests in Sprint 5.2. They are the issues most likely to distort real-company validation:

1. **Industry-agnostic thresholds** — systematic sector mis-ranking risk.
2. **Missing-data renormalization** — incomparable BQ/IA meaning across coverage levels.
3. **Cheapness double-count** between Valuation MOS and Expected Return reversion inside IA.
4. **Outlook metadata dependence** — Stage 4 often absent in practice.
5. **Financials / REITs / cyclicals** — FCF and leverage primitives poorly matched.
6. **Peer/moat/index under-weight relative to documentation rhetoric.**
7. **Margins module gap** — margin structure not independently analyzed.
8. **Financial Strength score documented but not aggregated.**
9. **Additive expected-return identity** — possible double-counting with FV path.
10. **Recommendation label taxonomy drift** between docs and operating matrix (communication risk during Validation Campaign).

---

## 8. Aggregation methodology — overall verdict

The aggregation design is **philosophically sound**:

- Quality aggregated from fundamental modules without price.
- Attractiveness aggregated from valuation and expected return without re-scoring quality.
- Recommendation as a transparent matrix.

It is **not yet a full literal implementation of every sentence** in the Investment Methodology (four equal pillars, mandatory peer superiority, standalone Financial Strength, Strong Buy only when all pillars affirm).

For validation work, treat HAP as:

> A deterministic quality-vs-price engine with ROIC/cash/capital-allocation emphasis, absolute threshold scoring, FCF-centric valuation, and an index-aware expected-return overlay — with peer/moat/outlook richness available mainly when metadata and rule coverage are present.

---

## 9. Suggested use of this audit

1. During Sprint 5.1 company reviews, map anomalies to the blind spots above (especially industry misfit, missing overlays, cheapness cascade).
2. Do **not** change weights or scoring in response to a single company.
3. If escalation is needed, open methodology tickets grouped by theme (industry normalization, peer layer, financials templates, ER identity, FS aggregator) — still outside this sprint’s “no code / no scoring changes” boundary.

---

## 10. Document control

| Item | Value |
|------|-------|
| Audit sprint | 5.2 |
| Scope | Methodology only |
| Code changes | None |
| Scoring / weight changes | None |
| Primary output | `docs/METHODOLOGY_AUDIT.md` |
