# First-filter business performance

Invest OS identifies companies with interesting reported business performance. One compact, two-column Business Performance section contains these descriptive facts:

- [Revenue Growth YoY](latest-revenue-growth-yoy.md): Strong / Solid / Flat / Weak strength bands, percentage; signed-direction saved filters preserved.
- [Revenue Growth Momentum](revenue-growth-momentum.md): Accelerating / Steady / Decelerating, percentage points.
- [Revenue Growth Consistency](revenue-growth-consistency.md): Steady / Choppy, six to eight quarterly observations.
- [Operating Margin](operating-margin.md): Profitable / Loss-making, percentage.
- [Operating Margin Trend](operating-margin-trend.md): Improving / Stable / Declining, percentage points versus the same fiscal quarter last year.

It also exposes [Red Flag Count](red-flag-count.md), an optional derived count of four distinct concern groups with explicit assessment coverage and transparent evidence. Numeric custom filters can compare the five numeric metrics. A low concern count is not an investment-quality or valuation score.

Public inputs must have finite values, source identifiers, matching currency and fiscal periods. Recompute ratios and compare actual year-ago dates. Reuse the existing 140-day quarterly-report freshness policy. Green identifies growing revenue, accelerating revenue growth or improving operating margins; market-context cards remain neutral. Missing, stale, anomalous or non-comparable metrics are omitted entirely, including their detail panels. Cards never contain placeholder labels. No empty grid positions are reserved. Missing facts are never zero or ranked as zero. No composite quality or valuation score is generated.

The preserved price chart keeps all timeframe selectors. [Earnings](upcoming-earnings.md) appears only with a fresh sourced future date; [support](support.md) appears only with a valid detected zone and compatible fresh quote. These sit in Market Context, separate from business performance. Unavailable context cards are omitted.

Removed from all first-filter cards and selectable filters:

- [Free Cash Flow Margin](dropped/free-cash-flow.md)
- [Forward P/E](dropped/forward-pe.md)
- [Balance Sheet / Cash / Debt](dropped/balance-sheet.md)
- [Gross Margin, Price/Sales and FCF Yield / former Financial Details](dropped/financial-details.md)
- [GAAP EPS Growth YoY](dropped/gaap-eps-growth-yoy.md)
- [EPS CAGR 3Y](dropped/eps-cagr-3y.md)
- [Net Margin](dropped/net-margin.md)
- [ROE](dropped/roe.md)
- [ROIC proxy](dropped/roic-proxy.md)
- [PEG](dropped/peg.md)
- [Trailing P/E](dropped/trailing-pe.md)
- [EV/EBITDA proxy](dropped/ev-ebitda-proxy.md)
- [Industry Relative Strength](dropped/industry-relative-performance.md)

Existing retirement files are reused. The four newly retired root documents moved into `dropped/` with their previous methodology preserved. Raw reported values, all underlying research calculations, dates, fiscal periods, source identifiers and anomaly warnings remain in Analyze with AI. Source identifiers are provenance, not independent verification.

The shared backend projection in `backend/app/services/screening_metrics.py` supplies API loads, static exports and badge evaluation. The browser hides invalid or expired projected metrics before rendering cards. Saved filters referencing removed metrics or labels require editing and fail closed, even within OR groups; their removal never silently broadens a saved screen.
