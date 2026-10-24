# AI brief copy format

The analysis instructions remain in `frontend/src/prompts/stock-analysis.md` and are copied unchanged apart from the company, prepared date and filter-name placeholders. Investment analysis, scores, tags, output table and research requirements are not shortened by the data formatter.

`frontend/src/aiBriefData.ts` builds a compact copy of each selected snapshot:

- Each retained financial fact appears once, with reported/computed/proxy status and as-of metadata. Duplicate aliases and parallel raw/screening/valuation copies are removed.
- Source identifiers appear once per stock in a `sources` list. Each fact references that list using 1-based indices; source identifiers themselves are preserved.
- Up to 10 revenue quarters, eight fundamental quarters and two annual periods are retained, matching the previous history windows. Available revenue, gross profit, operating income, net income, cash flow, capex, cash, debt, equity, diluted shares and EPS remain in the histories. There is no new provider request to fill missing history.
- Monetary amounts and share counts are expressed in millions. Prices and EPS remain per share; percentages, percentage points and ratios remain unscaled. Values are rounded to seven significant digits, preserving small non-zero values. Currency overrides, proxy/FX cautions and quarter/TTM distinctions are retained.
- Red-flag counts, lower bounds, coverage, triggered formulas and calculated inputs are kept. Duplicate copies of all the underlying evidence rows are replaced with source references. Missing or incomplete assessments remain unknown.
- Accounting warnings, source gaps, dated quote/support/earnings context and three recent filing links are retained. Filing metadata is not represented as reviewed filing contents.
- Generic repeated collection notes, unavailable-value objects, redundant valuation inputs, every price-return timeframe, JSON indentation and duplicate metric aliases are omitted. Invalid forward P/E and non-meaningful negative trailing P/E are not presented as usable valuation multiples; missing metrics and relevant cautions remain explicit.

A short data key accompanies the financial payload so an AI can interpret abbreviations, units and source references. The ready dialog shows the total character count before copying. The raw snapshots, calculations, full source metadata and financial histories stored by Invest OS are unchanged.
