# HAP Rule Library

Version: 1.0

---

# Purpose

The Rule Library defines the deterministic financial rules used by HAP.

Rules transform raw financial metrics into structured findings.

Rules never generate recommendations directly.

They produce evidence that is later consumed by the Investment Intelligence Engine.

Rules must be:

- Deterministic
- Explainable
- Auditable
- Testable
- Independent of LLMs

Every rule contains:

- Rule ID
- Category
- Trigger
- Severity
- Finding
- Explanation
- Suggested Analyst Action

---

# Rule Severity

INFO

Healthy condition.

POSITIVE

Strong positive indicator.

WARNING

Potential issue requiring attention.

CRITICAL

Serious financial concern.

---

# PROFITABILITY RULES

## PR001

Rule

ROIC > 20%

Severity

POSITIVE

Finding

Exceptional Capital Efficiency

Explanation

The company generates returns on invested capital significantly above typical corporate cost of capital.

Analyst Action

None.

---

## PR002

ROIC between 15% and 20%

Finding

Excellent Capital Efficiency

---

## PR003

ROIC between 10% and 15%

Finding

Healthy Returns

---

## PR004

ROIC below WACC

Severity

CRITICAL

Finding

Economic Value Destruction

Analyst Action

Investigate competitive position and capital allocation.

---

## PR005

ROIC declining for five consecutive years

Severity

WARNING

Finding

Deteriorating Capital Efficiency

---

## PR006

Operating Margin increasing five years

Finding

Improving Operating Efficiency

---

## PR007

Operating Margin declining five years

Finding

Margin Compression

---

## PR008

Net Margin volatility exceeds threshold

Finding

Unstable Profitability

---

## PR009

ROE > 20%

Finding

Excellent Shareholder Returns

---

## PR010

ROA consistently increasing

Finding

Improving Asset Utilization

---

# GROWTH RULES

## GR001

Revenue CAGR > 15%

Finding

Exceptional Revenue Growth

---

## GR002

Revenue CAGR between 8% and 15%

Finding

Healthy Revenue Growth

---

## GR003

Revenue CAGR below inflation

Severity

WARNING

Finding

Weak Organic Growth

---

## GR004

EPS growing faster than revenue

Finding

Operating Leverage Improving

---

## GR005

Revenue growing while FCF declines

Severity

WARNING

Finding

Low Quality Growth

---

## GR006

Share count increasing every year

Finding

Shareholder Dilution

Analyst Action

Review equity compensation.

---

## GR007

Revenue growth driven primarily by acquisitions

Finding

Acquisition Driven Growth

Analyst Action

Separate organic growth.

---

## GR008

EPS CAGR > 20%

Severity

POSITIVE

Finding

Exceptional Earnings Growth

Analyst Action

Confirm not driven solely by buybacks or one-time tax items.

---

## GR009

EPS CAGR < 0 over window with ≥3 EPS points

Severity

WARNING

Finding

Negative Earnings Growth

Analyst Action

Separate cyclical vs structural decline.

---

## GR010

FCF CAGR > 15% AND latest FCF > 0

Severity

POSITIVE

Finding

Exceptional Cash Flow Growth

---

## GR011

Latest FCF < 0 AND Revenue CAGR > 5%

Severity

CRITICAL

Finding

Cash-Consuming Expansion

Analyst Action

Stress-test funding needs and reinvestment returns.

---

## GR012

abs(Revenue CAGR) < 2% over 5Y window

Severity

INFO

Finding

Revenue Stagnation

---

## GR013

Revenue CAGR ≤ −5%

Severity

CRITICAL

Finding

Structural Revenue Decline

Analyst Action

Assess disruption, share loss, and turnaround credibility.

---

## GR014

FCF CAGR ≥ Revenue CAGR − 2pp AND Revenue CAGR > 0 AND latest FCF > 0

Severity

POSITIVE

Finding

Cash-Backed Growth

---

## GR015

EPS CAGR > 5% AND FCF CAGR < 0

Severity

WARNING

