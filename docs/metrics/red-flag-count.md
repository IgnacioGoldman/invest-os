# Red Flag Count

An integer **0–4**, adding one point per distinct, detected concern group. This is an explainable financial-warning count, not an AI score or an investment-quality rating. Zero means no flags detected by this rule set with complete coverage; it does not mean there are no investment risks.

## Rules (version 2)

| Concern group | Deterministic trigger | Required history |
| --- | --- | --- |
| Cash generation | **Either** positive TTM net income exceeds TTM operating cash flow at **both** latest quarter ends, **or** free cash flow is negative in **each** of two non-overlapping four-quarter periods. FCF = operating cash flow − absolute capex. | Five quarters for cash conversion; eight for persistent negative FCF. |
| Operating profitability | **Either** operating margin falls versus the equivalent prior-year quarter in **both** latest quarters, **or** operating income is negative in both latest quarters. Operating margin = operating income / revenue × 100. | Six quarters for the two YoY comparisons; two for operating losses. |
| Balance sheet | Latest reported quarter-end stockholders’ equity is negative. | One quarter. |
| Valuation: Priced for Perfection | **Both** P/S >10 and FCF yield <2%, strict boundaries. | Four aligned reported revenue, OCF and capex quarters; one fresh market-cap snapshot. |

Each group contributes at most one point, even when both its branches trigger. Weak cash conversion and negative FCF are therefore not counted twice; neither are declining margins and operating losses. Concern groups can still have related economic causes. The count is not a count of proven, independent root causes.

The original business rules use accounting sign and equality boundaries (zero, cash flow versus earnings), rather than universal debt multiples, P/E bands or an invented materiality percentage. Persistence windows are explicit policy choices to reduce single-period noise; they are not statistical guarantees. Comparisons ignore floating-point equality noise using relative tolerance 1e-12 and absolute tolerance 1e-10. Margin calculations require positive revenue and absolute margins no greater than 100%; direct operating-loss checks do not require revenue.

## Coverage and filtering

Every stock exposes `coverage` (`assessed`, `applicable`, `total`, `complete`), `checks`, detected `flags`, `observed_count`, `assessment_version`, source identifiers, periods, as-of dates and `valid_until` in `screening.metrics.red_flag_count`. A group's outcome is determined when any branch is flagged or all its branches are clear. A known flag determines that group's one-point contribution even if another overlapping branch is unassessed.

The numeric `value` is populated **only** when all four applicable groups are assessed using a current report. Otherwise it is `null`, never a manufactured zero. A partial assessment displays `≥N` when concerns are detected, or **Not fully assessed** when none can yet be confirmed, together with coverage. Details expose every group, the rule formulas, input values, source identifiers and reasons for missing coverage. Expired projections are hidden.

Numeric comparisons (`<`, `≤`, `=`, `≥`, `>`) require complete assessments, including when filtering for low counts. Missing, partial, stale, unsupported-sector or otherwise invalid assessments do not match. Sorting puts incomplete assessments after numeric values. New sort keys are saved in the existing expression JSON with a legacy-compatible database sort key; no database migration is required.

Custom filters also support numeric comparisons on the four existing business metrics. For example:

`Revenue Growth YoY > 15% AND Operating Margin > 15% AND Near Support on any selected timeframe AND Red Flag Count ≤ 1`.

Label-based saved filters and existing support ANY/ALL rules retain their meaning. Numeric operators and thresholds survive saving and editing. Default filter **test 1** is unchanged; the count is optional, not an automatic exclusion or ranking score.

## Validation and limitations

