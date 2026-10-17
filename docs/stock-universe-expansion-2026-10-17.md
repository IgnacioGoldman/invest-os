# Stock universe expansion — 17 October 2026

The app now contains 200 active stocks: the original 77 plus the 123 selected in
[the revenue research](research/revenue-expansion-2026-10-17/shortlist.md). The
historical starting universe is saved alongside that research as
`base-universe.json`.

All 123 additions completed a full local bootstrap without failures. Their
financial statements, daily price histories, current financial and valuation
metrics, and deterministic derived signals are saved in SQLite. A subsequent
200-stock price refresh verified 123 unchanged histories and updated 77. All
exported current prices and latest chart candles agree on 16 October 2026, the
latest completed session.

The local database contained older revenue histories for nine original stocks.
The verified published fundamentals for the original 77 were merged into SQLite,
preserving local history and current prices, before the final export. Revenue
momentum is calculable for all 200 stocks: 99 Accelerating, 60 Decelerating, and
41 Stable. Each of the 123 additions retains the qualifying revenue growth from
the research screen.

Reviewed house peer classifications cover all 200 stocks. Industry Relative
Strength is available for 90; the others explain insufficient comparable peers
or an unsupported market. Peer groups were not broadened solely to meet the
five-other-company requirement. The original peer assignments are preserved.

The coverage audit identifies unresolved current inputs in 29 stocks. Metrics
that are missing or mathematically not meaningful remain unavailable with their
source notes. A completed collection does not imply every financial ratio exists
or that companies with strong revenue growth are profitable.

## Mobile delivery

`open-data/stocks.json` is a compact screening index of approximately 14.1 MB,
or 1.33 MB using gzip. It retains current metrics, ten revenue quarters, the latest
quarterly fundamentals, two annual periods, and the source context needed by AI
briefs. Complete histories and industry comparison charts are in 200 individual
`open-data/snapshots/{SYMBOL}.json` files, fetched when a stock opens. Price
histories remain separate. All full financial snapshots total approximately
89 MB before compression.

Stock details use a bounded, timestamp-keyed cache, reject a response for the
wrong stock or dataset revision, and provide a retry after a failed request.
Filters, sorting and ten-stock pagination work from the initial index. Local
repair and price-fallback paths resolve full snapshots before saving, preventing
the smaller screening history from replacing durable financial history.

## Validation

- 200 active SQLite snapshots, 200 screening rows, 200 full detail files and 200
  exported price histories; original 77 and selected 123 match exactly.
- SQLite integrity quick check passed; derived signals rebuilt for all active
  stocks.
- Refresh validation passed with no price, valuation-input consistency or asset
  mismatches.
- Frontend and Python revenue momentum agree across 18 regression scenarios and
  every exported stock; all 200 have complete six-quarter windows.
- 134 Python tests and five frontend stock-metric/filter tests passed; production
  TypeScript/Vite build passed.
- Mobile and desktop browser checks cover the company count, pagination, search,
  new and existing stock details, full industry charts, detail caching and
  recovery from a failed detail request.

Scheduled refreshes use the expanded universe and regenerate both the screening
index and full details. Deployment validates every linked detail asset before
publishing. This release also carries forward the pending issuer-discovery and
refresh-verification reporting fixes described in the
[refresh audit](refresh-audit-2026-10-17.md).
