# Stock Data Refresh

Current flows:

`On demand: committed static JSON -> GitHub Pages`

`Daily: tracked SQLite -> SEC recent-submissions and current-input checks -> changed/currently incomplete SEC tickers + non-SEC tickers -> latest primary sources and bounded fallback -> tracked SQLite -> static JSON -> coverage audit -> commit tracked data -> GitHub Pages`

`Every four hours: tracked SQLite + deployed JSON fallback + recent prices -> valuation recalculation using saved financial inputs -> tracked SQLite + updated static JSON -> commit tracked data -> GitHub Pages`

## 1. GitHub Actions fetches the content

Both workflows read the active universe from `data/stocks/stocks.json`. The exported dataset currently contains 77 symbols.

The SEC fallback merges same-currency, calendar-aligned Yahoo facts before calculating the snapshot. Overlapping SEC facts take priority across equivalent concept names, and cards, histories and metric aliases are calculated together. FCF inputs use the latest complete common reporting period available to the fallback. A thin refresh retains a complete prior FCF calculation together with its inputs and date, and retained revenue history supplies the matching latest growth card.

Price validation requires each stock's price date to match its latest exported candle, and rejects future dates or dates more than seven days old. US and Stockholm stocks may use adjacent weekday session dates during a morning refresh, including Friday/Monday across a weekend. Dates must remain uniform within each market; larger gaps and mixed dates for unknown markets still fail validation.

The fundamentals, prices and Pages workflows share a queue without cancelling an active refresh. Each queued job checks out the latest commit on its selected branch when it starts, so a delayed deployment uses the database and static data saved by the preceding refresh. Both full and incremental price-history collection try Yahoo first and retain Stooq as a fallback.

- **Deploy local GitHub Pages, on demand:** build and deploy the static data already committed under `frontend/public/data/`. This does not fetch SEC data, refresh prices, or modify the dataset.
- **Update stock prices, every four hours:** use the checked-out LFS-tracked SQLite database as the preferred baseline, with the last successful deployed dataset as a fallback. Fetch recent daily candles and merge them into existing history. Recalculate returns, support distances, market cap, trailing/forward P/E, PEG, price/sales, FCF yield and EV/EBITDA from saved financial inputs, then rebuild derived signals. Yahoo supplies the expected earnings calendar and expected EPS when available; EPS must match the listing currency. Commit the updated database and tracked static data, then deploy. SEC requests are explicitly disabled in the price provider. If price sources are temporarily empty, existing history is retained and date validation decides whether publishing is safe.
- **Update stock fundamentals, once daily:** check out SQLite, fetch recent SEC submission metadata, and recollect tickers whose relevant filing changed or whose current fundamental inputs remain incomplete. Healthy unchanged SEC tickers preserve their snapshots. Existing non-SEC tickers are recollected so issuer and vendor updates are not skipped by the SEC gate. With `--reuse-saved-prices`, collection calculates financial and valuation metrics against SQLite prices, retains the complete saved price group and history, and does not fetch new prices or market estimates. Missing or inconsistent saved prices fail collection instead of triggering a price download. The workflow rebuilds signals, exports static data, audits coverage, commits the database, static exports, normalized issuer facts and coverage report, then deploys.
- **Other data:** Yahoo Finance supplies forward PE, market-cap estimates, and the next expected earnings release date/window used for `days_to_next_earnings`. Frankfurter or Yahoo Finance supplies currency conversion when required.
- **Non-SEC issuer data:** configured issuer workbooks, such as Axfood's for `AXFO.ST`, are preferred. A failed workbook fetch/parse tries Yahoo statement tables. NIBE checks its official archive for the newest report only, parses that supported consolidated PDF if it is new, and persists it in `data/stocks/issuer_facts/NIBE-B.ST.json`. The daily run never downloads older missing reports. Failed discovery/download/parse retains verified issuer history and records the failure. Yahoo supplies additional NIBE facts when available.
- **Missing SEC inputs:** the provider checks Yahoo statement tables as a second source for missing current fundamental inputs. It accepts only money facts in the verified SEC reporting currency and matching calendar fiscal periods. It excludes vendor EPS/share-count facts from this fallback to avoid mixing ADR and ordinary-share accounting. Non-calendar fiscal labels or incompatible currencies are reported as unsupported fallback cases. Available SEC snapshot values retain their source and accounting basis.
- **History retention:** a thinner refresh cannot erase persisted historical observations. Missing current values can retain a previous verified observation with its original `as_of`; explicitly not-meaningful metrics, such as PEG after earnings turn negative, remain unavailable. Fallback failures and unresolved gaps are visible in snapshot notes and the coverage audit.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

