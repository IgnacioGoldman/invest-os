# Forward P/E — Estimate — removed from first-filter screening

Forward P/E depends on forecast quality, horizon, adjustments and current price. It evaluates valuation rather than deterministic reported business performance.

Raw financial figures, calculation code, fiscal periods and source identifiers remain available to Analyze with AI. Excluded from visible cards, filters, presets, rankings and automatic scores. See the [metric index](../README.md).

<details>
<summary>Previous research methodology (not a screening card)</summary>

# Forward P/E — Estimate

`current listing share price / positive annual forward EPS estimate`.

Display only if EPS has an explicit identifiable annual forecast horizon (fiscal year or next twelve months), provider source, estimate-as-of date and listing currency. The price and estimate must be no older than seven calendar days and never future dated, using the existing market freshness policy. Show horizon, both dates, provider and formula. The seven-day estimate policy is conservative; it does not prove the forecast was revised recently. Bare Yahoo `forwardPE` or `forwardEps` lacks a forecast horizon in the current collector, so it is Unknown. Collection date alone is not an underlying analyst revision date.

The historical EPS CAGR extrapolation and an EPS reverse-engineered from a P/E are retained only as raw research data. They cannot supply the displayed estimate, including during price refresh or legacy-cache recovery. Missing, stale, loss-making, zero, currency-incompatible or undocumented inputs produce Unknown. No Cheap/Fair/Expensive label or valuation score is generated. Source identifiers do not establish independent verification or estimate reliability.

</details>
