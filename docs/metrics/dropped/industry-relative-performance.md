# Industry Relative Strength — retired from screening

Definition: Equal-weight tracked peer one-year price return minus market benchmark return, in percentage points.

Dropped because: Sparse peers, a selected universe, inconsistent industry classification and calendar/currency gaps distort comparisons.

Typical misleading situations: Sparse peers, a selected universe, inconsistent industry classification and calendar/currency gaps distort comparisons.

Reconsider only with: Reviewed stable classifications, representative peer coverage and a documented robust benchmark/currency methodology.

Excluded from default cards, saved-filter matching, rankings, composite scores and automatic positive/negative ratings. Raw source facts and historical calculations remain available to AI research. Saved filters using retired fields are disabled until edited, including OR expressions; they are never silently broadened.

See the [metric index](../README.md) for the current policy.

<details>
<summary>Historical methodology (inactive)</summary>

### Industry Relative Strength

Stock detail metric showing industry price context, with neutral styling and a supporting stock-versus-industry comparison.

_How has the stock's industry performed compared with the wider market?_

Industry Relative Strength compares the **equal-weight average 1-year price return of the stock's tracked industry peers with the 1-year price return of a relevant broad-market benchmark**. Exclude the selected stock from the peer basket. The result is shown in **percentage points (pp)**. The stock's own return versus its industry is supporting context in the detail panel.

The card uses **1Y as its fixed period**. It gives a longer view of relative performance than 3M, which is more sensitive to a recent earnings release or short-term move. Changing the stock's main price-chart range does not change this card's period or tag.

Formula:

```text
Stock Return % = ((Stock End Close / Stock Start Close) - 1) * 100
Peer Return % = ((Peer End Close / Peer Start Close) - 1) * 100

Industry Return % = sum(Eligible Peer Returns %) / Eligible Peer Count

Market Return % = ((Market End Level / Market Start Level) - 1) * 100

Industry Relative Strength (pp) = Industry Return % - Market Return %
Stock vs Industry (pp) = Stock Return % - Industry Return %
```

Every eligible peer contributes equally, regardless of company size or share price. Exclude the selected stock from the industry average so the card describes the performance of other tracked companies in its industry.

For example, if MU's tracked semiconductor peers gained an average of 30% and the broad market gained 15%, the card shows **+15 pp: Ahead of market**. If MU gained 18%, the detail panel also shows that MU trails its tracked industry by 12 pp. These are illustrative values, not current market data.

### Tags

Tags describe relative industry price performance over 1Y. They do not assign investment quality, valuation, or a buy/sell verdict. Use unrounded values to assign tags.

| Tag | Value | Meaning | Visual tone |
| --- | --- | --- | --- |
| **Ahead of market** | At least +5 pp | The tracked industry's return is at least 5 percentage points above the broad-market benchmark. | Gray |
| **In line with market** | Strictly between −5 pp and +5 pp | The tracked industry's return is within 5 percentage points of the broad-market benchmark. | Gray |
| **Behind market** | At most −5 pp | The tracked industry's return is at least 5 percentage points below the broad-market benchmark. | Gray |
| **Unclear** | No reliable comparison | The classification, comparable price history, or peer coverage is insufficient. | Gray |

The ±5 pp boundaries are first-pass product thresholds, not statistically established significance levels or predictions of future returns. All four tags use the existing neutral status tone, dot, and label. Green, yellow, and red do not grade this comparison. Direction is communicated by the signed value and tag wording; missing data also includes an explicit reason in the detail panel.

A positive result does not necessarily mean the industry rose. An industry down 10% against a market down 25% is ahead by +15 pp. An industry up 20% against a market up 35% is behind by −15 pp. The detail view must show both absolute returns so relative strength is not mistaken for a rising industry.

### Display

Place the card after **Proximity to Support**, using the same clickable metric card, typography, active state, and spacing as the other stock detail metrics:

```text
Industry Relative Strength
+15 pp
● 1Y · Ahead of market
```

Keep the numerical value white, including negative values, and the status dot and label gray for every tag. Keep the normal card background and border; selection may use the same blue active state as other metric cards, independent of performance. Display a sign for nonzero results and up to two decimal places, consistent with Revenue Growth Momentum. Missing values show `-` with `1Y · Unclear`; never substitute zero. Keep the same neutral treatment for this comparison's figures in the detail panel.

Selecting the card opens its explanation in the existing inline metric detail panel. Follow the same **Metric definition → question → explanation → Current value → tag** structure used by the other metrics, then show:

1. **Calculation:** Tracked industry return, market return, and their difference; for example, `Semiconductors +30% − market +15% = +15 pp`. Show the stock's own return and its difference from the industry separately: `MU +18% − tracked peers +30% = −12 pp`.
2. **Peer group and market:** The reviewed industry name, eligible peer count out of the total tracked peers, named broad-market benchmark, comparison dates, and data update date. Label the industry basket **Tracked industry average**.
3. **Comparison chart:** Stock, the same eligible peer basket, and the market benchmark, each starting at 100 on the same start date. The basket starts with equal allocations and holds that initial basket through the period, so its final return matches the arithmetic average used by the card. Use distinct non-evaluative line colors and explicit labels; color identifies each series, not good or bad performance.
4. **Companies included:** A sortable list of peer names, tickers, and 1Y returns, with the selected stock shown separately. Explain exclusions and allow opening a peer's stock detail.
5. **Method:** Equal weight, selected stock excluded, price returns excluding dividends, classification source, and a link or disclosure for the calculation rules. If unavailable, explain the specific missing input in this panel.

### Peer selection and data

