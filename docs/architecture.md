# Exploration Beta Architecture

Exploration Beta is a small local app for stock research. It has one frontend screen, a small FastAPI backend, local SQLite storage, and a few scripts for rebuilding stock data.

It does not include portfolio tracking, broker/exchange connectors, manual capital, notes, settings, investor personality, or AI recommendations.

## Main Flow

1. The frontend loads `GET /api/open-data/stocks`.
2. The backend reads stock rows from `data/invest_os.sqlite`.
3. The backend filters rows by the active stock list stored in SQLite.
4. When a row is expanded, the frontend loads `GET /api/open-data/stocks/{ticker}/price-history`.
5. The stock price chart is rendered from locally stored daily close history.
6. The Refresh button starts `POST /api/refresh` with `exploration_beta`.
7. The backend refresh worker fetches missing or stale stock data, stores it, and rebuilds derived stock signals.

## Frontend

The frontend is a React/Vite app.

- `frontend/src/main.tsx`: mounts React into `frontend/index.html`.
- `frontend/src/App.tsx`: owns app state, loads stocks, starts refresh jobs, and renders the beta table.
- `frontend/src/api.ts`: typed API client for the small backend surface.
- `frontend/src/components/OpenDataStockTable.tsx`: the main table, filters, support columns, stock price chart, and growth charts.
- `frontend/src/styles.css`: application styling.

## Backend

The backend is a FastAPI app.

- `backend/app/main.py`: HTTP routes.
- `backend/app/config.py`: data directory and environment config.
- `backend/app/services/storage.py`: SQLite schema and persistence helpers.
- `backend/app/services/open_data_stock_store.py`: loads stock snapshots and price history from DB.
- `backend/app/services/exploration_refresh.py`: refreshes stale or missing stock snapshots.
- `backend/app/services/refresh_jobs.py`: in-memory background job queue and status.
- `backend/app/services/stock_derived_signals.py`: deterministic derived stock signals.
- `backend/app/entry_engine/open_data_models.py`: stock snapshot models.
- `backend/app/entry_engine/open_data_metrics.py`: metric computation from public facts.
- `backend/app/entry_engine/providers/open_data_provider.py`: public data fetcher for SEC, yfinance, Stooq, and FX.
- `backend/app/entry_engine/utils/file_storage.py`: stock universe file helpers.

## Local Data

Primary runtime data lives in:

- `data/invest_os.sqlite`: SQLite database with stock snapshots, metric series, derived signals, and price history.
- `data/stocks/stocks.json`: the stock universe used by refresh.
- `data/stocks/derived_signals/latest.json`: derived stock signal file.
SQLite is the source of truth for stock snapshots. `data/stocks/stocks.json` remains a catalog used for searching and adding stocks to the active table.

## Cache

`.cache/open_data` is a local fetch cache. It avoids repeated calls for data such as forward PE estimates, SEC metadata, and price history.

It is safe to delete. The next refresh may take longer and make more external requests.

## Scripts

- `scripts/build_stock_universe.py`: builds `data/stocks/stocks.json`.
- `scripts/open_data_poc.py`: fetches public stock facts for a universe or ticker set and writes them to SQLite.
- `scripts/build_stock_derived_signals.py`: rebuilds derived stock signal files from active SQLite stock snapshots.

These scripts are useful for rebuilding data outside the UI.

## API Surface

- `GET /api/health`
- `GET /api/open-data/stocks`
- `GET /api/stocks/universe`
- `POST /api/stocks/active/{ticker}`
- `DELETE /api/stocks/active/{ticker}`
- `GET /api/open-data/stocks/{ticker}`
- `GET /api/open-data/stocks/{ticker}/price-history`
- `POST /api/open-data/stocks/{ticker}/refresh`
- `POST /api/refresh`
- `GET /api/refresh/jobs`

## Cleanup Rules

Safe to delete:

- `__pycache__` folders
- `frontend/dist`
- `.cache/open_data` if slower refreshes are acceptable

Keep:

- `data/invest_os.sqlite`
- `data/stocks/stocks.json`
- current backend/frontend source files
- scripts if you want local data rebuild tools