Snapshots persist `price_currency` and `valuation_inputs`: financial denominators converted to the listing currency, ADR-adjusted listing shares, and expected EPS. Price refreshes use these inputs without downloading statements. Older snapshots are upgraded locally from saved financial values and valuation ratios, without an SEC backfill. Unverified currency bridges remain unavailable. Retained financial inputs keep their matching valuation denominators. Static history exports prefer SQLite over the raw download cache.

Local collection without `--reuse-saved-prices` still supports bootstrapping a new stock with both financial data and prices. Once a baseline exists, the scheduled workflows update financial data and prices separately.

The SQLite database at `data/invest_os.sqlite` is the repo-persisted source of truth and is tracked with Git LFS. Update workflows check it out, mutate it, and commit the updated LFS pointer back to `main`.

The daily fundamentals workflow stores the latest checked relevant SEC accession in SQLite. On later runs, healthy unchanged SEC tickers are reported as preserved. `--repair-current-data` overrides this skip only for missing current fundamental inputs. The daily run makes a bounded second-source attempt and retains previously collected history without fetching it again. Local `--repair-data-gaps` runs and the explicit NIBE backfill remain responsible for deeper archive searches, older missing quarters, CAGR history, unsupported PDF layouts, fiscal-period alignment repairs, and adding deterministic parsers for additional issuers. There is no universal parser or arbitrary web crawl for every investor-relations site.

`data/stocks/data-coverage.json` is regenerated after export and committed with the data. The refresh report records repair reasons and source-attempt notes; the coverage audit distinguishes missing inputs from mathematically unavailable metrics and identifies gaps in the latest six revenue quarters. Both reports are uploaded as workflow artifacts.

The four-hour price workflow prefers the checked-out SQLite database for snapshots and price history, uses the deployed JSON as a fallback baseline, and commits both the refreshed database and tracked static files back to `main`.

`days_to_next_earnings` is stored inside each stock snapshot as a `price_opportunity` metric. It is a proxy estimate, not a company filing fact: the source is Yahoo Finance/yfinance and the metric notes include the expected date or date range. Bootstrap collection and the price workflow fetch the expected earnings date. Scheduled fundamentals preserve the saved estimate and countdown.

The database is then exported into static files used by the website:

- `data/open-data/stocks.json`: all stock snapshots and metrics.
- `data/open-data/price-history/{SYMBOL}.json`: daily price history for one symbol.
- `data/stocks/universe.json`: searchable symbol metadata.
- `data/meta.json`: refresh time, market date, and symbol count.

These generated files are packaged inside the GitHub Pages deployment artifact. The refreshed SQLite database is kept in the repo through Git LFS; raw SEC responses are not kept as production data. Supabase currently stores only users, watchlists, saved filters, and in-app badge events.

## 3. GitHub Pages publishes the update

After validation, Vite builds the frontend in static-data mode and GitHub Pages replaces the previous deployment. If refresh or validation fails, the previous working deployment remains live.

The browser loads all stock snapshots once, then searches, filters, and sorts them locally. Opening a symbol loads its separate price-history file and displays its charts.

There is currently **no stock-list pagination**. Before expanding to the full US market, the stock list should move behind a paginated API instead of downloading every snapshot at once.
