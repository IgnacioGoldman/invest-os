# Stock Data Refresh

Current flows:

`Daily: SEC + prices -> temporary SQLite -> static JSON -> GitHub Pages`

`Every four hours: deployed JSON + recent prices -> updated static JSON -> GitHub Pages`

## 1. GitHub Actions fetches the content

Both workflows read the universe from `data/stocks/stocks.json`. (**Symbols:** 22 manually selected stocks: `INOD`, `ORCL`, `CRM`, `AZN`, `NFLX`, `UBER`, `V`, `MA`, `CALM`, `DXCM`, `MSTR`, `MELI`, `MSFT`, `AAPL`, `META`, `GOOG`, `AMZN`, `NVDA`, `TSLA`, `DT`, `DDOG`, and `YPF`.)

- **Every four hours and on pushes:** download the last successful deployed dataset, fetch recent daily candles, merge them into existing history, and recalculate price, return, and support metrics. SEC data is reused unchanged. If one price source is temporarily empty, its deployed history is retained and the global date validation decides whether publishing is safe.
- **Once daily:** fetch the full available candle history plus SEC Company Facts and recent submission metadata. These provide revenue, EPS, margins, cash flow, cash, debt, equity, shares, and annual/quarterly history.
- **Other data:** Yahoo Finance supplies forward PE and market-cap estimates. Frankfurter or Yahoo Finance supplies currency conversion when required.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

The daily fundamentals workflow writes collected data to a temporary SQLite database at `data/invest_os.sqlite`. The four-hour price workflow instead starts from the last successful JSON deployed on GitHub Pages.

The database is then exported into static files used by the website:

- `data/open-data/stocks.json`: all stock snapshots and metrics.
- `data/open-data/price-history/{SYMBOL}.json`: daily price history for one symbol.
- `data/stocks/universe.json`: searchable symbol metadata.
- `data/meta.json`: refresh time, market date, and symbol count.

These generated files are packaged inside the GitHub Pages deployment artifact. Neither the refreshed SQLite database nor raw SEC responses are kept as a production database. Supabase currently stores only users, watchlists, saved filters, and in-app badge events.

## 3. GitHub Pages publishes the update

After validation, Vite builds the frontend in static-data mode and GitHub Pages replaces the previous deployment. If refresh or validation fails, the previous working deployment remains live.

The browser loads all stock snapshots once, then searches, filters, and sorts them locally. Opening a symbol loads its separate price-history file and displays its charts.

There is currently **no stock-list pagination** because the universe contains only 22 symbols. Before expanding to the full US market, the stock list should move behind a paginated API instead of downloading every snapshot at once.
