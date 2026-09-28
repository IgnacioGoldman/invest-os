# Local Data Workflow

The local workflow is the source-of-truth workflow for improving data quality before the automated refresh runs. It is allowed to be slower, deeper, and more complete than GitHub Actions because it runs intentionally from a developer machine and writes to the persistent local database.

The goal is:

`local collectors -> data/invest_os.sqlite -> derived metrics -> static export -> review -> commit publishable data`

GitHub Actions should later update the same persistent dataset model, not rebuild important facts from a temporary database and lose previously discovered evidence.

## 1. What Local Is Responsible For

Local runs should fill gaps that need deeper history or more careful crawling:

- Adjusted EPS growth YoY from official earnings-release exhibits.
- EPS alignment, once adjusted EPS and GAAP EPS are both available.
- Historical metric depth, such as at least four periods for revenue growth YoY and comparable metric histories where the source data supports it.
- Non-SEC or non-US symbols, such as `AXFO.ST`, where Yahoo Finance statement tables may be the current open/free source.
- Backfills for any ticker where the daily refresh can see that a metric is missing but should not spend a large request budget to repair it.

For example, UBER's adjusted EPS growth YoY was missed by the daily Action because the relevant earnings release was not one of the newest SEC archive filings selected by the small daily cap. Local backfill should be able to search farther back, find the official exhibit, parse the metric, write it to SQLite, rebuild derived signals, and export static data.

## 2. Persistence Model

Local writes to `data/invest_os.sqlite`.

Important: this SQLite file is currently local state, not a tracked repo file. It is large enough that committing it directly to git is probably not viable without Git LFS or another persistence mechanism. The current publishable repo artifact is the exported static data under `frontend/public/data/`.

The intended end state is that both local scripts and GitHub Actions modify a persistent database, then export static JSON from that database. Until that persistence layer is chosen, local can still be the quality-control workflow by updating SQLite and committing the resulting exported static JSON.

Possible persistence choices:

- Keep SQLite local and commit only exported static JSON.
- Track a smaller normalized data artifact instead of the full SQLite database.
- Use Git LFS for the SQLite database, if repo-size and Action checkout tradeoffs are acceptable.
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

Then run a deeper adjusted EPS enrichment pass. Local runs may use a larger archive lookup cap than the daily Action:

```sh
python scripts/enrich_adjusted_eps.py \
  --max-sec-archive-lookups 8 \
  --request-timeout 20 \
  --request-retries 1 \
  --retry-backoff 1 \
  --output /tmp/adjusted-eps-local-report.json
```

For a focused retry while debugging:

```sh
python scripts/enrich_adjusted_eps.py \
  --tickers UBER \
  --max-sec-archive-lookups 12 \
  --output /tmp/adjusted-eps-uber-report.json
```

After enrichment, rebuild derived signals and export static data:

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
    print("  adjusted EPS:", health.get("eps_adjusted_growth_yoy"))
    print("  EPS alignment:", health.get("eps_alignment"))
    print("  revenue growth YoY:", health.get("revenue_growth_yoy"))
PY
```

## 4. Metric History Targets

For each active ticker, local should aim to persist enough history to make metric trends useful:

- At least four periods for revenue growth YoY when quarterly or annual data supports it.
- At least four periods for major profitability and cash-flow metrics where possible.
- Explicit unavailable metrics when open/free source data cannot support the target.
- Source URLs, forms, periods, and notes for parsed SEC-derived metrics.

The current scripts compute many snapshot metrics but do not yet guarantee a minimum historical depth for every metric. That should become a local backfill concern first, then a daily validation concern once the database model supports it.

## 5. Relationship To GitHub Actions

Local is for completeness and repair. GitHub Actions are for updates.

The daily fundamentals refresh should eventually:

- Read the persistent database as its baseline.
- Fetch latest SEC Company Facts, recent submissions, prices, and estimates.
- Add or update only facts that are newer or better.
- Preserve known-good backfilled metrics when a shallow daily search does not rediscover them.
- Export static JSON from the updated database.
- Commit or otherwise persist the updated database/static data, depending on the chosen persistence layer.

The price refresh should continue to run more frequently, but it should also update the persistent database rather than treating GitHub Pages as the only baseline.

See [data-refresh.md](data-refresh.md) for the automated refresh model:

- SEC/fundamentals refresh once each weekday.
- Price and price-derived metric refresh every four hours on weekdays.
- Static export and GitHub Pages deployment after validation.
