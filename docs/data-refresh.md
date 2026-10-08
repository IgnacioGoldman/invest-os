# Stock Data Refresh

Current flows:

`On demand: committed static JSON -> GitHub Pages`

`Daily: tracked SQLite -> SEC recent-submissions and current-input checks -> changed/currently incomplete SEC tickers + non-SEC tickers -> latest primary sources and bounded fallback -> tracked SQLite -> static JSON -> coverage audit -> commit tracked data -> GitHub Pages`

`Every four hours: tracked SQLite + deployed JSON fallback + recent prices -> tracked SQLite + updated static JSON -> commit tracked data -> GitHub Pages`

## 1. GitHub Actions fetches the content

Both workflows read the active universe from `data/stocks/stocks.json`. The exported dataset currently contains 77 symbols.

- **Deploy local GitHub Pages, on demand:** build and deploy the static data already committed under `frontend/public/data/`. This does not fetch SEC data, refresh prices, or modify the dataset.
- **Update stock prices, every four hours:** check out the LFS-tracked SQLite database, use it as the preferred baseline, fall back to the last successful deployed dataset when needed, fetch recent daily candles, merge them into existing history, recalculate price, return, support, and `days_to_next_earnings` metrics, commit the updated database and tracked static data changes, then deploy. SEC data is reused unchanged. If one price source is temporarily empty, its existing history is retained and the global date validation decides whether publishing is safe.
- **Update stock fundamentals, once daily:** check out the LFS-tracked SQLite database, fetch recent SEC submission metadata, and recollect tickers whose relevant filing changed or whose current fundamental inputs remain incomplete. Historical quarter gaps, momentum windows and three-year CAGR gaps never trigger daily recollection. Healthy unchanged SEC tickers preserve their snapshots. Existing non-SEC tickers are recollected so issuer and vendor updates are not skipped by the SEC gate. Collection refreshes price inputs and Yahoo's earnings-calendar estimate; the four-hour price refresh still rolls the countdown forward. The workflow rebuilds signals, exports static data, audits coverage, commits the database, static exports, normalized issuer facts and coverage report, then deploys.
- **Other data:** Yahoo Finance supplies forward PE, market-cap estimates, and the next expected earnings release date/window used for `days_to_next_earnings`. Frankfurter or Yahoo Finance supplies currency conversion when required.
- **Non-SEC issuer data:** configured issuer workbooks, such as Axfood's for `AXFO.ST`, are preferred. A failed workbook fetch/parse tries Yahoo statement tables. NIBE checks its official archive for the newest report only, parses that supported consolidated PDF if it is new, and persists it in `data/stocks/issuer_facts/NIBE-B.ST.json`. The daily run never downloads older missing reports. Failed discovery/download/parse retains verified issuer history and records the failure. Yahoo supplies additional NIBE facts when available.
- **Missing SEC inputs:** the provider checks Yahoo statement tables as a second source for missing current fundamental inputs. It accepts only money facts in the verified SEC reporting currency and matching calendar fiscal periods. It excludes vendor EPS/share-count facts from this fallback to avoid mixing ADR and ordinary-share accounting. Non-calendar fiscal labels or incompatible currencies are reported as unsupported fallback cases. Available SEC snapshot values retain their source and accounting basis.
- **History retention:** a thinner refresh cannot erase persisted historical observations. Missing current values can retain a previous verified observation with its original `as_of`; explicitly not-meaningful metrics, such as PEG after earnings turn negative, remain unavailable. Fallback failures and unresolved gaps are visible in snapshot notes and the coverage audit.

Four symbols are processed in parallel. The refresh is rejected if a symbol fails, is missing, has invalid prices, or has an inconsistent market date.

## 2. The content is stored and exported

The SQLite database at `data/invest_os.sqlite` is the repo-persisted source of truth and is tracked with Git LFS. Update workflows check it out, mutate it, and commit the updated LFS pointer back to `main`.

The daily fundamentals workflow stores the latest checked relevant SEC accession in SQLite. On later runs, healthy unchanged SEC tickers are reported as preserved. `--repair-current-data` overrides this skip only for missing current fundamental inputs. The daily run makes a bounded second-source attempt and retains previously collected history without fetching it again. Local `--repair-data-gaps` runs and the explicit NIBE backfill remain responsible for deeper archive searches, older missing quarters, CAGR history, unsupported PDF layouts, fiscal-period alignment repairs, and adding deterministic parsers for additional issuers. There is no universal parser or arbitrary web crawl for every investor-relations site.

`data/stocks/data-coverage.json` is regenerated after export and committed with the data. The refresh report records repair reasons and source-attempt notes; the coverage audit distinguishes missing inputs from mathematically unavailable metrics and identifies gaps in the latest six revenue quarters. Both reports are uploaded as workflow artifacts.

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

There is currently **no stock-list pagination**. Before expanding to the full US market, the stock list should move behind a paginated API instead of downloading every snapshot at once.
