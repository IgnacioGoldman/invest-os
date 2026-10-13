# Revenue Growth Momentum diagnosis — 13 October 2026

Diagnostic only. No application logic, snapshots, cached facts, or database records were changed.

## Resolution implemented after diagnosis

The user subsequently authorized implementation and publication. Fiscal-period normalization restores BX, CRM, ORCL, SPGI, and STX. Verified issuer revenue backfills restore AZN, B, NVS, and YPF through Q2 2026. All 77 stocks have calculable momentum after the repair. AZN is Decelerating (−5.33 pp), NVS is Decelerating (−10.48 pp), B is Accelerating (+48.11 pp), and YPF is Accelerating (+13.29 pp).

The implementation includes a weekly history-repair path, durable source provenance, issuer report parsers that reject unrecognized layouts, retention of verified facts on source outages, prevention of incorrect labels returning during history merges, and protection against older deployed data replacing repaired histories during price refreshes. Rebuilding historical revenue also updates its latest growth card and alias. Other financial metrics are recomputed by the regular fundamentals collector.

The full-universe rebuild also corrects previously calculable classifications affected by historical source periods and comparative facts: APP becomes Decelerating, AFRM becomes Stable, HON becomes Accelerating, and OXY becomes Stable. Coverage checks alone would not have identified these incorrect values.

The following sections preserve the original diagnostic findings and experimental results before implementation.

## Scope and verified result

