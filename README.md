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

The `.github/workflows/pages.yml` workflow refreshes `data/stocks/stocks.json`, exports static JSON, builds the Vite app with `VITE_DATA_MODE=static`, and deploys `frontend/dist` to GitHub Pages.

It runs on pushes to `main`, manual dispatches, and daily at `00:00` in `Europe/Stockholm`. In the repository settings, set Pages source to GitHub Actions.
