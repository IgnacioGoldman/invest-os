# Invest OS

**Invest OS** is a local investment operating system for portfolio, cash, exposure, and order decisions.

It consolidates broker, exchange, and manual financial data into a structured snapshot, then uses a defined investment policy and AI analysis workflow to generate disciplined, human-approved recommendations.

## MVP: Unified Portfolio Snapshot

This initial MVP is a local-only FastAPI + React app that answers:

**What do I own across IBKR, Binance, bank cash, and manual sources?**

It produces:

- Net worth
- Invested value
- Cash
- Holdings
- Top positions
- Platform breakdown
- Asset class breakdown
- Open orders
- Recent order history where an API exposes it
- Data warnings when a source is missing or unavailable

Invest OS is read-only. It does not place, modify, cancel, transmit, or automate trades.

Dashboard reads are cache-only: page load and `GET` endpoints read from local SQLite and never call Binance or IBKR. External sources are contacted only when you use `POST /api/refresh`.

## Project Structure

```text
invest-os/
  backend/
    app/
      main.py
      config.py
      models.py
      snapshot.py
      sources/
        binance.py
        ibkr.py
        manual.py
      services/
        normalization.py
        portfolio.py
    requirements.txt
  frontend/
    package.json
    src/
      App.tsx
      api.ts
      components/
  data/
    manual/
      cash.yaml
      assets.yaml
    invest_os.sqlite
  .env.example
```

## Setup

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at:

```text
http://localhost:8000
```

Key endpoints:

- `GET /api/snapshot`
- `GET /api/holdings`
- `GET /api/cash`
- `GET /api/orders/open`
- `GET /api/orders/history`
- `POST /api/refresh`

`POST /api/refresh` accepts:

```json
{ "source": "all" }
```

Allowed source values:

- `all`
- `binance`
- `ibkr`
- `ibkr_history`
- `manual`

Refreshing one source replaces only that source's normalized records in SQLite. The dashboard reloads from SQLite after the refresh completes.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at:

```text
http://localhost:5173
```

If your API runs somewhere else, set:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Configuration

Create a local `.env` from the example:

```bash
cp .env.example .env
```

Supported values:

```dotenv
BASE_CURRENCY=EUR
FX_RATES_JSON={}

BINANCE_API_KEY=
BINANCE_API_SECRET=

IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1

ENABLE_DEMO_FALLBACK=true
```

`FX_RATES_JSON` is optional and used only for local total calculations when a source reports non-EUR values. Example:

```dotenv
FX_RATES_JSON={"USD":0.92,"USDT":0.92,"USDC":0.92,"GBP":1.17,"SEK":0.086}
```

API secrets are loaded from `.env` and are never logged by the app.

## Data Sources

## Local SQLite Cache

Normalized data is stored in:

```text
data/invest_os.sqlite
```

Tables:

- `holdings`
- `cash_balances`
- `open_orders`
- `order_history`
- `source_sync_status`

`source_sync_status` tracks each source's `last_synced_at`, `status`, and `warning`.

`GET` endpoints read this cache only. Use the frontend refresh dropdown or `POST /api/refresh` to update cached source data.

### Manual Data

Manual data lives in:

```text
data/manual/cash.yaml
data/manual/assets.yaml
```

Manual cash fields:

- `account_name`
- `platform`
- `currency`
- `balance`
- `purpose`: `emergency_fund | deployable_cash | tax_reserve | monthly_spending | other`
- `updated_at`
- `notes`

Manual asset fields:

- `symbol`
- `name`
- `asset_class`
- `platform`
- `quantity`
- `currency`
- `estimated_price`
- `cost_basis`
- `sector`
- `vertical`
- `geography`
- `updated_at`
- `notes`

The example YAML files are intentionally simple. Replace them with your own local data or empty the lists. Manual YAML changes appear in the dashboard after `POST /api/refresh` with `manual`, or after selecting "Refresh manual cash & assets" in the UI.

### Binance

Set:

```dotenv
BINANCE_API_KEY=
BINANCE_API_SECRET=
```

The Binance adapter fetches account balances, open orders, and recent trades for detected symbols where the API allows it. It uses signed read endpoints only and never calls trading endpoints that place, change, or cancel orders.

If credentials are missing or Binance is unavailable, the snapshot still loads manual data and includes a warning.

### Interactive Brokers

Set:

```dotenv
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
```

TWS or IB Gateway must be running locally with API access enabled. The app connects with `ib_insync` in read-only mode, fetches portfolio positions, cash balances, open orders, and available recent executions.

Common local ports:

- TWS live: `7496`
- TWS paper: `7497`
- IB Gateway live: `4001`
- IB Gateway paper: `4002`

If TWS/Gateway is not running, the snapshot still loads manual data and includes a warning.

## Normalized Snapshot

The backend normalizes all sources into:

- `Holding`
- `CashBalance`
- `Order`
- `PortfolioSnapshot`

`GET /api/snapshot` returns the full normalized snapshot with totals, breakdowns, top positions, open orders, order history, and source warnings.

When no real or manual data is available and `ENABLE_DEMO_FALLBACK=true`, the backend returns small demo data so the frontend remains usable while credentials are not configured.

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

## Data Sources

### API Sources

- Interactive Brokers
- Binance

### Manual Sources

- Bank cash
- External broker holdings
- Private/manual assets
- Other unconnected sources

Example manual entries:

- Cash in bank account
- 1,000 Dynatrace shares in E*TRADE
- Private investment
- Offline asset
- Reserved cash bucket

## Recommendation Philosophy

Invest OS does **not** automatically place trades.

The system generates structured **order ideas** and **portfolio recommendations** for human review.

Examples:

- Consider placing a buy-limit order
- Consider trimming an overweight position
- Review or cancel stale open orders
- Add an exit plan to unmanaged positions
- Avoid new buying if exposure limits are already exceeded
- Highlight missing data before making a recommendation

## Human Approval Required

All outputs are advisory.

The system should help answer:

1. What do I own?
2. How exposed am I?
3. What orders are currently open?
4. Do those orders still make sense?
5. Which holdings need exit plans?
6. What buy/sell ideas should I consider?
7. What risks or blind spots should I review?
8. What should I act on today or this week?

Final investment decisions and order placement remain manual.
