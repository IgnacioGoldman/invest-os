# Investful OS — Add "Priced for Perfection" Valuation Anti-Pattern

## Objective

Extend the existing deterministic anti-pattern detection system in Investful OS by introducing one additional valuation-related red flag:

**Priced for Perfection**

This anti-pattern identifies companies whose stock valuations are exceptionally high relative to their current revenue and free cash flow generation.

The objective is to flag potentially expensive stocks before sending them for deeper AI analysis.

IMPORTANT:
Investful OS already has an anti-pattern detection architecture with multiple rules.

Inspect and reuse that architecture.

Do NOT create a separate red-flag system, scoring framework, or new filtering mechanism.

---

## 1. New Anti-Pattern: Priced for Perfection

### Description

A company may have excellent business fundamentals, strong revenue growth, and improving profitability while its stock is still extremely expensive.

This anti-pattern detects situations where investors are paying a substantial premium relative to current financial performance.

### Detection Rule

Raise the red flag when BOTH conditions are satisfied:

1. Price-to-Sales (P/S) > 10
2. Free Cash Flow Yield < 2%

Logical expression:

IF:
  priceToSales > 10
  AND
  freeCashFlowYield < 0.02

THEN:
  Trigger "Priced for Perfection"

Both conditions must be true.

This is a deterministic warning, not a definitive conclusion that the company is overvalued.

The thresholds are initial screening heuristics, not universal valuation standards.

---

## 2. Financial Metrics

Inspect the existing financial data model and derived metrics.

Reuse existing calculations where available.

### Price-to-Sales

Calculate:

Price-to-Sales =
Market Capitalization / Trailing Twelve-Month Revenue

Use the latest four reported quarters of revenue.

Do not use forward revenue estimates.

### Free Cash Flow Yield

Calculate:

Free Cash Flow Yield =
Trailing Twelve-Month Free Cash Flow / Market Capitalization

Where:

Free Cash Flow =
Operating Cash Flow - Capital Expenditures

Reuse the application's existing definition of free cash flow if one is already established and consistent with this definition.

### Data Integrity

- Prefer existing financial metrics and calculations.
- Avoid duplicate calculation logic.
- Use consistent currencies and units.
- Ensure revenue and cash flow periods are aligned.
- Use a consistent market capitalization snapshot.
- Handle missing financial data.
- Handle zero or negative revenue.
- Handle zero or negative free cash flow correctly.
- Never substitute missing data with zero.
- Do not invent financial values.
- If the required metrics cannot be calculated reliably, return an unavailable/not-evaluated result rather than silently passing the company.
- Respect existing industry applicability rules, particularly where conventional free cash flow is not economically comparable, such as financial institutions.

Negative free cash flow mathematically satisfies the low-yield condition. Preserve the stated rule, but inspect existing negative-cash-flow anti-patterns and avoid creating duplicate definitions of the same warning.

---

## 3. Integration With Existing Anti-Pattern System

Inspect how existing anti-patterns are:

- Defined
- Calculated
- Registered
- Evaluated
- Counted
- Displayed
- Exposed to filtering

Register this as one additional independent anti-pattern.

Suggested identifier:

priced_for_perfection

Suggested category:

Valuation

Suggested display name:

Priced for Perfection

Suggested description:

"Stock valuation is unusually high relative to current revenue and free cash flow generation."

### Red-Flag Count

The existing red-flag count must automatically incorporate the new detection.

Example:

Before:
Red Flags = 0

After:
Priced for Perfection detected

Result:
Red Flags = 1

If a company already has two red flags and this new rule triggers:

Red Flags = 3

Each anti-pattern must contribute at most one flag per company.

Do not count the two underlying conditions as separate red flags.

Do not change existing red-flag calculations.

Do not introduce a separate valuation red-flag counter unless the existing architecture already supports categories.

---

## 4. Integration With Stock Filtering

The application already supports filtering companies using their total red-flag count.

Preserve this functionality.

Ensure the new anti-pattern automatically contributes to that existing count.

Example filter:

Revenue Growth YoY = Strong
AND
Red Flags = 0

A company triggering "Priced for Perfection" should no longer satisfy this filter.

IMPORTANT:

- Do not automatically remove stocks from the application.
- Do not automatically exclude flagged companies from all results.
- Let the existing filters determine which companies are displayed.
- Preserve existing presets and custom filters.
- Do not introduce a new filtering interface.

The purpose is to make this risk available to the existing screening process.

---