Audited all **77 stocks in the deployed World universe**, not every listed company globally, from [the public stocks dataset](https://ignaciogoldman.github.io/invest-os/data/open-data/stocks.json). Its snapshot timestamp is `2026-10-13T02:08:27.601529Z`. The local export and active SQLite snapshots have the same nine Unclear symbols. All deployed quarterly revenue histories equal the corresponding local histories.

| Status | Stocks |
| --- | ---: |
| Accelerating | 37 |
| Stable | 16 |
| Decelerating | 15 |
| Unclear | 9 |

The TypeScript frontend and Python filter calculator agree across every deployed symbol and 18 regression scenarios. This confirms calculation parity; it does not validate the financial source periods.

## Every affected stock

| Symbol | Company | Observed problem | Repair needed |
| --- | --- | --- | --- |
| AZN | AstraZeneca | Eight revenue quarters, all Q2 from 2018–2025; the newest quarter is June 2025. The latest six observations are years apart. | Collect complete quarterly revenue history from issuer reports. |
| B | Barrick Mining | Eight revenue quarters, all Q2 from 2018–2025. | Collect complete quarterly revenue history from issuer reports. |
| NVS | Novartis | Eight revenue quarters, all Q2 from 2018–2025. | Collect complete quarterly revenue history from issuer reports. |
| YPF | YPF | No quarterly revenue rows; cached revenue facts are annual. | Add a verified quarterly source in a consistent reporting currency. |
| ORCL | Oracle | August 2026 is tagged FY2026 Q1, colliding with August 2025. The latest fiscal sequence goes Q2, Q3, Q4, Q1 within FY2026. | Normalize periods using actual statement dates and Oracle's fiscal calendar. |
| CRM | Salesforce | January 2026 annual revenue is tagged FY2025; its derived Q4 appears after FY2026 Q3 as FY2025 Q4. | Normalize annual and quarterly periods before deriving Q4. |
| SPGI | S&P Global | December 2024 annual revenue is tagged FY2025 in a later comparative filing. FY2024 Q4 disappears and FY2025 Q4 has no YoY comparator. | Preserve distinct actual reporting periods when processing comparative facts. |
| STX | Seagate | June 2025 annual revenue carries inconsistent FY2027/FY2026 labels. FY2025 Q4 disappears; FY2026 Q4 has no comparator. | Normalize using actual fiscal boundaries, including 52/53-week years. |
| BX | Blackstone | June 2024 facts include a Q1 label despite their Q2 dates; comparative copies carry the later filing's FY. FY2025 Q2 has no comparable FY2024 Q2. | Normalize quarter identity before deduplication and YoY matching. |

## Why AZN is Unclear

The metric requires **six consecutive quarters of comparable revenue YoY growth**. It compares the median of the newest three growth rates with the median of the previous three. Six observations from different years are insufficient.

AZN's deployed latest six observations are FY2020 Q2, FY2021 Q2, FY2022 Q2, FY2023 Q2, FY2024 Q2, and FY2025 Q2. The continuity check correctly rejects this window.

Downloaded [AZN's live SEC Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000901832.json) during diagnosis. It exactly matches the cached source, so this specific gap is not caused by a stale local Company Facts cache. Recent revenue facts cover June and December year-ends; there is no complete consecutive quarterly sequence. The current extractor emits only the Q2 single-quarter observations from those facts.

AstraZeneca has already published [H1 and Q2 2026 results](https://www.astrazeneca.com/content/dam/az/PDF/2026/h1q2/H1-and-Q2-2026-results-announcement.pdf), dated 27 July 2026. Its [results archive](https://www.astrazeneca.com/investor-relations/results-and-presentations.html) includes quarterly reports missing from the app. This is a collection coverage problem; Unclear does not describe the company's growth performance.

The SEC's [API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) explains that Company Facts aggregates standard-taxonomy, entity-wide XBRL facts. Using it alone does not establish complete quarterly coverage for every issuer.

## The parser defect behind five other failures

`backend/app/entry_engine/open_data_metrics.py` copies raw `fy` and `fp` into `FactPoint` in `_parse_fact_point`, then `_quarterly_facts` groups direct quarters, YTD facts, and annual facts by those labels. Actual statement dates are not used to validate the fiscal identity before grouping. Comparative facts can carry a later filing's fiscal labels, and some cached rows also have inconsistent quarter/year labels.

Consequently, different actual periods collide. `_better_quarterly_fact` favors the later period end, which can remove the preceding year's quarter. Annual-minus-Q3 calculations can subtract facts from different actual fiscal years. `_matching_prior_year_quarter` trusts FY labels and does not require approximately one year between the compared dates.

This affects values as well as availability. Oracle's deployed latest-quarter growth is **45.37%**, comparing August 2026 against August 2024. With actual periods normalized, August 2025 is retained and that comparison becomes **29.61%**. These are diagnostic results from cached source facts, pending production validation.

## Controlled experiment

A temporary script copied the five affected SEC fact sets in memory, inferred fiscal identity from actual revenue annual statement start/end spans, and recomputed quarters through the existing engine. It changed metadata only; it did not change or invent any input revenue values. This is a diagnostic experiment for these five issuers, not a general production normalization algorithm.

| Symbol | Before | After metadata normalization | Experimental momentum |
| --- | --- | --- | ---: |
| BX | Unclear | Accelerating | +46.69 pp |
| CRM | Unclear | Accelerating | +3.46 pp |
| ORCL | Unclear | Accelerating | +9.49 pp |
| SPGI | Unclear | Stable | +0.83 pp |
| STX | Unclear | Accelerating | +14.56 pp |

All five regained six consecutive comparable growth observations. This demonstrates that additional revenue inputs are unnecessary for their currently failing windows. Applying an equivalent validated repair would increase calculable coverage from 68/77 to 73/77; AZN, B, NVS, and YPF would still need source backfills.

## Why ordinary refreshes do not resolve it

The daily Pages workflow passes `--repair-current-data`, not `--repair-data-gaps`. Incremental preflight therefore excludes historical momentum gaps from repair reasons and can preserve snapshots when SEC filings are unchanged.

The provider independently calls `fundamental_gap_reasons(snapshot, include_history=False)` before trying supplementary statements. A missing historical window alone does not trigger that fallback. AZN and YPF also have current metric gaps, so the history gate is not their only obstacle. An unchanged or incomplete primary source remains incomplete when downloaded again.

The momentum validator reports these symbols but intentionally permits deployment of otherwise usable stocks. Its successful run means frontend/filter parity, not full momentum coverage.

## Proposed repair order

1. Normalize actual fiscal periods before deduplication, YTD subtraction, and YoY matching. Preserve amendments/restatements for the same actual period, validate compatible starts and ends before subtraction, and reject comparisons separated by the wrong number of years. Add regression cases covering the five real failures, comparative filing labels, non-calendar fiscal years, and 52/53-week calendars.
2. Rebuild affected snapshots from canonical source periods. The existing `retain_verified_history` merges by `(period, as_of)`; corrected labels could otherwise coexist with retained incorrect labels for the same date and keep breaking continuity. Recompute cards, history, and flattened aliases together.
3. Backfill AZN, B, NVS, and YPF from verified issuer statements. Six consecutive YoY observations normally require **ten consecutive quarterly revenue amounts**, because each of the six quarters needs its prior-year comparator. Maintain the same revenue definition and reporting currency across the complete window. AZN's deployed series uses `RevenueFromSaleOfGoods`, while the current engine prefers total `Revenue` when available; a backfill must reconcile that definition rather than mix the two.
4. Add a bounded history-repair path independent of current card completeness and new filing detection. Record attempts and back off for structurally sparse sources rather than repeating an ineffective full download every day.
5. Show the specific missing-period or source reason and latest financial period beside Unclear. Track coverage regressions separately from frontend/backend parity. A price-refresh timestamp does not establish fresh financial statements.

Issuer backfill candidates already publish archives: [AstraZeneca](https://www.astrazeneca.com/investor-relations/results-and-presentations.html), [Novartis](https://www.novartis.com/investors/financial-data/quarterly-results), and [Barrick](https://www.barrick.com/investors/quarterly-reports/default.aspx?LanguageId=1). No YPF fallback has been validated during this diagnosis.

## Reproduction and artifacts

Production calculation parity was checked with:

```sh
.venv/bin/python scripts/validate_revenue_growth_momentum.py \
  --stocks /tmp/invest-os-deployed-stocks.json \
  --output /tmp/invest-os-momentum-deployed-validation.json
```

Additional diagnostic artifacts:

- `/tmp/invest-os-momentum-deployed-audit.json`: all nine affected symbols, reasons, and recent source observations.
- `/tmp/invest-os-momentum-normalization-debug.py`: the temporary, read-only experiment.
- `/tmp/invest-os-momentum-normalization-debug.json`: metadata corrections and before/after calculations for the five parser failures.
- `/tmp/invest-os-azn-sec-current.json`: the live SEC source used to confirm AZN's coverage gap.

Temporary artifacts are local and may be removed by system cleanup. The diagnosis and proposed next steps are preserved in this document.
