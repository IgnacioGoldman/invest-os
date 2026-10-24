# Research screening metrics

Invest OS identifies stocks worth researching; no standalone metric establishes investment quality or a buy/sell conclusion. Raw facts remain available for AI research. Metric categories are Reported Fact, Computed Metric and Estimate. Preserve source identifiers, dates, fiscal periods, formulas and warnings; provenance is not independent verification. Unknown/Needs Review never scores as zero. Composite investment and valuation scores are disabled.

Six default financial cards:

- [Revenue Growth YoY](latest-revenue-growth-yoy.md)
- [Revenue Growth Momentum](revenue-growth-momentum.md)
- [Operating Margin](operating-margin.md)
- [Free Cash Flow Margin](free-cash-flow.md)
- [Forward P/E (Estimate)](forward-pe.md)
- [Balance Sheet](balance-sheet.md)

[Earnings](upcoming-earnings.md) and [support](support.md) are neutral context beside the preserved price chart. [Financial Details](financial-details.md) contains Gross Margin, Price/Sales and FCF Yield.

Retired from screening and scoring (raw figures preserved):

- [GAAP EPS Growth YoY](dropped/gaap-eps-growth-yoy.md)
- [EPS CAGR 3Y](dropped/eps-cagr-3y.md)
- [PEG](dropped/peg.md)
- [ROE](dropped/roe.md)
- [ROIC proxy](dropped/roic-proxy.md)
- [Net Margin](dropped/net-margin.md)
- [Trailing GAAP P/E](dropped/trailing-pe.md)
- [EV/EBITDA proxy](dropped/ev-ebitda-proxy.md)
- [Industry Relative Strength](dropped/industry-relative-performance.md)

The existing GAAP EPS and Industry Relative Strength documents moved into `dropped/`, retaining their historical methodology in an inactive archive. Other retired metrics had no standalone Markdown files; their retirement documents were added here. New metrics were considered: share-count change, net-debt/FCF, FCF conversion and valuation/peer composites are not added to screening because denominator, period or coverage ambiguities would reintroduce the reliability problems. Raw share counts and cash-flow facts remain available for investigation.

`backend/app/services/screening_metrics.py` supplies API loads, static exports, saved-filter badges and derived research context. Cards and browser filters consume that same projection. Date-sensitive estimates are rechecked in the browser. Retired saved-filter rules fail closed (also within OR groups) until explicitly edited; missing values remain null and sort last.