## 5. Stock Details

Ensure the new anti-pattern appears in the existing red-flag presentation when triggered.

Follow the same visual conventions used by other anti-patterns.

Example:

Red Flags: 1

Priced for Perfection

Price-to-Sales: 16.5×
Free Cash Flow Yield: 1.1%

Explanation:

"Stock valuation is unusually high relative to current revenue and free cash flow."

Reuse existing components, colors, and interaction patterns.

Do not introduce a new valuation score.

Do not redesign the Stock Details page.

---

## 6. Relationship With Forward P/E

Investful OS already uses Forward P/E as a valuation indicator.

Preserve that functionality.

This new anti-pattern is complementary.

Forward P/E evaluates stock price relative to estimated future earnings.

Priced for Perfection evaluates stock price relative to reported revenue and free cash flow.

Important:

- Do not replace Forward P/E.
- Do not modify its existing calculation or classification.
- Do not combine these metrics into a composite valuation score.
- Do not automatically classify a company as overvalued because this red flag triggers.

The red flag identifies a potential valuation risk that deserves further investigation.

---

## 7. Validation Against Previous Analysis

Use these examples to validate the new rule.

These figures come from the October 23, 2026 analysis snapshot and must be treated as test fixtures, not hardcoded company-specific rules.

### Shopify (SHOP)

Price-to-Sales: 16.5×
Free Cash Flow Yield: 1.1%

Expected:

Priced for Perfection = TRUE

Contribution to Red Flags = +1

### Astera Labs (ALAB)

Price-to-Sales: approximately 39×
Free Cash Flow Yield: approximately 0.6%

Expected:

Priced for Perfection = TRUE

Contribution to Red Flags = +1

### Other Companies

Evaluate all companies through the same generic rule.

Do not hardcode ticker symbols.

Do not assume that every company with a high P/E should trigger this specific warning.

Only the two defined conditions should determine the result.

---

## 8. Testing

Add or update tests for:

1. P/S > 10 and FCF Yield < 2%
   Expected: Flag triggered.

2. P/S < 10 and FCF Yield < 2%
   Expected: No flag.

3. P/S > 10 and FCF Yield > 2%
   Expected: No flag.

4. P/S < 10 and FCF Yield > 2%
   Expected: No flag.

5. P/S = 10
   Expected: No flag.

6. FCF Yield = 2%
   Expected: No flag.

7. Missing revenue or market capitalization
   Expected: Not evaluated.

8. Missing free cash flow
   Expected: Not evaluated.

9. Zero or negative free cash flow
   Expected: Apply the defined mathematical rule when data is valid, without confusing missing values with zero.

10. Existing red-flag count integration
    Expected: Count increases by exactly one when triggered.

11. Existing filtering integration
    Expected: Companies triggering this rule are excluded by a Red Flags = 0 filter.

12. Existing anti-pattern regression tests
    Expected: All existing behavior remains unchanged.

Ensure that repeated evaluations do not create duplicate flags.

---

## 9. Implementation Instructions

Before making changes:

1. Inspect the existing anti-pattern detection architecture.
2. Identify where individual detection rules are registered.
3. Identify how the total red-flag count is calculated.
4. Identify how red flags are exposed to stock filters.
5. Inspect existing P/S and free cash flow calculations.
6. Inspect the existing UI presentation of detected anti-patterns.

Then implement the new rule using the existing architecture.

Requirements:

- Minimal changes.
- No unnecessary refactoring.
- No new scoring system.
- No additional API requests if the required data already exists.
- No duplicate financial calculations.
- Preserve existing filters.
- Preserve existing UI conventions.
- Keep thresholds centrally defined and easy to adjust later.
- Do not modify unrelated features.

---

## 10. Expected Result

After implementation:

Investful OS automatically evaluates the "Priced for Perfection" anti-pattern for every eligible company.

When triggered:

1. The company receives one additional red flag.
2. The existing total red-flag count increases by one.
3. The detected anti-pattern appears in Stock Details.
4. Existing red-flag filters automatically incorporate it.
5. Companies with this warning can be excluded using Red Flags = 0.

At completion, provide:

- Summary of implementation.
- Files modified.
- Exact calculation logic.
- Confirmation of integration with the existing red-flag count.
- Confirmation of integration with filtering.
- Shopify and Astera Labs validation results.
- Test results.
- Any limitations or unavailable data.

Do not stop at a proposed implementation plan.

Inspect the codebase, implement the functionality, and run the relevant tests.