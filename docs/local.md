# Local Data Workflow

The local workflow is the source-of-truth workflow for improving data quality before the automated refresh runs. It is allowed to be slower, deeper, and more complete than GitHub Actions because it runs intentionally from a developer machine and writes to the persistent local database.

The current goal is:

`local collectors -> data/invest_os.sqlite -> derived metrics -> static export -> review -> commit publishable data`

GitHub Actions persist both the tracked SQLite database and the static exports back to the repo. `data/invest_os.sqlite` is tracked with Git LFS, so local backfills and remote update workflows share the same source-of-truth file.

## 1. What Local Is Responsible For

Local runs should fill gaps that need deeper history or more careful crawling:

- Historical metric depth, such as at least four periods for revenue growth YoY and comparable metric histories where the source data supports it.
- Non-SEC or non-US symbols, such as `AXFO.ST`, where an issuer-published workbook or report should be preferred over Yahoo Finance statement tables when available.
- Backfills for any ticker where the daily refresh can see that a metric is missing but should not spend a large request budget to repair it.

Adjusted EPS growth YoY and EPS alignment were intentionally removed because coverage was too sparse across the tracked universe for a reliable deterministic metric.

## 2. Persistence Model

Local writes to `data/invest_os.sqlite`.

Important: this SQLite file is tracked through Git LFS. A local backfill should update the database first, then regenerate static files under `frontend/public/data/`, then commit both the LFS pointer change and the exported static data.

Both local scripts and GitHub Actions modify the persistent SQLite database, then export or refresh static JSON for GitHub Pages.

Longer-term persistence choices remain open if the dataset outgrows Git LFS:

- Track a smaller normalized data artifact instead of the full SQLite database.
- Use Supabase/Postgres as the shared persistent database and keep SQLite as a local cache or development mirror.

## 3. Local Backfill Loop

Start by collecting or refreshing the universe into SQLite:

```sh
python scripts/open_data_poc.py \
  --universe-file data/stocks/stocks.json \
  --workers 4 \
  --skip-filing-details \
  --min-coverage 0
```

After collection, rebuild derived signals and export static data:

```sh
python scripts/build_stock_derived_signals.py
python scripts/export_static_site_data.py
```

Then inspect the exported data before committing:

```sh
python - <<'PY'
import json
from pathlib import Path

rows = json.loads(Path("frontend/public/data/open-data/stocks.json").read_text())
for ticker in ("UBER", "AXFO.ST"):
    row = next((item for item in rows if item.get("ticker") == ticker), None)
    if not row:
        print(ticker, "missing")
        continue
    health = row.get("business_health") or {}
    print(ticker)
    print("  revenue growth YoY:", health.get("revenue_growth_yoy"))
    print("  GAAP EPS growth YoY:", health.get("eps_gaap_growth_yoy") or health.get("eps_growth_yoy"))
PY
```

## 4. Metric History Targets

For each active ticker, local should aim to persist enough history to make metric trends useful:

- At least four periods for revenue growth YoY when quarterly or annual data supports it.
- At least four periods for major profitability and cash-flow metrics where possible.
- Explicit unavailable metrics when open/free source data cannot support the target.
- Source URLs, forms, periods, and notes for parsed SEC-derived metrics.

The current scripts compute many snapshot metrics but do not yet guarantee a minimum historical depth for every metric. That should become a local backfill concern first, then a daily validation concern once the database model supports it.

For non-SEC tickers, prefer deterministic issuer data when it is available. `AXFO.ST` uses Axfood's official financial-data workbook, which provides quarterly and annual statement history back to 2015 and fills much deeper revenue growth YoY history than Yahoo Finance's limited quarterly table.

## 5. Relationship To GitHub Actions

Local is for completeness and repair. GitHub Actions are for updates.

The daily remote refresh should:

- Fetch recent SEC submissions for each ticker and use them as a cheap change detector.
- Recollect only tickers whose latest relevant SEC filing changed; preserve unchanged DB snapshots.
- Add or update only facts that are newer or better.
- Export static JSON from the updated database.
- Commit `data/invest_os.sqlite` and tracked static data changes back to `main`.

The price refresh continues to run more frequently. It reads the checked-out SQLite database when available, falls back to the deployed static dataset when needed, updates price-derived metrics and histories, and commits both the database and tracked static data changes.

See [data-refresh.md](data-refresh.md) for the automated refresh model:

- SEC/fundamentals refresh once each weekday.
- Price and price-derived metric refresh every four hours on weekdays.
- Static export and GitHub Pages deployment after validation.
