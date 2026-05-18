# Invest OS

**Invest OS** is a local investment operating system for portfolio, cash, exposure, and order decisions.

It consolidates broker, exchange, and manual financial data into a structured snapshot, then uses a defined investment policy and AI analysis workflow to generate disciplined, human-approved recommendations.

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

## Data Sources

### API Sources

- Interactive Brokers
- Binance

Binance order history can also show an estimated account value before and after each trade. Use **Refresh Binance ledger** to fetch read-only deposit/withdrawal history and historical Binance prices into SQLite. The dashboard then replays cached trades, deposits, withdrawals, and fees locally.

This replay is intentionally conservative: if deposits/withdrawals, historical prices, or earlier trades are missing, the value columns stay blank and the row warning explains what is incomplete.

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
