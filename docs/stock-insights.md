# Stock Insights

This page explains how the Exploration stock table forms the Business, Price, Valuation, and Conviction signals.

The goal is not to predict the future or produce a buy/sell command. The goal is to turn a large pile of public facts into a cleaner first-pass view: is this a good business, is the current price interesting, is valuation stretched, and how complete is the evidence?

## Main Inputs

Stock insights use public open-data snapshots, mainly:

- Business facts: latest-quarter revenue growth, EPS growth, margins, free cash flow, returns on equity/capital, cash, debt, and share count.
- Price facts: current price, 1 day to 5 year price changes, distance from all-time high, distance from 52 week high/low, volatility, and support-zone distance.
- Valuation facts: trailing PE, forward PE estimate when available, PEG proxy, price/sales, EV/EBITDA proxy, FCF yield, and valuation history.
- Context facts: recent SEC filings, known data gaps, peer ranks, valuation percentiles, net cash/debt, FCF conversion, and price versus fundamentals.

Every metric carries a source and quality tier. Some values are exact public facts, some are computed from public facts, and some are proxy estimates. Proxy estimates can be useful, but the UI should treat them with more humility.

## Business

### Latest Revenue Growth YoY 

_Is the business growing right now?_

Compares the latest quarter’s revenue with the same quarter last year. It tells you whether customers are spending more with the company and whether the overall business is expanding. For example, +15% means the company generated 15% more revenue than one year ago.

### Revenue Growth Momentum 

_Is the company’s growth getting stronger or weaker?_

Looks at how the revenue growth rate is changing between quarters. A company growing 8% → 12% → 16% is accelerating, while 25% → 20% → 15% is still growing strongly but slowing down. This helps you detect improvement or deterioration before revenue actually turns negative.

### Latest EPS Growth YoY

_Is the company converting its business into more earnings for shareholders?_

Compares earnings per share with the same quarter last year. Revenue can grow while costs grow even faster, so EPS tells you whether that growth is actually producing more profit per share. For example, Revenue +15% / EPS +25% is generally healthier than Revenue +15% / EPS -10%