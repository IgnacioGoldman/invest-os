# Exploration Beta

A local stock exploration app focused on one workflow: public/open-data stock screening.

The app serves cached stock fundamentals, derived metrics, support-distance metrics, and price history from local SQLite. It has no portfolio, capital, connector, notes, settings, personality, recommendation, or landing-page surfaces.

## Run Locally

```sh
(cd backend && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000)
```

```sh
(cd frontend && npm run dev -- --host 0.0.0.0)
```

Open http://localhost:5173/.

## Personal Accounts

Supabase is optional. Without its environment values, the public stock explorer shows the full stock universe. With Supabase configured, users can sign in with Google, build a private watchlist, save custom filter views, and see a daily `+N` badge when watched symbols newly enter a filter.

1. Create a Supabase project and run the SQL files in `supabase/migrations/` in filename order in its SQL Editor. Existing projects that already ran the first migration only need `202609190002_watchlists_and_filter_badges.sql`.
2. In Supabase Authentication, enable Google and configure the Google OAuth client. Use `https://<project-ref>.supabase.co/auth/v1/callback` as the Google client's authorized redirect URI, then add these app redirect URLs to the Supabase allow list:
   - `http://localhost:5173/**`
   - `https://ignaciogoldman.github.io/invest-os/**`
3. Copy `frontend/.env.example` to `frontend/.env.local`, then set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
4. For GitHub Pages, add repository Actions secrets named `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`.

The publishable key is intentionally used by the browser; row-level security keeps each user's data private. Never expose `SUPABASE_SERVICE_ROLE_KEY` to Vite or any `VITE_*` variable.

The Pages workflow refreshes and validates the tracked stock universe after each completed US market session, then evaluates each user's watchlist filters against that exact dataset. A separate lightweight workflow downloads the currently deployed dataset and evaluates it every eight hours, keeping badges timely and providing regular database activity for the Free Supabase project. A filter's first evaluation establishes its baseline quietly. Later watched symbols entering a built-in or custom filter create a dated in-app badge event.

## Kept Data

- `data/invest_os.sqlite`: local SQLite cache for stock snapshots, metric series, derived signals, and price history.
- `data/stocks/stocks.json`: stock universe used by refresh.
- `data/stocks/derived_signals/latest.json`: deterministic derived stock signals.

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

## GitHub Pages

The `.github/workflows/pages.yml` workflow refreshes the tracked universe from public data, rejects incomplete or incoherent refreshes, exports static JSON with `VITE_DATA_MODE=static`, evaluates watchlist filter badges when Supabase secrets are configured, and deploys `frontend/dist` to GitHub Pages. Generated market data is kept in the deployment artifact rather than committed daily.

It runs on pushes to `main`, manual dispatches, and at `23:30 UTC` Monday through Friday after the US market close. In the repository settings, set Pages source to GitHub Actions.
