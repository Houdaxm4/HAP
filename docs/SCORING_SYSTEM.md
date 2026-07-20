# HAP Scoring System

Version: 1.0

---

# Purpose

The HAP Scoring System transforms structured financial analysis into objective investment scores.

The goal is to ensure that every recommendation produced by HAP is:

- Consistent
- Explainable
- Repeatable
- Auditable

The scoring system must never rely on subjective LLM judgment.

Scores are calculated from deterministic financial rules and structured analytical findings.

---

# Overall Philosophy

HAP separates company quality from investment attractiveness.

Business Quality asks:

"Would I like to own this business?"

Investment Attractiveness asks:

"Would I buy this business today at the current price?"

These are independent scores.

A company can receive:

Business Quality

95

Investment Attractiveness

55

because an excellent company can still be significantly overvalued.

---

# Overall Scoring Structure

Business Quality Score

↓

Financial Strength

↓

Investment Attractiveness

↓

Final Recommendation

---

# Business Quality Score

Business Quality evaluates the underlying company.

Weighting

Profitability

25%

Growth

15%

Cash Flow

20%

Balance Sheet

15%

Capital Allocation

15%

Business Outlook

10%

Total

100%

Business Quality intentionally ignores valuation.

---

# Investment Attractiveness Score

Investment Attractiveness evaluates whether today's price offers an attractive opportunity.

Weighting

Intrinsic Value

35%

Expected Return

30%

Margin of Safety

20%

Relative Valuation

15%

Total

100%

Investment Attractiveness intentionally ignores company quality.

---

# Financial Strength Score

Financial Strength measures financial resilience.

Weighting

Liquidity

25%

Leverage

30%

Interest Coverage

20%

Cash Position

15%

Debt Maturity

10%

---

# Profitability Score

Profitability is calculated from:

ROIC

40%

Operating Margin

20%

Net Margin

15%

ROE

10%

ROA

5%

Margin Stability

10%

---

# Growth Score

Growth is calculated from:

Revenue CAGR

30%

EPS CAGR

25%

FCF CAGR

25%

Growth Stability

10%

Organic Growth

10%

---

# Cash Flow Score

Cash Flow is calculated from:

Free Cash Flow

30%

Cash Conversion

30%

Owner Earnings

20%

FCF Stability

20%

---

# Balance Sheet Score

Balance Sheet Score is calculated from:

Debt

35%

Liquidity

25%

Interest Coverage

20%

Net Cash Position

10%

Working Capital

10%

---

# Capital Allocation Score

Capital Allocation Score is calculated from:

ROIC Trend

30%

Share Buybacks

20%

Dividend Policy

10%

Reinvestment Quality

20%

Acquisition Quality

20%

---

# Business Outlook Score

Business Outlook evaluates future prospects.

Inputs

Industry Trends

Competitive Position

Management Guidance

Market Opportunities

Structural Risks

The Outlook score is intentionally capped at 10% of Business Quality because future forecasts are inherently uncertain.

---

# Valuation Score

Valuation evaluates today's market pricing.

Inputs

Discounted Cash Flow

Historical Multiples

Enterprise Value

Owner Earnings Value

Reverse DCF

Outputs

Fair Value

Margin of Safety

Premium / Discount

---

# Expected Return Score

Expected Return estimates future shareholder returns.

Components

Growth Contribution

Dividend Yield

Buyback Yield

Valuation Reversion

Multiple Expansion

Expected CAGR

---

# Business Quality Interpretation

90–100

Exceptional Business

80–89

Excellent Business

70–79

High Quality Business

60–69

Average Business

50–59

Below Average

Below 50

Poor Business

---

# Investment Attractiveness Interpretation

90–100

Strong Buy Opportunity

80–89

Buy Opportunity

70–79

Reasonably Attractive

60–69

Fairly Valued

50–59

Limited Upside

Below 50

Avoid at Current Price

---

# Final Recommendation Matrix

Business Quality

90+

Investment Attractiveness

90+

Recommendation

Strong Buy

---

Business Quality

90+

Investment Attractiveness

70–89

Recommendation

Buy

---

Business Quality

90+

Investment Attractiveness

Below 70

Recommendation

Watch

Reason

Excellent company but insufficient margin of safety.

---

Business Quality

70–89

Investment Attractiveness

80+

Recommendation

Buy

---

Business Quality

Below 70

Investment Attractiveness

Above 80

Recommendation

Speculative

Requires analyst review.

---

Business Quality

Below 60

Recommendation

Avoid

Regardless of valuation.

---

# Confidence Score

Confidence is calculated independently.

Inputs

Historical Coverage

Source Agreement

Audited Data

Missing Data

Analyst Assumptions

Forecast Dependency

Confidence never affects the score itself.

Instead, confidence qualifies the reliability of the score.

Example

Business Quality

92

Confidence

0.98

Very reliable.

Business Quality

92

Confidence

0.53

Requires analyst review.

---

# Analyst Overrides

Analysts may override:

Growth Assumptions

Discount Rate

Terminal Growth

R&D Capitalization

Owner Earnings Adjustments

Margin Normalization

Every override must record:

Original Value

New Value

Reason

Impact

Analyst Name

Timestamp

Overrides never replace reported financial statements.

---

# Future Expansion

The scoring system is designed to evolve.

Future versions may include:

ESG Score

Management Quality Score

Competitive Moat Score

Innovation Score

Customer Concentration Score

Geographic Diversification Score

Currency Risk Score

Country Risk Score

AI Risk Score

Cybersecurity Risk Score

Each future score must integrate into the existing framework without changing the core philosophy.

---

# Core Principle

Every recommendation generated by HAP must be reproducible.

Given the same financial data, rules, and assumptions, HAP must always produce the same scores and the same recommendation.

The language model explains the recommendation.

The scoring engine determines it.