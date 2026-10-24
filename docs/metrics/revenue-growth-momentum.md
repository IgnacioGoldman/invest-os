### Revenue Growth Momentum

Revenue Growth Momentum is best calculated from **six consecutive quarters of revenue growth YoY**, comparing the median of the latest three quarters with the median of the preceding three.

A comparison of only the last two quarters can mistake a recovery from one unusually weak quarter for sustained acceleration. The median is the middle growth rate after sorting each group of three. It reduces the influence of one unusually strong or weak quarter while allowing two quarters of changed growth to affect the signal.

Formula:

```text
Quarterly Revenue Growth YoY % = ((Quarter Revenue / Same Quarter Last Year Revenue) - 1) * 100

Recent Median = median(Growth YoY Q[t-2], Growth YoY Q[t-1], Growth YoY Q[t])
Prior Median = median(Growth YoY Q[t-5], Growth YoY Q[t-4], Growth YoY Q[t-3])

Revenue Growth Momentum (pp) = Recent Median - Prior Median
```

The result is a change in **percentage points (pp)**, not a percentage change in revenue or a percentage change in the growth rate. Each quarter contributes equally; the median is not revenue-weighted and does not measure aggregate six-month revenue growth.

For example, SYK's earlier three quarters grew 11.88%, 11.07%, and 10.25%, while its latest three grew 11.42%, 2.63%, and 9.42%. Their medians are 11.07% and 9.42%, respectively. Momentum is therefore **−1.65 pp: Steady**, even though the latest quarter rebounded **+6.79 pp** from 2.63% to 9.42%.

Why this matters: the main signal asks whether the company's typical growth pace has changed. The latest-quarter movement provides context about a rebound or sudden deterioration without replacing that broader trend.

### Tags

Revenue Growth Momentum describes changes in growth pace, not the absolute strength of growth or the stock's valuation.

- **Accelerating:** Recent median growth is at least 3 pp above the prior median.
- **Decelerating:** Recent median growth is at least 3 pp below the prior median.
- **Steady:** The median difference is strictly between −3 pp and +3 pp.
- **Hidden card:** Six consecutive quarters with finite, comparable revenue YoY growth are unavailable. Missing growth, missing quarters, duplicate quarters, or invalid fiscal periods prevent calculation. Older valid quarters never replace a missing quarter in the latest window.

These thresholds are a first-pass signal. Steady means the typical growth pace is within 3 pp of its earlier level; it does not mean every quarter was stable. A company can accelerate while revenue is still shrinking, or decelerate while revenue is still growing strongly.

### Latest-quarter movement

The latest-quarter change is shown separately:

```text
Latest-quarter Change (pp) = Growth YoY Q[t] - Growth YoY Q[t-1]
```

- **Rebounding:** The latest change is at least +3 pp, the previous growth rate was at least 3 pp below the prior median, and the latest growth rate is within 3 pp of the prior median. This describes a return toward the earlier pace; it does not establish why the dip occurred or whether lost sales were recovered.
- **Improving:** The latest change is at least +3 pp and the rebound conditions are not met.
- **Weakening:** The latest change is at most −3 pp.
- **Steady:** The latest change is strictly between −3 pp and +3 pp.

This supporting label does not affect momentum filters, sorting, or the primary tag. Both changes use unrounded values for classification and display rounded to two decimal places. Expandable evidence identifies all six quarters used in the calculation.

### Data updates and validation

The shared backend screening projection recomputes momentum from validated `historical_series.quarterly_revenue` inputs. The TypeScript implementation preserves the same six-quarter formula and is checked for parity. New quarterly data changes the window on the next projection rebuild; the browser rechecks its freshness deadline before rendering.

GitHub Actions evaluates saved-filter badges using the matching Python implementation in `backend/app/services/revenue_growth_momentum.py`. Deployment and data-refresh workflows run `scripts/validate_revenue_growth_momentum.py` to compare both implementations across regression scenarios and every exported symbol before publishing. The validator records unavailable symbols and their reasons without inventing missing observations or rejecting otherwise usable stock data.

Run the same validation locally:

```sh
python3 scripts/validate_revenue_growth_momentum.py --output /tmp/revenue-growth-momentum-report.json
```

SEC fact fiscal-year and quarter labels can describe the filing that contains a comparative observation. The collector validates them against actual statement dates and the issuer's fiscal calendar before grouping quarters, deriving Q4, or matching prior-year revenue. YoY comparisons must also have dates approximately one year apart.

AZN, Barrick (B), Novartis (NVS), and YPF use durable, source-linked quarterly revenue facts in `data/stocks/issuer_facts/` to supplement sparse SEC histories. These contain reported consolidated revenue in USD, with a consistent company-specific revenue definition. New issuer reports are checked at most weekly; failed downloads or unrecognized tables retain verified history. Six consecutive YoY growth observations generally require ten consecutive quarterly revenue amounts.

The daily refresh includes `--repair-revenue-history`: it upgrades older revenue histories once and retries remaining unavailable momentum windows at most weekly even when filings have not changed. Price refreshes preserve newer repaired revenue histories rather than restoring an older deployed snapshot. Corrected fiscal labels supersede older labels for the same reporting date.

To preview or apply a rebuild using downloaded SEC facts:

```sh
python scripts/backfill_revenue_history.py --facts-dir .cache/open_data
python scripts/backfill_revenue_history.py --facts-dir .cache/open_data --apply
```

The rebuild checks for momentum coverage regressions, updates the latest revenue growth card and its alias together, and preserves existing prices. It does not refresh other financial metrics; a normal fundamentals collection computes those from the normalized facts.

The median deliberately responds more slowly than a two-quarter comparison. One new strong quarter is early evidence, not enough on its own to establish sustained acceleration. One weak quarter still matters economically even when it has little influence on the median, so read this signal alongside the six quarterly observations, latest movement, and revenue growth YoY.

## Research screening confidence

The card displays its signed percentage-point value and Accelerating / Steady / Decelerating label. Calculation classification remains metadata for AI, not a visible Computed Metric badge. Preserve six fiscal periods, source identifiers and the formula. The latest comparable quarter must also pass the revenue input checks. No investment score is derived. The ±3 pp thresholds are the existing documented product rules, not newly fitted thresholds. Green means accelerating revenue only.

The first-filter projection recomputes every YoY observation from comparable public revenue amounts, requiring approximately ten consecutive quarterly amounts. The latest report must pass the same 140-day freshness rule as Revenue Growth YoY. Missing, stale, duplicate, currency-incompatible or anomalous inputs hide the card entirely; no placeholder or numeric zero is inserted.
