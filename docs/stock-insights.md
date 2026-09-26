# Stock Insights

This page explains how the Exploration stock table forms the Business, Price, Valuation, and Conviction signals.

The goal is not to predict the future or produce a buy/sell command. The goal is to turn a large pile of public facts into a cleaner first-pass view: is this a good business, is the current price interesting, is valuation stretched, and how complete is the evidence?

## Main Inputs

Stock insights use public open-data snapshots, mainly:

- Business facts: latest-quarter revenue growth, adjusted EPS growth, GAAP EPS growth, EPS alignment, margins, free cash flow, returns on equity/capital, cash, debt, and share count.
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

### Adjusted EPS Growth YoY

_Is the company generating more underlying earnings for shareholders?_

Compares adjusted earnings per share with the same quarter last year. It aims to show how the ongoing business is performing by excluding certain unusual or non-recurring items reported by the company. The app only fills this when it can parse a high-confidence Adjusted EPS or Non-GAAP EPS YoY percentage from an official SEC earnings-release exhibit. For example, Adjusted EPS +25% suggests underlying earnings per share are improving, while Adjusted EPS -10% suggests the core earnings trend is weakening.

### GAAP EPS Growth YoY

_Is the company reporting more profit per share than a year ago?_

Compares GAAP diluted earnings per share with the same quarter last year. It reflects the company’s official reported earnings after operating costs, interest, taxes, changes in share count, and other accounting gains or losses. Because unusual items can affect GAAP earnings, a very strong or weak result does not always mean the underlying business changed by the same amount. For example, GAAP EPS +80% may look very strong, but part of that increase could come from a large investment gain.

### EPS Alignment

_Are adjusted and reported earnings telling the same story?_

Compares the adjusted and GAAP EPS trends to see how closely they agree. High alignment means both measures point to a similar earnings trend, while low alignment suggests that unusual or excluded items are materially affecting reported earnings. For example, Adjusted EPS +25% / GAAP EPS +22% shows strong alignment, while Adjusted EPS +25% / GAAP EPS +80% signals a large divergence that may need further investigation.

### Free Cash Flow Margin

_Is the company turning its revenue into actual cash?_

Measures free cash flow as a percentage of revenue. It shows how much cash the business keeps after paying operating costs and capital expenditures. This is especially useful because revenue and EPS can look strong while cash generation is weak.

## Price

### Proximity to support

_Is the current price close to a nearby support zone?_

Compares the current price with a detected support zone from recent daily price history. Support means a clustered swing-low area with enough touches to look like a practical floor, not simply the lowest price in the range. Closer to 0% means the stock is nearer support; the window label shows which price range produced the signal. See [Support](metrics/support.md) for the calculation details.

## Valuation

### Forward P/E

_How expensive is the stock relative to expected earnings?_

Compares the current share price with analysts’ expected earnings per share over the next 12 months. It helps answer whether investors are already paying a high price for the company’s expected growth.
A high Forward P/E is not automatically bad if earnings are expected to grow quickly. A low Forward P/E is not automatically attractive if earnings are stagnating or falling.
