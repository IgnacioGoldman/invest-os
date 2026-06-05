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

This writes `data/stocks/stocks.json` with 100 liquid US/ADR tickers, scored
by liquidity, activity, size, spread, volatility, and data quality, then capped
by region and sector.

#### Step 1 - Data Collection (deterministic)

```sh
python scripts/open_data_poc.py GOOGL
```

#### Step 2 - Analysis (deterministic)

"Analyze Stocks"

Stock-analysis prompts live under:

```text
skills/stock-analysis/
```

The stock-analysis skill is designed for the future non-deterministic AI step.
It should consume collected facts only, avoid guessing, identify missing data,
and ask for more data when the supplied facts are insufficient.
