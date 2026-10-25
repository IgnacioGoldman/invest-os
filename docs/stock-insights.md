# Stock Insights

**Core principle: Invest OS collects, calculates, and filters. AI interprets, evaluates, and ranks.**

---

## 1. Financial Data Collection

Invest OS collects publicly available financial and market information across four categories.

### Business Performance
- Revenue growth and growth momentum.
- Operating margin and profitability trends.
- Earnings growth.
- Free cash flow and cash conversion.
- Debt, liquidity, and capital allocation.
- Share dilution and returns on capital.

### Price and Market Data
- Current price and historical performance.
- Proximity to technical support.
- Distance from historical highs and lows.
- Volatility and industry relative strength.

### Valuation
- Trailing and Forward P/E.
- PEG and Price/Sales.
- EV/EBITDA.
- Free cash flow yield.
- Historical valuation and peer comparisons.

### Additional Context
- Recent financial reports and SEC filings.
- Upcoming earnings announcements.
- Accounting anomalies and unusual items.
- Data completeness and source reliability.

Each metric retains its source, calculation method, and data-quality information.

**Not every collected metric is suitable for automatic investment judgments.**

---

## 2. Objective Business Screening

The first analytical layer focuses on measurable business performance.

These metrics allow investors to identify companies with attractive operating characteristics without relying on complex valuation assumptions.

### Business
- [Revenue Growth YoY](metrics/signals/revenue-growth-yoy.md)
- [Revenue Growth Momentum]
- [Revenue Growth Momentum](metrics/signals/revenue-growth-momentum.md)
- [Operating Margin]
- [Operating Margin Trend]

### Entry Timing

- [Support](metrics/signals/support.md).
- [Industry Relative Strength](metrics/contextual/industry-relative-performance.md).


### Red Flag Detection

Strong growth or profitability does not necessarily mean a company is financially healthy.

Invest OS includes a deterministic **Red Flag Detection** layer that identifies measurable financial anti-patterns.

Examples include:

- **Weak cash generation:** Persistent negative free cash flow or poor earnings-to-cash conversion.
- **Excessive leverage:** Elevated debt relative to earnings or insufficient interest coverage.
- **Share dilution:** Sustained increases in outstanding shares.
- **Margin deterioration:** Significant declines in operating profitability.
- **Earnings-quality concerns:** Material inconsistencies between reported earnings and cash generation.
- **Valuation warnings:** Measurable valuation extremes supported by reliable historical or peer evidence.

Each condition follows explicit, explainable rules, with industry-specific treatment where necessary.

### Red Flag Count

Detected anti-patterns are consolidated into a derived metric:

**Red Flag Count: 0 → N**

Each distinct triggered condition contributes one flag.

Investors can use this metric in stock filters.

Example:

`Red Flag Count <= 1`

The underlying flags remain accessible so investors can understand which conditions were triggered.

Related conditions should not be double-counted. Missing information must not be interpreted as zero risk; data coverage is tracked separately.

**A red flag is a reason to investigate, not an automatic reason to reject an investment.**

AI can later determine whether a detected warning is temporary, justified by business circumstances, or already reflected in the stock price.

---

## 5. Valuation Requires Context

Unlike revenue growth or operating margin, valuation metrics cannot reliably determine investment attractiveness in isolation.

For example, a Forward P/E of 30 might be attractive for one business and excessive for another.

Its interpretation depends on:

- Expected revenue and earnings growth.
- Industry characteristics.
- Competitive position and growth durability.
- Historical valuation.
- Cash generation and financial risks.

Invest OS continues collecting valuation metrics but avoids assigning definitive **Cheap / Fair / Expensive** judgments based on individual ratios.

Instead, valuation information is preserved as context for deeper AI analysis.

Objective valuation warnings may contribute to the Red Flag Count when supported by reliable evidence.

**Valuation metrics describe what investors are paying. AI evaluates whether that price is justified.**

---

## 6. Investment Analysis Workflow

Invest OS follows a structured investment discovery process.

### Step 1 — Collect and Validate

Gather business, valuation, and market data.

Verify data quality, completeness, and comparability.

### Step 2 — Screen

Apply configurable filters using measurable characteristics such as:

- Revenue growth.
- Revenue growth momentum.
- Operating margin.
- Operating margin trends.
- Proximity to support.

The goal is to identify companies worth investigating further.

### Step 3 — Identify Red Flags

Evaluate financial anti-patterns and calculate the Red Flag Count.

Allow investors to include or exclude companies based on their preferred risk criteria.

Keep individual warnings visible for further investigation.

### Step 4 — Analyze with AI

Select shortlisted stocks and provide AI with the complete available evidence:

- Business performance.
- Financial statements and cash generation.
- Valuation metrics.
- Price and market context.
- Detected red flags.
- Relevant accounting and industry information.
- Data-quality limitations.

AI evaluates each company in its business, industry, and accounting context.

The analysis produces:

**Business Quality Score (0–100)**

Evaluates business strength, profitability, competitive position, growth durability, and financial resilience.

**Valuation Attractiveness Score (0–100)**

Evaluates whether the current valuation is attractive relative to growth, profitability, business quality, and risks.

**Investment Ranking**

Compares selected stocks by overall investment attractiveness.

**Investment Rationale**

Explains strengths, weaknesses, valuation considerations, red flags, and important uncertainties.

AI may challenge or contextualize individual screening signals rather than mechanically incorporating them into the final scores.

---

## 7. Invest OS Philosophy

Invest OS separates two responsibilities.

### Deterministic Analysis — Invest OS

Collects public financial data, calculates measurable metrics, detects financial anti-patterns, and enables consistent screening.

Its purpose is to reduce noise and help investors discover potentially attractive opportunities.

### Contextual Analysis — AI

Interprets the collected evidence within the company's business, industry, financial, and valuation context.

Its purpose is to determine which shortlisted companies represent the most attractive investment opportunities and explain why.

**Invest OS discovers and organizes opportunities. AI interprets and evaluates them.**

This separation combines the consistency and transparency of rule-based screening with the contextual reasoning required for investment analysis.

---

## 8. Detailed Metric Documentation

This page describes the overall Invest OS strategy.

Individual metric documentation contains detailed formulas, thresholds, calculation methods, data requirements, and update behavior.

- [Revenue Growth Momentum](metrics/signals/revenue-growth-momentum.md)
- [Support](metrics/signals/support.md)
- [Industry Relative Strength](metrics/contextual/industry-relative-performance.md)

The strategy document remains intentionally high-level, while individual metric pages provide the technical implementation details.