The metric uses the explicit **sector → industry** mapping in `data/stocks/industry-classifications.json`, covering the current 77 tracked stocks. These are Invest OS business peer groups, not licensed GICS classifications. Financials is a broad sector; Investment Managers is an industry. MU uses Semiconductors; a narrower memory-chip group would need its own classification and sufficient coverage. The mapping retains original labels, the review date, market, currency, and source references for documented business-model corrections. New or changed input classifications show Unclear until the mapping is reviewed.

The application prefers raw classifications saved in `data/stocks/stocks.json`. The universe builder can import Nasdaq classifications, normalizing some sector names; Yahoo Finance supplies fallback metadata in some collection paths. Their original per-stock vendor provenance was not recorded, and the mapping explicitly preserves that limitation. Business groups normalize software labels, separate Strategy's digital-asset treasury from software, split semiconductor equipment from chipmakers, and distinguish financial-data providers, lenders, and payment networks. These overrides affect this metric's comparison groups and retain the original snapshot labels.

Use the full tracked universe, independently of search, filters, and personal watchlists. Deduplicate issuers and share classes. Require at least **five eligible other companies** in the reviewed industry. With fewer peers, show Unclear and explain the coverage gap. Do not silently substitute a broader sector or the entire universe.

The current universe is a selected stock sample. Its average describes **tracked peers**, not every listed company in the industry. For example, BX currently has no other Investment Managers peers in the local dataset, so it would show Unclear until coverage expands.

All returns use the same date window: end on the selected stock's latest saved session, and start on the last benchmark market session on or before the date one calendar year earlier (February 28 for a leap-day anniversary). The start must be within seven calendar days of that anniversary. Every included peer and the market benchmark must have positive, finite closes at the same endpoints. Peers need at least 200 sessions and 90% of benchmark sessions; the stock, eligible basket, and market must also share at least 200 sessions and 90% coverage for the chart. A short-history stock cannot substitute its since-listing return for 1Y. Missing data excludes a peer and is reflected in the coverage count.

The current version supports US-listed, USD-quoted peer groups. Other markets, including the two Stockholm listings, show Unclear until a compatible benchmark is configured. Broader comparisons require an explicit currency-conversion and calendar-alignment policy. Prices older than seven calendar days or dated in the future are unavailable; dates are shown in the panel. Price returns use saved daily closes, excluding cash dividends, matching the current price-chart basis. Price-source collection remains responsible for comparable split-adjusted closes.

The market benchmark is the **S&P 500 price index (`^GSPC`, USD)**, sourced through Yahoo Finance/yfinance and persisted in `data/stocks/benchmarks/sp500.json`. It represents a US large-cap market reference, not the same weighting or constituent set as the tracked industry basket. Both sides use price returns. The index must cover the stock's latest saved session; a missing or outdated index does not shift the comparison to an older end date. See the [S&P 500 index description](https://www.spglobal.com/spdji/en/indices/equity/sp-500/) and [Yahoo history](https://finance.yahoo.com/quote/%5EGSPC/history/).

### Refreshes and validation

The shared Python implementation is `backend/app/services/industry_strength.py`. It builds each stock's `industry_relative_strength` snapshot field from the full active universe, saved daily price histories, explicit classification mapping, and persisted benchmark history. It recalculates the complete trailing year every time; it does not update only once per year or reuse a cached percentage.

- **Price refresh:** `scripts/refresh_static_prices.py` refreshes the benchmark, updates stock histories, recalculates all industry comparisons, and saves them to SQLite and static JSON. SEC requests are disabled for benchmark collection too.
- **Fundamentals refresh:** `scripts/open_data_poc.py` rebuilds all comparisons after saved collection, including unchanged SEC stocks. It refreshes the index independently while preserving the saved stock prices used by the scheduled fundamentals flow.
- **Static export:** `scripts/export_static_site_data.py` independently rebuilds comparisons from the exported universe and saved histories using the persisted benchmark, without a network request.
- **Local app:** full and individual stock refreshes rebuild saved industry comparisons.

Both scheduled workflows commit the benchmark history with the updated SQLite database and static stock data. Failed or empty benchmark downloads retain previously saved history; an unusable or stale baseline yields Unclear instead of retaining an old gap. The browser also suppresses a comparison if its end date no longer matches the stock price date or is stale.

Rebuild the metric without recollecting company fundamentals or stock prices:

```sh
.venv/bin/python scripts/refresh_industry_strength.py
# Use only the saved index history:
.venv/bin/python scripts/refresh_industry_strength.py --no-fetch
```

Run the regression checks with `.venv/bin/python -m unittest discover -s scripts -p 'test_industry_strength.py'`. They cover averaging, benchmark subtraction, tag boundaries, negative absolute returns, issuer deduplication, classification changes, currency and history exclusions, stale data, cache retention, and recalculation during database rebuild and static export.

### How to use it

Read this metric alongside revenue growth, earnings, free cash flow, support, and valuation. An industry ahead of the market has shown relative price strength, but that does not establish that a particular stock is attractive. An industry behind the market can contain recovery opportunities or deteriorating businesses; the price comparison alone does not establish which. These are contextual observations, so the card and its tags stay neutral.

The supporting stock-versus-industry gap helps frame research questions: why has the company led or lagged peers, and do reported fundamentals support that difference? It does not automatically make a lagging stock a bargain or a leading stock overpriced.

This metric does not measure whether a stock or industry is cheap or expensive. Industry valuation needs suitable fundamental ratios and comparable valuation history. The analysis brief includes the industry-versus-market gap, stock-versus-industry gap, all three absolute returns, period, peer coverage, benchmark identity, dates, and limitations. Chart points are omitted from the brief to keep it compact. The metric does not automatically change the existing valuation or business-quality scores.

</details>
