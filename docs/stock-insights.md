# Stock business-performance screening

Invest OS shows four deterministic first-filter facts: Revenue Growth YoY, Revenue Growth Momentum, Operating Margin and Operating Margin Trend. See the [metric index](metrics/README.md) for calculations, thresholds, confidence checks and retired metrics.

Business Performance is a compact two-column section. A missing, stale or non-comparable metric has no card or detail panel. The separate Market Context section shows only valid future earnings dates and detected support zones; chart timeframes remain unchanged.

The built-in **test 1** filter requires Growing Revenue Growth YoY, Profitable Operating Margin, and Inside Support Zone or Near Support on **any** of the 1m, 3m or 6m timeframes. Missing or invalid support on another timeframe does not veto a valid match. It is available to guests and signed-in users, sorts alphabetically, and can be customized as a separate saved filter. New support conditions default to **Any selected timeframe**; the editor also offers **Every selected timeframe** and preserves existing saved filters that require all selected timeframes. Support conditions describe market context rather than investment quality.

Valuation, cash-flow, balance-sheet, earnings and return-on-capital interpretations are reserved for Analyze with AI. Their underlying figures, calculations, dates, periods, source identifiers and anomaly warnings remain exported. No subjective investment ratings or automatic quality scores appear in first-filter screening.

AI brief instructions live in [`frontend/src/prompts/stock-analysis.md`](../frontend/src/prompts/stock-analysis.md). Edit this Markdown file to change the requested analysis. `prepareStockAnalysis()` imports it as text through Vite's `?raw` loader, fills `{{subject}}`, `{{preparedAt}}` and `{{filterName}}`, and appends each selected company's JSON data. The brief preview and data assembly remain in `frontend/src/aiAnalysis.ts`. Prompt edits take effect after rebuilding and deploying the frontend.

The brief asks for investment analysis of every selected stock, with Business Quality and Valuation Attractiveness scores from 0 to 100 and a table ranked by their equal-weight average. It treats the supplied dataset as a starting point for additional sourced research when available. Scores are contextual AI judgments, kept separate from deterministic screening. The brief excludes reviews of Invest OS and requires material uncertainty and evidence gaps to be reflected in the investment rationale.
