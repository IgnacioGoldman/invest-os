# Green flags

Three deterministic rules feed [Green Flag Count](../../green-flag-count.md). Each met rule contributes one point, with a maximum of three.

| Rule | Required history |
| --- | --- |
| [Sustained revenue growth](sustained-revenue-growth.md) | Eight revenue quarters to calculate four consecutive quarterly YoY comparisons |
| [Profitable growth](profitable-growth.md) | Sustained revenue growth inputs and four latest operating-income quarters |
| [Cash-backed earnings](cash-backed-earnings.md) | Eight quarters of net income, operating cash flow and capex |

The two growth rules overlap: Profitable growth also meets Sustained revenue growth. This is an explicit count of rules met, not a count of independent strengths or a weighted quality score. Green and red flags can coexist and do not cancel each other.

## Shared requirements

Rules use `historical_series.quarterly_fundamentals` and the same [accounting input checks as red flags](../../../../../backend/app/services/red_flags.py), implemented in the experiment-local `flag_facts.py`: consecutive unique fiscal quarters, compatible quarter-end dates and currencies, finite sourced reported facts, no proxies, and no conflicting comparable quarterly revenue. The latest report must be current, not superseded by a newer revenue report, and no more than 140 days old. Market quotes do not affect green-flag freshness.

Financial businesses, REITs and investment funds are outside this rule set. Missing classification, stale data, invalid denominators and unsupported inputs cannot establish a positive result or a zero count.

Each rule is `flagged` when met, `clear` when assessed but not met, or `unassessed` when its required inputs are unavailable or invalid. Excluded groups are `not_applicable`. A numeric count is published only when all three rules are assessed; partial assessments retain confirmed rules in `observed_count`. The experiment HTML shows a lower bound such as **≥2**, or **Not fully assessed** when no positive rule is confirmed. Green flags do not affect the existing financial-rule filter.

Calculations use unrounded values. Comparisons remove floating-point noise using `math.isclose(rel_tol=1e-12, abs_tol=1e-10)`. Equality qualifies for the 8% growth threshold and operating-cash-flow/net-income comparison, while break-even operating income and zero free cash flow do not qualify.

The 8% threshold is an initial screening heuristic. These rules describe reported patterns; they do not establish organic growth, durable competitive advantage, fair valuation or future returns.

Implementation: [green_flags.py](../../../green_flags.py). Regression coverage: [test_green_flags.py](../../../test_green_flags.py).