Existing `quarterly_fundamentals`, the saved quote and market capitalization are used. No new provider, AI call or fabricated missing value is introduced. Inputs require finite numbers, supported public source identifiers, exact/computed public-fact tiers, compatible monetary currencies, matching metric/row dates and unique fiscal periods. Proxy statement inputs are rejected. The existing sourced listing-share market-cap estimate is permitted with its estimation warning preserved; this does not validate an analyst forecast or a model-generated market cap. Windows require consecutive fiscal quarters, 60–120 days between quarter ends and 350–380 days between year-ago dates. Conflicting same-quarter revenue series invalidate the margin branch. A new price quote cannot refresh financial history: the latest report must match the latest saved revenue/fundamentals report and be no more than 140 days old.

Version 2 continues to exclude financial businesses, REITs and investment funds, and requires sector/industry classification. These businesses need different cash-flow, profitability and capital interpretations; exclusions are unassessed, never zero flags. The rules are deliberately limited:

- Cash conversion reflects accruals, working capital and non-cash gains as well as potential earnings-quality issues. Capital investment can explain negative FCF; growth businesses can intentionally operate at a loss.
- Negative book equity can arise from buybacks, distributions and accounting history. It is not an insolvency or excessive-leverage determination.
- Debt completeness, maturities and consistently sourced interest expense are inadequate for a general debt-stress rule. No universal debt/equity threshold is applied.
- Diluted weighted-average share series include derived Q4 differences and are not consistently split-adjusted. They cannot reliably establish material shareholder dilution. These inputs remain available for AI research.
- GAAP EPS volatility, one-off gains and valuation attractiveness require context; high/negative P/E is not automatically a flag. No claim is made that all possible earnings or valuation risks are covered.

The accounting distinction between earnings and operating cash flow is explained in the [SEC financial-statements guide](https://www.sec.gov/about/reports-publications/beginners-guide-financial-statements). [IAS 7](https://www.ifrs.org/issued-standards/list-of-standards/ias-7-statement-of-cash-flows.html) describes cash-flow classifications and the adjustment of profit for non-cash and working-capital effects. These sources explain the accounting context; they do not endorse this application's thresholds or persistence windows.

Implementation: `backend/app/services/red_flags.py`, shared through the existing screening projection for API loads, static exports, derived signals, custom filters and watchlist badge evaluation. Analyze with AI receives the same assessment and the original raw financial data through its existing snapshot payload.

## Priced for Perfection

`backend/app/services/valuation_metrics.py` centrally defines strict limits `PRICE_TO_SALES_LIMIT=10` and `FCF_YIELD_LIMIT=0.02` (fraction). It recomputes TTM revenue from the latest four reported quarters and TTM FCF as sum(OCF − abs(capex)), uses the same saved positive market capitalization for both ratios, and supplies both research financial details and the fourth concern group. FCF yield is displayed as a percent but compared as a fraction. Zero and negative FCF satisfy the low-yield condition when fully sourced. Missing FCF never becomes zero. Zero/negative TTM revenue cannot support P/S. Exactly 10× or 2% does not trigger.

The valuation group contributes exactly one additional point, not one per condition. It is separate from persistent negative FCF: the additional high-sales-multiple condition identifies a valuation exposure, whereas the existing cash group concerns reported cash generation over two years. Neither rule is rewritten. This warning is an initial screening heuristic, not proof of overvaluation; sector, business model and future performance require context. Forward P/E remains unchanged. No preset automatically excludes this warning.

The latest statement and quote must be current (140 days and seven days respectively). Complete counts expire at the earlier deadline; partial counts retain the report deadline and expose the missing valuation coverage. Four quarterly revenues/cash flows must share the listing currency. Where a reliable quarterly FX bridge is absent, this rule is unassessed rather than mixing converted TTM values with original-currency quarters. All source identifiers, quarter dates, market-cap date, ratios and input amounts remain inspectable.

Dated October 23, 2026 source fixtures validate SHOP at approximately 16.50× / 1.0743% and ALAB at 39.227× / 0.5868%; each adds one valuation flag. Tests also cover all strict boundaries, missing inputs, negative/zero FCF, currency mismatch, sector exclusions, deduplication and existing count/filter integration.
