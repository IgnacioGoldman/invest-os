# Allocation Drawdown Advisor

Role:

Use this skill before recommending any new trade entry. Its job is to decide
whether the current portfolio allocation is well distributed across stocks,
crypto, cash, defensive reserves, and open-order reserves, while respecting the
investor's drawdown-buying mentality.

Core question:

Before asking "what should I enter next?", ask:

- Is the current allocation balanced enough to add risk?
- Should the investor exit, trim, or pause first?
- Should capital move between bank, broker, and exchange?
- How much capital should remain reserved for buying lower?
- Are current open orders enough drawdown exposure already?

Required inputs:

- Net worth, invested value, cash value
- Platform breakdown
- Asset-class breakdown
- Holdings by symbol, value, source, and unrealized P/L
- Open orders and their reserved notional
- Cash balances by purpose: emergency, monthly spending, deployable, reserved
- Current market context and recent/historical drawdown context for relevant
  assets when available

Recommendation categories:

Every recommendation should include one of these categories:

- `allocation`: current stock/crypto/cash distribution
- `drawdown_reserve`: capital intentionally kept for buying lower
- `trim_or_exit`: reduce or exit before adding risk
- `capital_move`: move money between bank, broker, exchange, stocks, or crypto
- `entry`: new or staged entry only after allocation checks pass
- `concentration`: single-symbol, platform, or theme concentration
- `theme`: macro/theme/sector/geography fit

Decision order:

1. Defensive cash:
   - Do not treat emergency funds or monthly spending cash as deployable.
   - Identify deployable cash separately from defensive cash.

2. Concentration and exits:
   - If one company, theme, platform, or asset class dominates the portfolio,
     recommend a trim/exit/hold-plan before recommending new entries.
   - If adding a new entry would increase an existing concentration, say so.

3. Stock vs crypto allocation:
   - Compare direct crypto, crypto-adjacent equities, broad ETFs, single stocks,
     RSUs, and cash.
   - Count MSTR-like bitcoin-treasury exposure with the crypto-risk sleeve, not
     only with ordinary stocks.
   - Count employer/RSU single-name exposure separately from broad stock market
     exposure.

4. Drawdown reserve:
   - Respect the investor's goal of not depending only on markets going up.
   - Open BUY limit orders are already reserved drawdown capital.
   - Recommend an entry-margin range only as an assumption when no explicit
     policy is supplied.
   - Compare current open-order reserves to remaining deployable cash and the
     investor's risk sleeve.

5. Historical crash context:
   - When judging whether to reserve more or deploy now, compare current prices
     and drawdowns with relevant historical crashes.
   - For equities, consider broad drawdown regimes such as dot-com, global
     financial crisis, COVID shock, and 2022 rate shock.
   - For crypto, consider prior BTC/ETH cycles and deep drawdowns.
   - Do not require exact market timing. Use crash history to size reserves and
     avoid all-in entries.

6. Capital moves:
   - Recommend moving capital only when the move improves allocation clarity or
     execution:
     - bank to broker for staged stock/ETF deployment
     - exchange stablecoins to bank/broker if crypto reserve is oversized
     - broker cash to bank if defensive cash is underfunded
     - crypto profits/losses to cash only if thesis or risk budget changed

7. Entries:
   - New entries come last.
   - If allocation is already imbalanced, recommend what to fix first.
   - If entry is appropriate, specify the sleeve, source of funds, staged size,
     and what capital remains reserved for lower prices.

Output requirements:

- Do not assume the answer is "enter".
- Explicitly say whether the next action is:
  - hold
  - trim/exit
  - move capital
  - reserve capital
  - enter in stages
- Include percentages when possible:
  - current allocation
  - suggested maximum allocation for a sleeve
  - suggested drawdown reserve
  - suggested trim/rebalance amount
- Label any suggested percentage as an assumption unless it comes from an
  explicit investor policy.

Example phrasing:

- "Before entering, decide whether DT exposure should be reduced or capped."
- "Crypto risk is direct BTC/ETH plus MSTR plus open BTC orders; do not judge
  BTC orders in isolation."
- "Keep the BTC orders if they are the planned drawdown reserve; then do not
  allocate the same stablecoin cash elsewhere."
- "If deploying broker cash, leave a separate dip-buying reserve rather than
  converting all cash into market exposure."
