# Invest OS

**Invest OS** is a local investment operating system for portfolio, cash, exposure, and order decisions. It consolidates broker, exchange, and manual financial data into a structured snapshot, then uses a defined investment policy and AI analysis workflow to generate disciplined, human-approved recommendations.

Invest OS is read-only. It does not place, modify, cancel, transmit, or automate trades.

Dashboard reads are cache-only: page load and `GET` endpoints read from local SQLite and never call Binance or IBKR. External sources are contacted only when you use `POST /api/refresh`.

## Core Use Cases

| Area | Use Case | Key Question | Output |
|---|---|---|---|
| **Unified Portfolio Snapshot** | Consolidate API + manual data | What do I own across IBKR, Binance, bank cash, and manual sources? | Net worth, holdings, cash, top positions, platform breakdown |
| **Manual Assets & Cash** | Track non-connected money/assets | What cash, bank balances, and external holdings exist outside APIs? | Manual ledger with balances, positions, purpose, confidence, and staleness |
| **Market & Allocation Exposure** | Check under/over-investment | Am I too exposed to markets, crypto, stocks, sectors, currencies, or platforms? | Exposure vs target policy, allocation breakdowns, concentration warnings |
| **Sector / Vertical Analytics** | Understand thematic exposure | What themes, verticals, geographies, and sectors am I invested in or missing? | Exposure map and blind-spot analysis |
| **Order & Exit Management** | Review open orders and suggest buy/sell actions | What orders exist, do they make sense, what orders should I consider, and which holdings lack an exit plan? | Keep/modify/cancel/review, buy-limit, take-profit, trim, stop-loss, trailing-stop ideas, conflict warnings |
| **Investment Policy** | Anchor recommendations to rules | Are suggestions consistent with my targets and risk limits? | Cash reserve, max crypto, max single position, market exposure limits |
| **Behavior Analytics** | Learn from trade history | Am I repeating good or bad trading patterns? | Holding-period, win/loss, overtrading, exit-quality insights |
| **Daily Decision Review** | Prioritize next actions | What should I review or act on today/this week? | Ranked action list |
| **AI Analysis Package** | Feed Claude/Codex consistent inputs | Can an LLM generate structured recommendations from clean data? | Snapshot, orders, policy, metadata, prompt/skill files |
| **Recommendation Format & Approval** | Standardize human-approved decisions | What is recommended, why, under what conditions, and with what confidence? | Action, evidence, risk, conditions, confidence, missing data; no auto-trading |

## Run locally

```sh
trap 'kill 0' EXIT; (cd backend && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000) & (cd frontend && npm run dev -- --host 0.0.0.0)
```

Open http://localhost:5173/.

## AI Workflows

### Portfolio Recommendations

"Analyze Portfolio"

Portfolio recommendation prompts live under:

```text
skills/portfolio-recommendations/
```

The backend loads all Markdown files in that folder when generating portfolio
recommendations.

### Stock Analysis

#### Step 0 - Build a balanced stock universe

```sh
python scripts/build_stock_universe.py
```

This writes `data/stocks/stocks.json` with 500 liquid US/ADR tickers, scored
by liquidity, activity, size, spread, volatility, and data quality, then capped
by region and sector.

#### Step 1 - Data Collection (deterministic)

```sh
python scripts/open_data_poc.py --universe-file data/stocks/stocks.json --output data/stocks/open_data_collection_500.json --workers 8 --checkpoint-every 10 --skip-filing-details
```

Collects public facts, price history, valuation inputs, annual fundamentals,
SEC filing metadata, and data gaps into `data/stocks/open_data/<TICKER>/`.
The 500-ticker command skips per-filing SEC archive exhibit lookups to avoid
archive rate limits; omit `--skip-filing-details` when you want deeper filing
context for a smaller run. For one symbol, run `python scripts/open_data_poc.py GOOGL`.

#### Step 2 - Derived Signals (deterministic)

```sh
python scripts/build_stock_derived_signals.py
```

Writes `data/stocks/derived_signals/latest.json`. It surfaces what is
numerically unusual: valuation percentiles, growth acceleration, margin deltas,
FCF conversion, net cash/debt, share-count change, sector ranks, and
price/fundamental gaps. This is needed so the AI sees patterns and anomalies,
not only raw metrics.

#### Step 3 - AI Candidate Analysis (non-deterministic)

Give Codex:

```text
Analyze Stocks using skills/stock-analysis/stock-entry-analyst.md. Use data/stocks/open_data/*/latest.json and data/stocks/derived_signals/latest.json to find one long-term entry candidate and one short-term setup candidate. Use current context for finalists, return evidence-bound JSON, ask for missing data when needed, and save the result to data/stocks/ai_candidate_analysis/latest.json.
```

### Multi-Asset Opportunity Analysis

#### Step 0 - Keep stock deterministic artifacts fresh

Run the stock universe, stock open-data collection, and stock derived-signal
steps above. Stocks keep their own richer equity-specific facts.

#### Step 1 - Build ETF, commodity-proxy, and crypto signals

```sh
python scripts/build_asset_derived_signals.py
```

This writes `data/assets/derived_signals/latest.json`. It collects free/public
deterministic market facts for:

- ETFs: price returns, drawdowns, volatility, liquidity, expense ratio, yield,
  AUM, exposure, and portfolio-fit score.
- Commodity proxies: gold, silver, platinum, palladium, copper, broad
  commodities, and oil proxies with price/risk/liquidity/fit metrics.
- Crypto: Binance public price history, returns, drawdowns, volatility,
  liquidity, 24h volume/change, and portfolio-fit score.

Use `--no-portfolio-fit` if you want pure market signals without reading the
cached portfolio snapshot.

#### Step 2 - AI Portfolio Entry Analysis

Use the dashboard **Analyze** button or ask Codex:

```text
Analyze Portfolio using skills/portfolio-recommendations/. Use the portfolio snapshot, data/assets/derived_signals/latest.json, data/stocks/derived_signals/latest.json, and data/stocks/open_data/*/latest.json. Decide whether the next best action is stock, ETF, commodity proxy, crypto, cash reserve, trim/exit, or wait.
```

The dashboard shows separate deterministic tables for **Stocks Insights**,
**ETF Insights**, **Crypto Insights**, and **Commodities Insights**. The AI
recommendation backend receives the portfolio snapshot plus deterministic
multi-asset opportunity context when those files exist.
