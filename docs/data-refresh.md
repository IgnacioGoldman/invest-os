# Stock Data Refresh

Current flows:

`On demand: committed static JSON -> GitHub Pages`

`Daily: tracked SQLite -> SEC + prices -> tracked SQLite -> static JSON -> commit tracked data -> GitHub Pages`

`Every four hours: tracked SQLite + deployed JSON fallback + recent prices -> tracked SQLite + updated static JSON -> commit tracked data -> GitHub Pages`

## 1. GitHub Actions fetches the content

Both workflows read the universe from `data/stocks/stocks.json`. (**Symbols:** 22 manually selected stocks: `INOD`, `ORCL`, `CRM`, `AZN`, `NFLX`, `UBER`, `V`, `MA`, `CALM`, `DXCM`, `MSTR`, `MELI`, `MSFT`, `AAPL`, `META`, `GOOG`, `AMZN`, `NVDA`, `TSLA`, `DT`, `DDOG`, and `YPF`.)

- **Deploy local GitHub Pages, on demand:** build and deploy the static data already committed under `frontend/public/data/`. This does not fetch SEC data, refresh prices, or modify the dataset.
- **Update stock prices, every four hours:** check out the LFS-tracked SQLite database, use it as the preferred baseline, fall back to the last successful deployed dataset when needed, fetch recent daily candles, merge them into existing history, recalculate price, return, and support metrics, commit the updated database and tracked static data changes, then deploy. SEC data is reused unchanged. If one price source is temporarily empty, its existing history is retained and the global date validation decides whether publishing is safe.
- **Update remote GitHub Pages, once daily:** check out the LFS-tracked SQLite database, fetch the full available candle history plus SEC Company Facts and recent submission metadata, enrich adjusted EPS with a small archive cap, rebuild derived signals, export static data, commit the updated database and tracked static data changes, then deploy. These provide revenue, EPS, margins, cash flow, cash, debt, equity, shares, and annual/quarterly history.
- **Other data:** Yahoo Finance supplies forward PE and market-cap estimates. Frankfurter or Yahoo Finance supplies currency conversion when required.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

The SQLite database at `data/invest_os.sqlite` is the repo-persisted source of truth and is tracked with Git LFS. Update workflows check it out, mutate it, and commit the updated LFS pointer back to `main`.

The four-hour price workflow prefers the checked-out SQLite database for snapshots and price history, uses the deployed JSON as a fallback baseline, and commits both the refreshed database and tracked static files back to `main`.

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
