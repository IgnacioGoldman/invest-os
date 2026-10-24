# Stock business-performance screening

Invest OS shows four deterministic first-filter facts: Revenue Growth YoY, Revenue Growth Momentum, Operating Margin and Operating Margin Trend. See the [metric index](metrics/README.md) for calculations, thresholds, confidence checks and retired metrics.

Business Performance is a compact two-column section. A missing, stale or non-comparable metric has no card or detail panel. The separate Market Context section shows only valid future earnings dates and detected support zones; chart timeframes remain unchanged.

Valuation, cash-flow, balance-sheet, earnings and return-on-capital interpretations are reserved for Analyze with AI. Their underlying figures, calculations, dates, periods, source identifiers and anomaly warnings remain exported. No subjective investment ratings or automatic quality scores appear in first-filter screening.

AI brief instructions live in [`frontend/src/prompts/stock-analysis.md`](../frontend/src/prompts/stock-analysis.md). Edit this Markdown file to change the requested analysis. `prepareStockAnalysis()` imports it as text through Vite's `?raw` loader, fills `{{subject}}`, `{{preparedAt}}` and `{{filterName}}`, and appends each selected company's JSON data. The brief preview and data assembly remain in `frontend/src/aiAnalysis.ts`. Prompt edits take effect after rebuilding and deploying the frontend.
