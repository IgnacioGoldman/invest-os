# Exploration Beta

A local stock exploration app focused on one workflow: public/open-data stock screening.

The app serves cached stock fundamentals, derived metrics, support-distance metrics, and price history from local SQLite. Signed-in users have a personal space with Explore, Watchlist, and Portfolio tabs.

The universe contains 200 stocks. Static mobile builds load compact screening data first and fetch complete financial histories and price charts when a stock opens. The revenue-led 123-stock expansion and its selection evidence are documented in [the research shortlist](docs/research/revenue-expansion-2026-10-17/shortlist.md).

## Run Locally

```sh
(cd backend && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000)
```

```sh
(cd frontend && npm run dev -- --host 0.0.0.0)
```

Open http://localhost:5173/.

## Personal Accounts

Supabase is optional. Without its environment values, the public stock explorer shows the full stock universe. With Supabase configured, users can sign in with Google, build a private watchlist, save custom filter views, and see a daily `+N` badge when watched symbols newly enter a filter. The Portfolio tab saves amounts by source in EUR, USD or SEK, with an invested/uninvested status. Users can add, edit or delete amounts and choose a currency for the combined total and pie chart. Conversions use daily ECB reference rates via [Frankfurter](https://frankfurter.dev/), with the rate date shown; original balances are never converted in storage. If rates are unavailable, mixed-currency totals wait for a retry rather than adding incompatible currencies.

My space opens on **Explore**, using the same stock list, search, filters, and stock details as the public view. All stock lists share a full-width search field beside a compact filter icon, with a blue dot when a filter is active. Tap a stock's bookmark-plus icon to save it directly to **My Watchlist**, then use the confirmation's **View** action or switch to **Watchlist** to organize it. Explore and Watchlist keep separate search and filter settings.

Stock detail links use the exact ticker, such as `/DTM`, to keep company names from colliding. Existing company-name links still open when they identify one stock unambiguously; exact tickers take priority. Run `(cd frontend && npm run test:routing)` to check stock link resolution.

Choose **Analyze**, select stocks, then **Generate AI brief** to create and copy a comparison brief. The ready view includes a short preview, an optional full prompt, and **Open ChatGPT**; paste the prompt into ChatGPT or another AI to start the analysis. The brief includes numerical metrics, fiscal periods, source identifiers and data dates. Selection works across search, filters and pages. If automatic copying is blocked, use the copy button or select the full prompt to copy it manually.

The business-performance facts, Revenue Growth Consistency, derived **Red Flag Count**, and custom filter metrics share `frontend/src/stockMetrics.ts`. Red Flag Count adds at most one point for each of four concern groups and exposes its evidence and coverage; incomplete assessments never pass numeric limits. Custom filters support both descriptive labels and numeric comparisons, including revenue >15%, operating margin >15% and Red Flag Count ≤1. See the [metric index](docs/metrics/README.md). Proximity to Support offers a separate timeframe selector. Run `(cd frontend && npm run test:metrics)` to check card statuses, numeric comparisons, saved-filter persistence and agreement with the Python watchlist badge evaluator; deployment runs this check too.

The filter picker shows **All stocks** and your saved custom filters. Choose **New filter** to define conditions and sorting; every metric must match, and any selected status may match within a metric. Choose **Edit** to change, rename, hide, or delete your saved filters.

An empty watchlist shows one **Add stocks** action. Once stocks are saved, search and a compact filter button share a row, with a blue dot indicating an active filter. **Add stocks**, **Analyze**, and **Organize** sit below. Groups use subtle, collapsible labels above flat stock rows. Use **Organize** to create or edit groups and reveal drag handles for reordering stocks; clicking a handle also provides move controls for touch and keyboard use. **Add stocks** lets you choose a destination when groups exist. Choose **Group order** in the sort sheet to return to your saved arrangement after sorting by a metric. Deleting a group keeps its stocks watched under **Ungrouped**. Groups, their collapsed state, and stock placement sync with your account.

1. Create a Supabase project and run the SQL files in `supabase/migrations/` in filename order in its SQL Editor. Existing projects should run only migrations they have not applied. For Portfolio, apply `202610080001_money_entries.sql` before deploying the frontend. For grouped watchlists, also apply `202610130001_watchlist_groups.sql` before deploying the frontend; existing watched symbols remain in My Watchlist in their original order. These migrations create private tables with per-user read/write policies.
2. In Supabase Authentication, enable Google and configure the Google OAuth client. Use `https://<project-ref>.supabase.co/auth/v1/callback` as the Google client's authorized redirect URI, then add these app redirect URLs to the Supabase allow list:
   - `http://localhost:5173/**`
   - `https://ignaciogoldman.github.io/invest-os/**`
3. Copy `frontend/.env.example` to `frontend/.env.local`, then set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
4. For GitHub Pages, add repository Actions secrets named `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`.

The publishable key is intentionally used by the browser; row-level security keeps each user's data private. Never expose `SUPABASE_SERVICE_ROLE_KEY` to Vite or any `VITE_*` variable.

The price workflow refreshes daily candles and recalculates price-dependent metrics and valuation ratios from saved financial inputs every four hours on weekdays, with SEC requests disabled. The Pages workflow performs the slower SEC fundamentals refresh once each weekday while reusing saved prices. Both evaluate each user's watchlist filters against the resulting dataset. A separate lightweight workflow evaluates the deployed dataset every eight hours, keeping badges timely and providing regular database activity for the Free Supabase project. A filter's first evaluation establishes its baseline quietly. Later watched symbols entering a saved custom filter create a dated in-app badge event.

## Kept Data

- `data/invest_os.sqlite`: local SQLite cache for stock snapshots, metric series, derived signals, and price history.
- `data/stocks/stocks.json`: stock universe used by refresh.
- `data/stocks/derived_signals/latest.json`: deterministic derived stock signals.
- `data/stocks/industry-classifications.json`: explicit business peer groups with original labels and review metadata.
- `data/stocks/benchmarks/sp500.json`: retained historical benchmark data; Industry Relative Strength is disabled pending robust peer coverage and classification. See the [metric index](docs/metrics/README.md).

## Useful Scripts

```sh
python scripts/build_stock_universe.py
```

Builds `data/stocks/stocks.json`.

```sh
python scripts/open_data_poc.py --universe-file data/stocks/stocks.json --workers 8 --skip-filing-details
```

Collects public stock facts into `data/invest_os.sqlite` and marks saved tickers active.

```sh
python scripts/build_stock_derived_signals.py
```

Rebuilds `data/stocks/derived_signals/latest.json` from active SQLite stock snapshots.

```sh
python scripts/export_static_site_data.py
```

Exports active SQLite stock snapshots, the universe, and price history into `frontend/public/data/` for a static GitHub Pages build.

```sh
python scripts/refresh_static_prices.py --output /tmp/price-refresh-report.json
```

Uses saved financial inputs to update candles, price/support metrics and current valuations, without SEC requests. The deployed Pages dataset supplies fallback data when needed.

## GitHub Pages

The `.github/workflows/pages.yml` workflow refreshes fundamentals using saved SQLite prices, rejects incomplete or incoherent refreshes, exports static JSON with `VITE_DATA_MODE=static`, and deploys `frontend/dist` to GitHub Pages. It runs manually and at `10:30 UTC` Monday through Friday.

The `.github/workflows/price-refresh.yml` workflow reuses saved fundamentals, refreshes prices and recalculates current valuations at `00:30`, `04:30`, `08:30`, `12:30`, `16:30`, and `20:30 UTC` Monday through Friday, and supports manual runs. In the repository settings, set Pages source to GitHub Actions.

## Paper strategy versus VWCE

The existing Portfolio tab includes a forward-running €10,000 EUR paper simulation, a VWCE comparison chart, current/historical holdings and a complete transaction/decision timeline. It starts at actual activation, with no fabricated past performance. Deterministic screening and risk coverage gate one daily structured AI review; fixed portfolio rules decide orders and execute them at later valid closes. The separate private money tracker is preserved.

See [the simulation architecture, exact rules, accounting conventions and setup](docs/portfolio-simulation.md). Set the repository Actions secret `OPENAI_API_KEY` to enable AI reviews. The scheduled workflow runs weekdays at 23:35 Europe/Stockholm and can be dispatched manually. Without sufficient validated inputs or the key, the strategy stays in cash rather than inventing investments.
