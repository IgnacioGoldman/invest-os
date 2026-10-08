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

### NIBE issuer backfill

`NIBE-B.ST` previously had five Yahoo quarterly revenue observations, from Q2 2025 through Q2 2026. Only Q2 2026 had a matching prior-year quarter, so only one YoY growth value could be calculated. The missing history was a collector limitation: NIBE's public reports had not been parsed. The reports themselves were available.

The local backfill now imports consolidated tables from NIBE's 2024 and 2025 year-end reports and Q1/Q2 2026 reports. It persists normalized facts, publication dates, and source URLs in `data/stocks/issuer_facts/NIBE-B.ST.json`. Regular non-SEC collection checks the issuer archive for new reports, merges this durable history with Yahoo statements, and prefers issuer facts for overlapping periods. Archive or PDF failures retain verified history and are reported. The daily fundamentals workflow also commits updated issuer facts. The imported history contains 15 revenue quarters, Q4 2022 through Q2 2026, and 11 comparable YoY growth values. It also extends reported operating/net profit, EPS, recent gross profit, balance-sheet facts, and cash flow. Adjusted operating profit is kept out of reported-profit metrics. Issuer cash-flow capex uses investments in existing operations, excluding acquisitions.

To discover and import new NIBE reports, collect the symbol, rebuild signals, and export:

```sh
.venv/bin/python scripts/backfill_nibe_issuer_data.py
.venv/bin/python scripts/build_stock_derived_signals.py
.venv/bin/python scripts/export_static_site_data.py
```

The backfill checks NIBE's report archive for new quarterly reports and year-end reports from 2024 onward. It rejects unrecognized PDF layouts instead of guessing columns. For a downloaded PDF, use `--pdf PATH --year YYYY --quarter N --filed YYYY-MM-DD --url ORIGINAL_URL`; `--facts-only` updates normalized issuer facts without recollecting the snapshot. Commit the normalized issuer facts along with SQLite and the static export so subsequent refreshes retain the history.

For an isolated repair when other exported symbols have newer price data than the local SQLite database, `scripts/export_static_site_data.py --snapshot-ticker NIBE-B.ST` publishes just the repaired snapshot and recomputes static metadata. It preserves the other exported snapshots and price-history files. Use this only after ensuring the repaired SQLite snapshot retains the latest price metrics.

### Coverage audit

```sh
.venv/bin/python scripts/audit_stock_data_coverage.py --output data/stocks/data-coverage.json
.venv/bin/python scripts/validate_revenue_growth_momentum.py --output /tmp/revenue-growth-momentum-report.json
```

The audit checks all exported symbols, distinguishes missing fundamental inputs from mathematically unavailable growth/valuation metrics, and validates the latest six revenue-growth quarters. Four growth observations meet the basic history target above; momentum requires six consecutive growth observations, usually at least ten consecutive revenue quarters. A large total history count does not guarantee that the latest six quarters are usable.

The 2026-10-08 audit after the NIBE repair covers 77 symbols. Remaining revenue-history gaps:

| Symbols | Remaining issue |
| --- | --- |
| `YPF` | No quarterly revenue history; latest quarterly revenue growth, EPS growth, profitability, FCF, and return metrics are also unavailable. Current SEC facts provide annual statements. |
| `AZN`, `B`, `CRM`, `NVS`, `ORCL`, `SPGI`, `STX` | Latest six revenue quarters contain a gap or duplicate fiscal period. These need period alignment/history repair, despite having older growth observations. |
| `BX` | FY2025 Q2 lacks a comparable prior-year revenue value. |

Other missing current inputs, as reported by the collector:

| Metric | Symbols |
| --- | --- |
| Quarterly free cash flow | `AZN`, `YPF` |
| Gross margin | `UBER`, `V`, `MA`, `HWM`, `UNP`, `INTU`, `YPF` |
| Operating margin | `COP`, `YPF` |
| ROIC inputs | `INOD`, `DDOG`, `ISRG`, `COP`, `YPF` |
| Debt / debt-to-equity inputs | `DDOG`, `ISRG` |
| EPS CAGR | `V` |
| EV/EBITDA inputs | `AXFO.ST`, `DT`, `DDOG`, `PLTR`, `TER`, `ISRG` |

Some metrics, such as gross margin for financial businesses, may not be comparable or explicitly reported. A missing debt fact also does not prove zero debt. These entries require source review rather than fabricated values. Negative earnings-growth cases and other explicitly not-meaningful metrics are listed separately in the JSON audit; an empty PEG is often intentional.

## 5. Relationship To GitHub Actions

Local is for completeness and repair. GitHub Actions are for updates.

The daily remote refresh should:

- Fetch recent SEC submissions for each ticker and use them as a cheap change detector.
- Recollect SEC tickers whose latest relevant filing changed or whose current fundamental inputs remain incomplete; preserve healthy unchanged snapshots. Historical momentum/CAGR gaps must not trigger daily collection.
- Recollect non-SEC tickers, check the newest supported issuer report, and try a bounded Yahoo statement fallback when current primary-source collection is unavailable or incomplete. Preserve verified history and report unresolved gaps. Older report downloads stay in the local backfill workflow.
- Add or update only facts that are newer or better.
- Export static JSON from the updated database.
- Commit `data/invest_os.sqlite` and tracked static data changes back to `main`.

The price refresh continues to run more frequently. It reads the checked-out SQLite database when available, falls back to the deployed static dataset when needed, updates price-derived metrics and histories, and commits both the database and tracked static data changes.

See [data-refresh.md](data-refresh.md) for the automated refresh model:

- SEC/fundamentals refresh once each weekday.
- Price and price-derived metric refresh every four hours on weekdays.
- Static export and GitHub Pages deployment after validation.
