# Red Flag Count

## What it means?

_Which potential financial concerns appear in the company's reported data?_

Counts the concern groups detected across cash generation, operating profitability, the balance sheet and valuation. It helps identify areas that deserve a closer look. For example, a count of 2 means two of the four groups triggered a warning. Zero means none of these rules detected a concern in a complete assessment; it does not mean the investment has no risks.

## How is calculated?

`number of distinct concern groups with at least one detected flag`, from 0 to 4.

| Concern group | When it adds one flag |
| --- | --- |
| Cash generation | Positive trailing-12-month net income exceeds trailing-12-month operating cash flow at both latest quarter ends, or free cash flow is negative in each of two non-overlapping four-quarter periods. |
| Operating profitability | Operating margin falls versus the same quarter last year in both latest quarters, or operating income is negative in both latest quarters. |
| Balance sheet | Stockholders' equity is negative in the latest reported quarter. |
| Valuation: Priced for Perfection | Price-to-Sales is above 10× and Free Cash Flow Yield is below 2%. Both conditions must hold; exactly 10× or 2% does not trigger. |

Trailing twelve months means the latest four reported quarters. Free cash flow is `operating cash flow − absolute capital expenditure`. Price-to-Sales is `market capitalization / trailing-12-month revenue`; Free Cash Flow Yield is `trailing-12-month free cash flow / market capitalization × 100`. Both valuation ratios use the same market capitalization and compatible currencies. Sourced zero or negative free cash flow satisfies the low-yield condition; missing cash flow does not.

Each group contributes at most one flag, even if both of its branches trigger. A group is assessed when any branch is flagged or all its branches are clear. Cash conversion needs five quarters; persistent negative free cash flow needs eight. The margin comparisons need six quarters; operating losses need two. Valuation needs four aligned revenue and cash-flow quarters plus a fresh market capitalization.

The exact count is available only when all four groups are assessed. Partial coverage displays **≥N** when flags are known, or **Not fully assessed** when none can yet be confirmed. Numeric filters require a complete assessment.

Use source-linked, comparable public financial data with a latest report no older than 140 days and a market-cap snapshot no older than seven days. Financial businesses, REITs and investment funds are excluded from this rule set; missing or unsupported data never becomes a zero count. A valuation assessment can include the existing sourced market-cap estimate, with its estimation warning preserved.

## Tags

- **Complete assessment:** all four concern groups have been assessed; the displayed count is exact for this rule set.
- **Partial assessment:** some groups have been assessed; the displayed result is incomplete.
- **Not assessed:** none of the concern groups could be assessed from the available data.

These tags describe assessment coverage. Detected flags still need context: investment can explain negative cash flow, buybacks can explain negative book equity, and a high sales multiple with low cash yield does not establish overvaluation.
