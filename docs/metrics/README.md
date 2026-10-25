# Metrics

Metric documentation is organized into two groups:

- **Signals** have deterministic classification rules and tags. Their existing content and classification behavior are preserved.
- **Contextual metrics** are financial indicators that require business, industry, accounting or valuation context. They have no deterministic classification tags. For example, Forward P/E of 40 does not automatically mean Expensive, and 10 does not automatically mean Cheap.

## Signals

- [Operating Margin Trend](signals/operating-margin-trend.md)
- [Operating Margin](signals/operating-margin.md)
- [Red Flag Count](signals/red-flag-count.md)
- [Revenue Growth Consistency](signals/revenue-growth-consistency.md)
- [Revenue Growth Momentum](signals/revenue-growth-momentum.md)
- [Revenue Growth YoY](signals/revenue-growth-yoy.md)
- [Support](signals/support.md)
- [Upcoming Earnings](signals/upcoming-earnings.md)

Business-performance signals remain visible by default in stock details. Earnings and support retain their existing Market Context placement and deterministic tags. Missing, stale, anomalous or non-comparable signal metrics remain omitted. Numeric custom filters and Red Flag Count retain their existing behavior and coverage requirements. A low concern count is not an investment-quality or valuation score.

## Contextual

- [Balance Sheet / Net Cash](contextual/balance-sheet.md)
- [EPS CAGR 3Y](contextual/eps-cagr-3y.md)
- [EV / EBITDA Proxy](contextual/ev-ebitda-proxy.md)
- [Financial Details](contextual/financial-details.md)
- [Forward P/E](contextual/forward-pe.md)
- [Free Cash Flow Margin](contextual/free-cash-flow.md)
- [GAAP EPS Growth YoY](contextual/gaap-eps-growth-yoy.md)
- [Industry Relative Strength](contextual/industry-relative-performance.md)
- [Net Margin](contextual/net-margin.md)
- [PEG (historical growth proxy)](contextual/peg.md)
- [ROE (annualized quarterly)](contextual/roe.md)
- [ROIC Proxy](contextual/roic-proxy.md)
- [Trailing GAAP P/E](contextual/trailing-pe.md)

Stock details offer a collapsed **Contextual metrics** control. Expanding it reveals additional cards using the same layout as signals. Selecting a card opens its question, description, calculation, dates, sources, limitations and a neutral chart at the bottom. Missing values show an em dash with an explanation. Missing comparable history is stated explicitly; historical observations are never fabricated. Annual, quarterly and TTM bases are labeled separately.

Contextual definitions are separate from the signal/filter registry. They do not restore retired saved-filter rules, presets, rankings or automatic scores. Saved filters referencing removed metrics or labels still require editing and fail closed, including OR groups. Raw reported values, underlying research calculations, dates, fiscal periods, source identifiers and anomaly notes remain available to Analyze with AI. Source identifiers are provenance, not independent verification.

The shared backend projection in `backend/app/services/screening_metrics.py` supplies validated signal metrics and contextual research calculations to API loads and static exports. The frontend uses those projections where available, retaining their input requirements, including the seven-day forecast/quote policy for Forward P/E. Additional saved contextual figures come from the existing raw research data. Their reporting dates and limitations are shown without classification tags.
