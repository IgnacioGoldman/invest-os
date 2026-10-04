# Stock Data Refresh

Current flows:

`On demand: committed static JSON -> GitHub Pages`

`Daily: tracked SQLite -> SEC recent-submissions gate -> changed SEC tickers only -> tracked SQLite -> static JSON -> commit tracked data -> GitHub Pages`

`Every four hours: tracked SQLite + deployed JSON fallback + recent prices -> tracked SQLite + updated static JSON -> commit tracked data -> GitHub Pages`

## 1. GitHub Actions fetches the content

Both workflows read the universe from `data/stocks/stocks.json`. (**Symbols:** 22 manually selected stocks: `INOD`, `ORCL`, `CRM`, `AZN`, `NFLX`, `UBER`, `V`, `MA`, `CALM`, `DXCM`, `MSTR`, `MELI`, `MSFT`, `AAPL`, `META`, `GOOG`, `AMZN`, `NVDA`, `TSLA`, `DT`, `DDOG`, and `YPF`.)

- **Deploy local GitHub Pages, on demand:** build and deploy the static data already committed under `frontend/public/data/`. This does not fetch SEC data, refresh prices, or modify the dataset.
- **Update stock prices, every four hours:** check out the LFS-tracked SQLite database, use it as the preferred baseline, fall back to the last successful deployed dataset when needed, fetch recent daily candles, merge them into existing history, recalculate price, return, support, and `days_to_next_earnings` metrics, commit the updated database and tracked static data changes, then deploy. SEC data is reused unchanged. If one price source is temporarily empty, its existing history is retained and the global date validation decides whether publishing is safe.
- **Update SEC fundamentals, once daily:** check out the LFS-tracked SQLite database, fetch recent SEC submission metadata for each ticker, and only recollect tickers whose latest relevant SEC filing changed. Recollected tickers refresh Company Facts, recent filing context, prices needed by the snapshot, adjusted EPS with a small archive cap, and the current Yahoo Finance earnings-calendar estimate. Unchanged tickers preserve their existing DB snapshots; the four-hour price refresh still rolls the earnings countdown forward. The workflow then rebuilds derived signals, exports static data, commits the updated database and tracked static data changes, then deploys.
- **Other data:** Yahoo Finance supplies forward PE, market-cap estimates, and the next expected earnings release date/window used for `days_to_next_earnings`. Frankfurter or Yahoo Finance supplies currency conversion when required.
- **Non-SEC issuer data:** when a deterministic issuer-published workbook is configured, such as Axfood's financial-data workbook for `AXFO.ST`, the provider uses that source before falling back to Yahoo Finance statement tables.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

The SQLite database at `data/invest_os.sqlite` is the repo-persisted source of truth and is tracked with Git LFS. Update workflows check it out, mutate it, and commit the updated LFS pointer back to `main`.

The daily SEC workflow stores the latest relevant SEC accession it has checked per ticker in SQLite. On later runs, unchanged tickers are reported as preserved instead of being recollected from scratch. Local backfills remain responsible for deeper archive searches and historical repairs.

The four-hour price workflow prefers the checked-out SQLite database for snapshots and price history, uses the deployed JSON as a fallback baseline, and commits both the refreshed database and tracked static files back to `main`.

`days_to_next_earnings` is stored inside each stock snapshot as a `price_opportunity` metric. It is a proxy estimate, not a company filing fact: the source is Yahoo Finance/yfinance and the metric notes include the expected date or date range. Full stock collection refreshes the expected earnings date, and the regular price refresh keeps the day countdown current in SQLite and static JSON.

The database is then exported into static files used by the website:

- `data/open-data/stocks.json`: all stock snapshots and metrics.
- `data/open-data/price-history/{SYMBOL}.json`: daily price history for one symbol.
- `data/stocks/universe.json`: searchable symbol metadata.
- `data/meta.json`: refresh time, market date, and symbol count.

These generated files are packaged inside the GitHub Pages deployment artifact. The refreshed SQLite database is kept in the repo through Git LFS; raw SEC responses are not kept as production data. Supabase currently stores only users, watchlists, saved filters, and in-app badge events.

## 3. GitHub Pages publishes the update

After validation, Vite builds the frontend in static-data mode and GitHub Pages replaces the previous deployment. If refresh or validation fails, the previous working deployment remains live.

The browser loads all stock snapshots once, then searches, filters, and sorts them locally. Opening a symbol loads its separate price-history file and displays its charts.

There is currently **no stock-list pagination** because the universe contains only 22 symbols. Before expanding to the full US market, the stock list should move behind a paginated API instead of downloading every snapshot at once.