Finding

Accrual Growth Risk

Analyst Action

Review receivables, capitalization policies, and non-cash earnings.

---

## GR016

Share Count CAGR < 0 AND Revenue CAGR > 0

Severity

POSITIVE

Finding

Anti-Dilutive Expansion

---

## GR017

Revenue CAGR > 0 AND Revenue per Share CAGR < 0

Severity

WARNING

Finding

Dilution Exceeds Top-Line Growth

Analyst Action

Recast growth on per-share metrics for investment debate.

---

## GR018

Book Value CAGR ≥ 8%

Severity

POSITIVE

Finding

Strong Book Value Compounding

---

## GR019

Growth Stability ≥ 0.70 AND Revenue CAGR > 0

Severity

POSITIVE

Finding

Stable Growth

---

## GR020

Growth Volatility > 0.80 OR Growth Stability < 0.40

Severity

WARNING

Finding

Unstable Growth

Analyst Action

Prefer longer windows; normalize one-time spikes.

---

## GR021

Growth Persistence ≥ 0.80 over ≥5 YoY observations

Severity

POSITIVE

Finding

Persistent Growth

---

## GR022

Growth Acceleration ≤ −5 percentage points

Severity

WARNING

Finding

Growth Deceleration

Analyst Action

Update outlook assumptions; avoid extrapolating old CAGR.

---

## GR023

Growth Acceleration ≥ +5 percentage points AND latest Revenue YoY > 0

Severity

POSITIVE

Finding

Growth Acceleration

Analyst Action

Test durability vs easy comps / temporary stimulus.

---

## GR024

At least one Revenue YoY > 25% and at least one Revenue YoY < −10% in same 5Y window

Severity

WARNING

Finding

Boom-Bust Growth Pattern

Analyst Action

Normalize cycle; do not treat peak CAGR as base case.

---

## GR025

Revenue CAGR > 30% over ≥3 years

Severity

WARNING

Finding

Hypergrowth Sustainability Risk

Analyst Action

Use fade assumptions in outlook/valuation; stress-test.

---

## GR026

normalize_covid metadata flag OR FY2020–FY2021 with |Revenue YoY| > 40%

Severity

INFO

Finding

Possible Base-Effect Distortion

Analyst Action

Propose COVID-normalized growth series via analyst adjustment.

---

## GR027

Latest Revenue YoY > 40% AND prior 3Y average Revenue YoY < 10%

Severity

WARNING

Finding

One-Time Revenue Spike Suspected

Analyst Action

Remove one-time revenue; recompute organic CAGR.

---

## GR028

discontinued_operations_impact metadata flag

Severity

WARNING

Finding

Discontinued Operations Distortion

Analyst Action

Restate continuing-operations growth series.

---

## GR029

Any shareholders’ equity point ≤ 0 in BV CAGR window

Severity

INFO

Finding

Book Value Growth Not Meaningful

Analyst Action

Ignore BV_CAGR; rely on revenue/EPS/FCF growth.

---

## GR030

Revenue points < 3

Severity

WARNING

Finding

Insufficient Growth History

Analyst Action

Lower confidence; request longer series before high-conviction use.

---

## GR031

Organic Revenue CAGR ≥ 8% AND Inorganic Revenue Share < 20%

Severity

POSITIVE

Finding

Strong Organic Growth

---

## GR032

Revenue CAGR > 0 AND Organic Revenue CAGR < 0 (organic series available)

Severity

CRITICAL

Finding

Acquisitions Masking Organic Decline

Analyst Action

Treat organic decline as primary growth truth; normalize.

---

# CASH FLOW RULES

## CF001

Free Cash Flow positive every year

Finding

Consistent Cash Generation

---

## CF002

Cash Conversion > 100%

Finding

Exceptional Cash Conversion

---

## CF003

Cash Conversion below 70%

Severity

WARNING

Finding

Weak Cash Conversion

---

## CF004

Negative Free Cash Flow three consecutive years

Severity

CRITICAL

Finding

