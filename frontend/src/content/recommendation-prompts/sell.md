Audit the current Invest OS portfolio for sell, trim, and hold decisions.

Use:
- the current portfolio snapshot from the running Invest OS backend or app data
- saved investor profile and target allocation
- open orders and current cash/reserve context
- data/stocks/open_data/*/latest.json
- data/stocks/derived_signals/latest.json
- data/assets/derived_signals/latest.json

Read skills/portfolio-recommendations/trade-mentality.md and skills/portfolio-recommendations/allocation-drawdown-advisor.md before deciding.

Find:
1. one position that should be trimmed because of concentration, allocation drift, valuation, or risk
2. one position that should be exited or moved to a strict watchlist because the thesis/data has weakened
3. positions that should explicitly not be sold despite volatility

For each sell/trim candidate, include:
- symbol/platform
- current portfolio role and weight
- evidence supporting the decision
- suggested trim/exit size
- tax, liquidity, and opportunity-cost caveats
- what would invalidate the sell/trim decision
- a safer alternative action if confidence is not high

Ask for missing data only if it blocks the decision.
Save the result to data/stocks/ai_exit_analysis/latest.json.
Do not place trades.
