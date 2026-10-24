# Balance Sheet — removed from first-filter screening

Cash, investments and debt require interpretation of liquidity, restrictions, leases and borrowing scope. Net cash is not a first-filter business-performance signal.

Raw financial figures, calculation code, fiscal periods and source identifiers remain available to Analyze with AI. Excluded from visible cards, filters, presets, rankings and automatic scores. See the [metric index](../README.md).

<details>
<summary>Previous research methodology (not a screening card)</summary>

# Balance Sheet

Reported Facts (or identified computations): cash and cash equivalents, short-term investments, long-term investments and debt, each with its exact source tags, date, currency and scope. Unknown components remain Unknown, never zero.

Cash means unrestricted `CashAndCashEquivalentsAtCarryingValue` or `CashAndCashEquivalents`. Restricted-cash aggregates and cash-plus-investment aggregates are excluded from cash equivalents but preserved under explicit raw research keys. Short-term and long-term investment tags are shown separately; neither establishes liquidity. Strategic and illiquid holdings never enter net cash.

Computed Metric: `cash and cash equivalents − complete debt`, only with the same balance-sheet date and currency, nonnegative values, precise cash scope and an explicitly complete debt tag/component set. Partial debt (including long-term debt alone), lease-only inputs, or ambiguous aggregates give Needs Review for net cash/debt while retaining the component amounts. Even a complete tag requires examination of the filing's leases and borrowing definitions. All tags and component notes remain visible; no investment-quality rating is assigned.

The collector prefers short-term borrowings plus current/noncurrent long-term debt when all are available. Reported debt may have a narrower scope; disclose the tags rather than silently calling it total debt. Source identifiers do not establish independent verification.

</details>
