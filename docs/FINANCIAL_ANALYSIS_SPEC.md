# HAP Financial Analysis Specification

Version: 1.0

---

# Purpose

The Financial Analysis Engine is the core intelligence layer of HAP (Houda's Analyst Platform).

Its purpose is to evaluate the economic quality of a business, determine whether it creates shareholder value, assess whether the current market price represents an attractive investment opportunity, and produce deterministic, explainable, and auditable analytical outputs.

The engine does not write reports.

It produces structured analytical objects that are later consumed by the Report Generator, Email Generator, Analyst Chat, and future APIs.

---

# Core Philosophy

HAP separates two completely different questions.

## Question 1

Is this fundamentally an excellent business?

Examples:

- Does it consistently earn high returns on capital?
- Does it possess a durable competitive advantage?
- Does it generate strong cash flow?
- Does management allocate capital intelligently?
- Is the balance sheet financially healthy?
- Is profitability sustainable?

---

## Question 2

Is this an attractive investment today?

Examples:

- Is the current valuation attractive?
- What expected return does today's market price imply?
- Is there an adequate margin of safety?
- Should an investor buy today, wait, hold, or avoid?

These questions must never be combined.

A wonderful company may be a poor investment if it is significantly overvalued.

Likewise, an average company may represent an attractive investment if priced far below intrinsic value.

---

# Design Principles

Every analysis module must follow these principles.

1. Single Responsibility

Every module answers exactly one financial question.

2. Structured Outputs

Modules return structured Pydantic objects only.

No narrative text.

3. Explainability

Every conclusion must be supported by evidence.

4. Auditability

Every metric must trace back to source data.

5. Deterministic Logic

Financial rules should be deterministic whenever possible.

6. AI as Writer

Large language models explain conclusions.

They do not invent them.

7. Separation of Concerns

Analysis modules never access:

- Excel
- SEC APIs
- Yahoo Finance
- Raw JSON
- Workbook cells

Modules consume only CompanyFinancialModel.

---

# Overall Architecture

Data Providers

↓

Excel Parser

↓

Workbook Validation

↓

Canonical Financial Model

↓

Financial Analysis Engine

↓

Investment Intelligence Engine

↓

Recommendation Engine

↓

Report Generator

↓

Email Generator

↓

Analyst Chat

---

# Canonical Financial Model

The canonical financial model is the only input accepted by analysis modules.

It contains:

IncomeStatement

BalanceSheet

CashFlowStatement

MarketData

ValuationInputs

WorkbookMetrics

CompanyMetadata

Historical FinancialSeries

Every value includes:

- value
- reporting period
- currency
- confidence
- source
- audited flag
- provenance

---

# Workbook Metrics vs HAP Metrics

HAP distinguishes two classes of quantitative outputs. They must never be conflated.

## Workbook Metrics

Workbook Metrics are **analyst-owned** values from the Excel workbook — typically formula cells (ROIC, margins, CAGRs, valuation ratios, etc.).

| Property | Rule |
|---|---|
| Source | Parsed from workbook; stored on ``CompanyFinancialModel.workbook_metrics`` |
| Mutability | **Read-only** for HAP — never overwritten by analysis modules or the pipeline |
| Use in scoring | Workbook Metrics do **not** feed module scores directly |
| Use in analysis | Compared against independently computed HAP Metrics when equivalents exist |

Golden rule (``PROJECT.md``): HAP must never overwrite analyst-calculated ratios or formulas in the workbook.

## HAP Metrics

HAP Metrics are **computed independently** by each analysis module from canonical statement facts (``FinancialSeries`` / ``FinancialPoint``).

| Property | Rule |
|---|---|
| Source | Derived inside the module from ``CompanyFinancialModel`` statements |
| Output field | ``AnalysisModuleResult.metrics`` (each ``MetricResult`` has ``origin="hap"``) |
| Use in scoring | HAP Metrics feed deterministic scores and rules |
| Workbook access | Modules never read Excel; workbook values arrive only via ``workbook_metrics`` on the model |

## Metric Comparison (additive extension)

When a module computes a HAP Metric that has an equivalent Workbook Metric, the module records a structured comparison under:

``AnalysisModuleResult.coverage["metric_comparisons"]``

Each comparison includes:

| Field | Description |
|---|---|
| Workbook Value | Analyst workbook metric value |
| HAP Value | Independently computed HAP value |
| Difference | ``HAP Value − Workbook Value`` |
| Tolerance | Allowed absolute or relative variance |
| Status | ``match``, ``within_tolerance``, ``divergent``, ``workbook_only``, ``hap_only``, ``not_comparable`` |
| Recommended Action | e.g. ``no_action``, ``reconcile_inputs``, ``investigate_workbook_formula``, ``request_analyst_review`` |

Comparisons are aggregated on ``AnalysisEngineResult.metric_comparisons``.

This extension does **not** change the core ``AnalysisModuleResult`` contract fields (``module_name``, ``score``, ``confidence``, ``metrics``, ``findings``, ``risks``, ``opportunities``, ``evidence``, ``analyst_adjustments``, ``status``).

Future modules (**Cash Flow**, **Balance Sheet**, **Capital Allocation**, **Valuation**, **Expected Return**) must:

1. Compute HAP Metrics from statement facts only.
2. Never write workbook formula cells.
3. Attach Workbook vs HAP comparisons when equivalents exist.

---

# Standard Analysis Module Contract

Every module returns AnalysisModuleResult.

Fields:

module_name

score

confidence

metrics

findings

risks

opportunities

evidence

analyst_adjustments

status

No free-form text.

---

# Scores

Every module produces a score from 0 to 100.

Interpretation

90–100

Exceptional

80–89

Excellent

70–79

Good

60–69

Average

40–59

Weak

Below 40

Poor

Modules define their own scoring methodology.

---

# Confidence

Confidence measures certainty.

Confidence is influenced by:

Audited statements

Historical coverage

Source agreement

Missing information

Analyst assumptions

Conflicting sources

Confidence never represents business quality.

It represents certainty.

---

# Evidence

Every finding must include evidence.

Evidence contains:

Metric

Value

Period

Source

Provenance

Confidence

Findings without evidence are invalid.

---

# Deterministic Rules

Business rules belong in rule libraries.

Examples

ROIC > 15%

↓

Excellent Capital Efficiency

Gross Margin increasing 5 years

↓

Improving Competitive Position

Debt / EBITDA > 4

↓

High Financial Risk

Revenue CAGR below inflation

↓

Weak Organic Growth

LLMs never create deterministic rules.

---

# Module Specifications

---

## Profitability Module

Purpose

Evaluate the company's ability to convert revenue into durable economic profit.

Questions

- Are margins attractive?
- Are margins improving?
- Are returns on capital high?
- Is profitability stable?

Metrics

Gross Margin

Operating Margin

EBIT Margin

Net Margin

ROA

ROE

ROIC

NOPAT

Margin CAGR

Margin Stability

Margin Trend

Possible Findings

Exceptional ROIC

Improving Margins

Margin Compression

Declining Returns

Stable Profitability

Possible Risks

Declining margins

Low ROIC

High earnings volatility

Possible Adjustments

Capitalize R&D

Normalize unusual margins

Remove one-time expenses

Outputs

Score

Confidence

Metrics

Findings

Evidence

Risks

Adjustment Proposals

---

## Growth Module

Purpose

Determine whether company growth is durable and economically valuable.

Questions

Is growth sustainable?

Is growth profitable?

Is growth accelerating?

Metrics

Revenue CAGR

EPS CAGR

FCF CAGR

Operating Income CAGR

Book Value CAGR

Share Count CAGR

Growth Stability

Growth Trend

Findings

Strong Organic Growth

Growth Deceleration

Negative Earnings Growth

Stable Growth

Risks

Acquisition-driven growth

Revenue stagnation

Share dilution

Possible Adjustments

Normalize acquisition effects

Adjust one-time growth

Outputs

Standard AnalysisModuleResult

---

## Cash Flow Module

Purpose

Evaluate cash generation quality.

Questions

Does accounting profit convert into cash?

Metrics

Operating Cash Flow

Free Cash Flow

Cash Conversion

Owner Earnings

CapEx Ratio

FCF Margin

Cash Flow Stability

Findings

Excellent Cash Generator

Weak Cash Conversion

Strong Owner Earnings

Risks

Negative FCF

Poor conversion

High CapEx dependency

Adjustments

Owner earnings normalization

Maintenance CapEx adjustment

---

## Balance Sheet Module

Purpose

Evaluate financial strength.

Metrics

Current Ratio

Quick Ratio

Debt / Equity

Debt / EBITDA

Interest Coverage

Net Debt

Liquidity

Findings

Strong Balance Sheet

High Leverage

Excellent Liquidity

Risks

Debt maturity

Refinancing risk

Liquidity weakness

---

## Capital Allocation Module

Purpose

Evaluate management's capital allocation skill.

Metrics

Share Buybacks

Dividends

Acquisitions

ROIC Trend

Reinvestment Rate

Findings

Excellent Capital Allocation

Value-destructive acquisitions

Shareholder Friendly

Risks

Empire building

Poor reinvestment

---

## Valuation Module

Purpose

Estimate intrinsic value.

Methods

DCF

Owner Earnings

Reverse DCF

Enterprise Multiples

Historical Multiples

Outputs

Intrinsic Value

Margin of Safety

Fair Value Range

Valuation Confidence

Scenario Analysis

Bull

Base

Bear

---

## Expected Return Module

Purpose

Estimate forward-looking investor return.

Metrics

Expected IRR

Dividend Yield

Buyback Yield

Growth Contribution

Valuation Change

Expected CAGR

Findings

High Expected Return

Limited Upside

Negative Expected Return

---

## Recommendation Module

Purpose

Aggregate every previous module.

Produces

Business Quality Score

Investment Attractiveness Score

Overall Recommendation

Recommendations

Strong Buy

Buy

Hold

Watch

Avoid

Sell

Recommendation never ignores valuation.

---

# Investment Intelligence Engine

The Investment Intelligence Engine combines outputs from every module.

Inputs

Profitability

Growth

Cash Flow

Balance Sheet

Capital Allocation

Valuation

Expected Return

Outputs

Business Quality

Financial Strength

Growth Quality

Capital Allocation Quality

Valuation

Investment Attractiveness

Final Recommendation

No financial calculations occur here.

Only synthesis.

---

# Report Generator

Consumes structured outputs.

Produces

Executive Summary

Business Overview

Financial Analysis

Valuation

Risks

Opportunities

Recommendation

No calculations occur inside the report generator.

---

# Email Generator

Consumes Recommendation.

Produces

New Analysis Email

Quarterly Update Email

Annual Update Email

Emails summarize analytical outputs.

They never perform analysis.

---

# Analyst Chat

The Analyst Chat retrieves:

Canonical Financial Model

Analysis Results

Recommendation

Company History

SEC Evidence

Provenance

The LLM answers using retrieved evidence.

The chat never invents financial data.

---

# Long-Term Vision

HAP should become an institutional-grade investment research platform capable of:

- Completing analyst Excel models.
- Validating reported financial data.
- Performing structured financial analysis.
- Producing explainable investment recommendations.
- Generating professional reports.
- Drafting analyst communications.
- Maintaining historical company knowledge.
- Supporting continuous quarterly updates.
- Remaining fully auditable and explainable.

Every new feature added to HAP must follow this specification.