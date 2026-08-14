# Stock Insights

This page explains how the Exploration stock table forms the Business, Price, Valuation, and Conviction signals.

The goal is not to predict the future or produce a buy/sell command. The goal is to turn a large pile of public facts into a cleaner first-pass view: is this a good business, is the current price interesting, is valuation stretched, and how complete is the evidence?

## Main Inputs

Stock insights use public open-data snapshots, mainly:

- Business facts: revenue growth, EPS growth, margins, free cash flow, returns on equity/capital, cash, debt, and share count.
- Price facts: current price, 1 day to 5 year price changes, distance from all-time high, distance from 52 week high/low, volatility, and support-zone distance.
- Valuation facts: trailing PE, forward PE estimate when available, PEG proxy, price/sales, EV/EBITDA proxy, FCF yield, and valuation history.
- Context facts: recent SEC filings, known data gaps, peer ranks, valuation percentiles, net cash/debt, FCF conversion, and price versus fundamentals.

Every metric carries a source and quality tier. Some values are exact public facts, some are computed from public facts, and some are proxy estimates. Proxy estimates can be useful, but the UI should treat them with more humility.

## Business

Business asks: does the company itself look healthy?

The app checks whether enough facts exist to judge the company. A stock can be marked `Unclear` when key business facts are missing.

The strongest business label needs several things to be true at once:

- Revenue growth is meaningfully positive.
- EPS growth is meaningfully positive.
- Operating margin is strong.
- Return on equity is strong.
- Cash generation and balance-sheet facts are available.

The labels are:

- `Strong`: growth, profitability, returns, and cash generation look strong.
- `Solid`: good fundamentals, but not elite across the board.
- `Mixed`: some facts are good and others are weaker or less clean.
- `Weak`: several core business facts look poor or deteriorating.
- `Unclear`: not enough business facts to classify.

## Price

Price asks: is the current quote offering a useful entry point?

A good company can still be a poor entry if the stock is extended. A falling stock can look cheap, but still be risky if the move looks unstable.

The app looks at short-term pullbacks, longer-term trend, distance from highs, and nearby support.

The labels are:

- `Pullback`: meaningful pullback while the longer trend remains healthy.
- `Better spot`: off highs and less stretched, but not a clear bargain.
- `Deep pullback`: meaningfully below highs, but trend is weak or sideways.
- `Strong trend`: uptrend is strong, but this is more momentum than discount.
- `No dip`: near highs or still stretched, with no useful pullback.
- `Falling`: large drawdown or weak trend evidence; possible falling-knife setup.
- `Unclear`: not enough price facts to classify.

## Valuation

Valuation asks: is the price reasonable for the business?

The app compares current valuation to both absolute guardrails and the company's own available history. It uses PE, forward PE, price/sales, EV/EBITDA, FCF yield, and historical ranges where available.

The labels are:

- `Cheap`: attractive versus available history, with enough valuation history to trust the signal.
- `Fair`: not cheap, but not obviously expensive either.
- `Slightly expensive`: elevated, but not severely stretched.
- `Pricey`: clearly expensive on available valuation facts.
- `Very pricey`: stretched on multiple valuation measures.
- `Unclear`: not enough valuation facts to classify.

If valuation history is unreliable or incomplete, the app avoids giving the strongest cheap label even when the current numbers screen well.

## Conviction

Conviction is a 0-10 summary score for the entry setup.

It combines the three big questions:

- Business: is this a company worth studying?
- Price: is the entry point attractive or risky?
- Valuation: does the price make sense?

The score starts from a base:

- Around `4.5` when important data is missing.
- Around `5.0` when the business is not high quality.
- Around `5.6` when the stock is extended and not near support.
- Around `6.8` for a quality setup with valuation caveats.
- Around `7.0` to `7.4` for a quality business near support or in a healthier pullback.

Then the app applies smaller adjustments from derived signals.

Positive adjustments can come from:

- Unusual valuation reset.
- PE below the company's historical median.
- High FCF-yield percentile versus history.
- Cheapness versus sector peers.
- Price weakness while fundamentals are still growing.
- Net cash balance sheet.
- Strong FCF conversion.
- Good growth plus FCF yield.

Negative adjustments can come from:

- PE well above the company's historical median.
- Weak FCF-yield percentile.
- Expensive sector-relative valuation.
- Price running far ahead of fundamentals.
- High net debt versus FCF.
- Weak FCF conversion.
- Weak sector revenue rank.
- Falling operating margin.
- Meaningful share dilution.

The adjustment is intentionally limited so one clever-looking metric cannot dominate the whole judgment.

## Score Bands

The UI reads conviction like this:

- `0-3`: weak, avoid, or insufficient facts.
- `4-5`: interesting but too uncertain.
- `6-7`: interesting setup with meaningful caveats.
- `8-10`: very strong setup with cleaner valuation, price action, and evidence.

There are also caps:

- If important data is missing, conviction cannot rise above `5.2`.
- If price action looks like a falling knife, conviction cannot rise above `6.3`.
- If there is no useful dip, conviction cannot rise above `6.0`.

These caps are important. They stop the app from presenting a high-confidence idea when the setup still has a basic problem.

## Opportunity Type

The app also gives a plain-language opportunity type:

- `Quality compounder pullback`: good business, temporarily less stretched.
- `Momentum continuation`: longer trend is strong, but it is more trend-following than bargain hunting.
- `Temporary selloff`: price has pulled back, but the facts do not prove a deeper bargain.
- `Falling knife risk`: price action is weak enough that waiting may be wiser.
- `Insufficient data`: facts are not complete enough to judge.

## How To Read It

Use conviction as a triage signal, not a final decision.

A high score means the stock deserves more attention. A low score means either the setup is weak or the facts are not clean enough yet. The best candidates usually have a healthy business, an entry price that is not stretched, valuation that is not extreme, and enough evidence to explain why the score exists.

