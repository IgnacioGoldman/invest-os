# Stock Insights

Stock Insights is the use-case layer of Exploration Beta. It explains what the table is meant to help with and how to interpret the main signals.

The goal is not to predict the future or produce buy/sell commands. The goal is to turn a large pile of public facts into a cleaner first-pass research view:

- Is this business growing?
- Is growth improving or weakening?
- Is the company profitable and cash-generative?
- Is valuation stretched or interesting?
- Is the current price near a detected support area?
- Is the data complete enough to trust the read?

## Main Inputs

Stock insights use public/open data snapshots:

- Business facts: latest-quarter revenue growth, EPS growth, margins, free cash flow, ROE/ROIC, cash, debt, and share count.
- Price facts: current price, 1D to 5Y returns, distance from all-time high, distance from 52-week high/low, and support-zone distance.
- Valuation facts: PE, forward PE estimate when available, PEG proxy, price/sales, EV/EBITDA proxy, FCF yield, and valuation history.
- Context facts: SEC facts, known data gaps, valuation percentiles, net cash/debt, FCF conversion, and price versus fundamentals.

Every metric carries a source and quality tier. Some values are exact public facts, some are computed from public facts, and some are proxy estimates. Proxy estimates are useful for screening, but should be treated with more humility.

## Core Use Cases

### Find Growing Businesses

Use revenue growth and EPS growth to identify companies that are expanding and converting that growth into shareholder earnings.

Helpful columns:

- Latest revenue growth YoY
- Revenue growth momentum
- Latest EPS growth YoY
- Revenue CAGR / EPS CAGR metrics in the wider table

### Spot Growth Acceleration Or Deceleration

Revenue growth momentum compares recent quarterly growth against prior quarters. This helps separate a business that is still improving from one that is growing but slowing.

Example:

- 8% to 12% to 16% revenue growth suggests acceleration.
- 25% to 20% to 15% still shows growth, but with deceleration.

### Check Profit Quality

Margins, free cash flow, ROE, and ROIC help answer whether growth is healthy or expensive to produce.

Useful questions:

- Are gross and operating margins stable or improving?
- Is the company producing free cash flow?
- Is ROIC meaningfully positive?
- Is debt low enough that the balance sheet is not dominating the story?

### Compare Valuation

Valuation metrics help show whether a good business is priced like a good business, an exceptional business, or a troubled business.

Useful questions:

- Is PE high or low versus history and peers?
- Is FCF yield attractive?
- Is price/sales stretched?
- Is EV/EBITDA usable for this company, or only a rough proxy?

### Review Price Setup

The stock price chart gives a simple line-chart view across ranges such as 1D, 1W, 1M, 3M, 6M, 1Y, 2Y, 5Y, and All.

Use it to answer:

- Is the stock extended or recently pulled back?
- Is the current price near recent support?
- Is the longer-term trend still intact?
- Did fundamentals improve while price moved sideways or down?

### Understand Near Support

Near support metrics estimate the distance from the latest close to a detected support zone within a lookback window. Short windows can reflect a nearby tactical shelf; longer windows use the primary support floor in that chart range.

Current support windows:

- Near 1M
- Near 6M
- Near 2Y
- Near 5Y

For example, a 5Y support value of `+90%` means the primary detected 5-year support floor is about 90% below the latest close. It does not mean price is near support on that chart.

The table shows both:

- distance from support, such as `+3.18%`
- inferred support level, such as `$304.89`

## What The App Is Good For

Exploration Beta is good for:

- screening many stocks quickly
- finding companies with strong or improving fundamentals
- comparing valuation and price setup in one view
- spotting names worth deeper manual research
- keeping a local, deterministic research cache
- refreshing only missing or stale stock data

## What The App Is Not

Exploration Beta is not:

- a broker
- a trade execution system
- a portfolio tracker
- a personal financial plan
- a live quote terminal
- a replacement for reading filings
- a guarantee that detected support will hold

## Practical Workflow

1. Refresh Exploration Beta.
2. Filter by sector, growth, valuation, support, or other table dimensions.
3. Expand interesting stocks to inspect price and growth charts.
4. Use support distance as a setup clue, not as a decision by itself.
5. Open the underlying metric tooltips when a number looks surprising.
6. Shortlist candidates for deeper research outside the table.