Persistent Cash Burn

---

## CF005

Owner Earnings consistently increasing

Finding

Strong Economic Earnings

---

## CF006

Capital Expenditures increasing while revenue stagnates

Finding

Capital Efficiency Risk

---

# BALANCE SHEET RULES

## BS001

Current Ratio > 2

Finding

Strong Liquidity

---

## BS002

Current Ratio below 1

Severity

WARNING

Finding

Liquidity Risk

---

## BS003

Debt / EBITDA > 4

Severity

CRITICAL

Finding

Excessive Financial Leverage

---

## BS004

Interest Coverage below 3

Finding

Debt Servicing Risk

---

## BS005

Net Cash Position

Finding

Strong Financial Flexibility

---

## BS006

Debt decreasing every year

Finding

Balance Sheet Strengthening

---

# CAPITAL ALLOCATION RULES

## CA001

ROIC increasing while share count decreases

Finding

Excellent Capital Allocation

---

## CA002

Large acquisitions with declining ROIC

Severity

WARNING

Finding

Potential Value Destructive Acquisition

---

## CA003

Consistent dividend growth

Finding

Shareholder Friendly Management

---

## CA004

Buybacks executed below intrinsic value

Finding

Value Creating Buybacks

---

## CA005

Buybacks while debt increases significantly

Severity

WARNING

Finding

Aggressive Financial Engineering

---

# VALUATION RULES

## VA001

Margin of Safety > 30%

Finding

Highly Attractive Valuation

---

## VA002

Margin of Safety between 15% and 30%

Finding

Attractive Valuation

---

## VA003

Margin of Safety below 10%

Finding

Limited Upside

---

## VA004

Intrinsic Value below current market price

Finding

Potentially Overvalued

---

## VA005

Expected Return above 15%

Finding

Excellent Expected Return

---

## VA006

Expected Return below S&P 500 expected return

Severity

WARNING

Finding

Index Likely Superior

---

# BUSINESS QUALITY RULES

## BQ001

ROIC consistently above WACC

AND

Positive Free Cash Flow

AND

Stable Margins

Finding

Excellent Business Quality

---

## BQ002

High ROIC

AND

Negative Free Cash Flow

Finding

Profitability Quality Requires Investigation

---

## BQ003

High Growth

AND

Declining Margins

Finding

Growth Quality Deteriorating

---

# COMPETITIVE ADVANTAGE RULES

## MOAT001

ROIC exceeds peer median for 10 years

Finding

Evidence of Durable Competitive Advantage

---

## MOAT002

Gross Margin consistently exceeds peers

Finding

Pricing Power

---

## MOAT003

Operating Margin expanding while peers contract

Finding

Competitive Position Improving

---

# PEER COMPARISON RULES

## PEER001

ROIC exceeds peer average

Finding

Outperforming Industry

---

## PEER002

Revenue Growth exceeds peer average

Finding

Market Share Expansion

---

## PEER003

Expected Return below peer average

Finding

Inferior Investment Opportunity

---

# INDEX COMPARISON RULES

## IDX001

Expected Return exceeds S&P 500 by at least 3%

Finding

Superior Expected Return versus Index

---

## IDX002

Expected Return below S&P 500

Finding

Index Preferred

---

# OUTLOOK RULES

## OUT001

Revenue guidance increased

Finding

Positive Forward Outlook

---

## OUT002

Margins expected to improve

Finding

Operating Outlook Improving

---

## OUT003

Management lowered long-term guidance

Severity

WARNING

Finding

Future Growth Expectations Reduced

---

# GENERAL PRINCIPLES

Rules produce findings.

Rules never produce investment recommendations.

Multiple rules combine to produce scores.

Scores combine to produce business quality.

Business quality combines with valuation to produce recommendations.

Recommendations are always supported by evidence generated from rules.

Every rule should have automated unit tests.

Every rule should be traceable to the financial metrics that triggered it.

The Rule Library is expected to grow continuously as HAP evolves.

Version 1.0 intentionally contains foundational rules only.