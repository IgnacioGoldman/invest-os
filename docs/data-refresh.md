# Stock Data Refresh

Current flow:

`GitHub Actions -> public data sources -> temporary SQLite -> static JSON -> GitHub Pages`

## 1. GitHub Actions fetches the content

The Pages workflow runs every four hours on weekdays and reads the stock universe from `data/stocks/stocks.json`.

- **Symbols:** 22 manually selected stocks: `INOD`, `ORCL`, `CRM`, `AZN`, `NFLX`, `UBER`, `V`, `MA`, `CALM`, `DXCM`, `MSTR`, `MELI`, `MSFT`, `AAPL`, `META`, `GOOG`, `AMZN`, `NVDA`, `TSLA`, `DT`, `DDOG`, and `YPF`.
- **Price candles:** daily candles, using the maximum available history from Stooq or Yahoo Finance. The app derives 1D, 1W, 1M, 3M, 6M, 1Y, 2Y, 5Y, and all-time views from this history.
- **SEC data:** Company Facts and recent submission metadata. These provide revenue, EPS, margins, cash flow, cash, debt, equity, shares, and annual/quarterly history. The app derives growth, support, return, valuation, and quality metrics from them.
- **Other data:** Yahoo Finance supplies forward PE and market-cap estimates. Frankfurter or Yahoo Finance supplies currency conversion when required.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

During the workflow, collected data is written to a temporary SQLite database at `data/invest_os.sqlite`. It contains stock snapshots, daily prices, metric history, and derived signals.

The database is then exported into static files used by the website:

- `data/open-data/stocks.json`: all stock snapshots and metrics.
- `data/open-data/price-history/{SYMBOL}.json`: daily price history for one symbol.
- `data/stocks/universe.json`: searchable symbol metadata.
- `data/meta.json`: refresh time, market date, and symbol count.

These generated files are packaged inside the GitHub Pages deployment artifact. The refreshed database is not a permanent production database. Supabase currently stores only users, watchlists, saved filters, and in-app badge events.

## 3. GitHub Pages publishes the update

After validation, Vite builds the frontend in static-data mode and GitHub Pages replaces the previous deployment. If refresh or validation fails, the previous working deployment remains live.

The browser loads all stock snapshots once, then searches, filters, and sorts them locally. Opening a symbol loads its separate price-history file and displays its charts.

There is currently **no stock-list pagination** because the universe contains only 22 symbols. Before expanding to the full US market, the stock list should move behind a paginated API instead of downloading every snapshot at once.
