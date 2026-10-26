# Reverse-engineering a quality/value/support filter

The desired entry set is **Strong or Solid business quality AND Cheap or Fair valuation AND at/near support on any timeframe**. The first two are the independent AI assessments, not existing deterministic labels. The existing Revenue Strong/Solid labels describe revenue growth, not overall business quality.

On the saved 23 October prices, 64 stocks are at/near at least one valid support zone. Only 15 also match both requested AI assessments; all 15 rank between #6 and #63, including 13 in the top 50. This is the exact tag-matching set for the saved review, not a claim of investment merit or future performance.

| Rank | Stock | Business quality | Valuation |
| --- | --- | --- | --- |
| 6 | ANIP | Solid | Cheap |
| 7 | BMY | Solid | Cheap |
| 8 | NVDA | Strong | Fair |
| 10 | NFLX | Strong | Fair |
| 21 | RGLD | Strong | Fair |
| 22 | PEP | Strong | Fair |
| 30 | UBER | Solid | Fair |
| 32 | GRND | Solid | Fair |
| 33 | RDDT | Solid | Fair |
| 41 | EVR | Solid | Fair |
| 42 | TGT | Solid | Fair |
| 43 | DTM | Solid | Fair |
| 44 | CLS | Solid | Fair |
| 59 | DUOL | Strong | Fair |
| 63 | ROAD | Solid | Fair |

## An implementable current-builder screen

Use all of the following:

1. Revenue Growth YoY **>0%**, rather than requiring the Strong/Solid growth bands.
2. Operating Margin **>0%**.
3. Red Flag Count **≤1**, requiring the builder's existing complete assessment.
4. Proximity to Support: **At Support OR Near Support**, with **ANY** of **1M, 3M, 6M, 1Y, 2Y, 5Y**. Apply AND between the four rules, OR within support choices/timeframes.

The exact existing-engine expression is [positive_growth_one_flag.json](positive_growth_one_flag.json). This is a broad shortlist for subsequent valuation review. It returns 33 stocks, including 12 of the 15 desired matches, ten top-50 stocks and three bottom-50 stocks. It cannot enforce Cheap/Fair valuation.

A zero-flag rule returns fewer stocks but excludes NVDA, NFLX and GRND, each of which has one observed concern in a complete assessment and received favorable quality/value tags. Allowing one concern is a deliberate review trade-off, not a declaration that the concern is immaterial.

BMY, RGLD and EVR fail the broader screen because coverage is incomplete; BMY and EVR also lack a validated operating-margin filter value. Their raw financial facts allowed an analytical assessment but do not satisfy the stricter filter's evidence contract. Keep a separate manual-review queue for incomplete data; never turn unknown coverage into zero flags.

## Contextual metrics worth considering

**FCF yield** is the most direct existing contextual candidate for valuation: cash generation relative to market price. **FCF margin** adds cash-generation context to profitability. **Trailing P/E** can be a secondary check where earnings are sustainable and attributable to the same equity shares. Their meanings are complementary; none is an AI Cheap/Fair classification.

Illustrative research thresholds, using the same broad current-builder screen above:

| Additional condition | Selected | Matches requested AI tags | Top 50 | Bottom 50 |
| --- | --- | --- | --- | --- |
| None | 33 | 12 | 10 | 3 |
| FCF yield ≥3% | 19 | 10 | 8 | 2 |
| FCF margin ≥10% and FCF yield ≥3% | 15 | 8 | 7 | 2 |
| Positive trailing P/E ≤30 and FCF margin ≥10% | 14 | 8 | 7 | 0 |

The last screen still admits GOOG, MU, WDC and FOUR with Unknown valuation, and CDE/CSCO with other mismatched assessments. Its lack of bottom-50 stocks is not the same as selecting only top-ranked stocks. It also misses RDDT, which the review rated Fair above 30x earnings, and lower-margin TGT/CLS/ROAD. The 3% cash-yield rule misses NVDA despite its favorable growth-adjusted assessment.

These contextual fields currently have **no filter registration**. The tests above are isolated numeric research predicates over the saved sourced values, not production-ready contextual validation. Enabling them requires adding optional numeric rules consistently across the frontend registry/builder, Python saved-filter evaluator, persistence/notifications and tests. Preserve the original metric definitions and source/freshness requirements. Do not convert warning-heavy or incompatible inputs into a usable valuation merely because a number is finite.

Data checks matter as much as thresholds. FOUR's implausible FCF yield stems from a share-denominator problem and passes a minimum-yield rule. GOOG's apparent low P/E is affected by non-operating earnings. Working capital, stock compensation, tax effects, capex timing, ownership attribution and sector differences can distort cash and earnings comparisons. The existing concern count does not exhaust those issues.

Do not use the current Forward P/E as an immediate workaround: all 200 frozen briefs lack a usable sourced, dated forward estimate. ROE and the saved ROIC/PEG/EV-EBITDA proxies also have denominator/accounting limitations; gross and net margins are not cross-sector quality guarantees.

## Closest implementation of the user's actual intent

Keep **investment qualification** separate from **entry timing**:

- Persist the reviewed Business quality and Valuation tags with their symbol, financial/price dates, prompt/model provenance and review status. Filter for Strong/Solid and Cheap/Fair using those explicit assessments.
- Apply the existing at/near-any-support condition as a daily timing overlay. A favorable company outside support remains on the qualification list for later monitoring.
- Sort qualifying entries by the saved AI rank. If the product definition literally requires the top 50, use an explicit rank limit; this produces 13 matches on this review, but it is a selection policy tied to that dated ranking.
- Reassess when financial inputs, price or the investment case materially change. An old Cheap/Fair assessment cannot automatically remain current through a large price move.

This path reproduces the desired 15-company cohort without pretending growth strength or a P/E cutoff encodes the AI's judgment. It requires exposing saved AI assessments as filterable fields; the existing app does not currently persist them as an automated screen.

All threshold comparisons are **in sample on one subjective review**, using much of the same evidence that informed the ranking. Do not tune cutoffs until they reproduce this table and then call the strategy validated. Freeze a proposed policy, evaluate later dates/unseen reviews, retain missing-data reasons and compare false inclusions/exclusions. Future return validation is a separate experiment.

Full results and expressions: [comparison.md](comparison.md), [evaluation.json](evaluation.json), [requested-cohort.csv](requested-cohort.csv). No production filters or application code were changed.
