### Forward P/E

Forward P/E compares the **current share price with expected earnings per share for a future annual period**, commonly the next 12 months or the next fiscal year, depending on the estimate source.

Trailing P/E uses earnings already reported. Forward P/E uses an earnings estimate, which gives a first-pass view of the price investors are paying for expected profits. Estimates can change after results, guidance updates, or changes in business conditions, so the estimate period and source matter.

Formula:

```text
Forward P/E = Current Share Price / Expected Annual EPS
```

Or, when the app uses its historical-growth proxy:

```text
Expected Annual EPS Proxy = Trailing EPS * (1 + 3-Year EPS CAGR % / 100)
Forward P/E Proxy = Current Share Price / Expected Annual EPS Proxy
```

For example, a $100 share price and expected annual EPS of $5 produce a Forward P/E of 20x. Investors are paying $20 for each $1 of expected annual earnings per share.

The app prefers the public forward P/E estimate from Yahoo Finance when available. Its underlying estimate methodology is not independently verified by the app. When that estimate is unavailable, the app can use trailing EPS grown by its SEC-derived 3-year EPS CAGR as a proxy. The proxy is an extrapolation of historical earnings growth; check the metric source, tier, and notes to identify which value is shown. A meaningful earnings multiple requires positive expected EPS and a share price and EPS expressed in the same currency.

Why I’d put this next: growth and free cash flow describe the business. Forward P/E adds the price being paid for its expected earnings, helping put that business performance in valuation context.

### Tags

Forward P/E is a valuation metric, so its tags should describe the earnings multiple.

Suggested tags, using the app’s existing forward P/E cutoffs as a first-pass guide:

- **Cheap:** Forward P/E is positive and 18x or lower. The price is relatively low compared with expected earnings.
- **Fair:** Forward P/E is above 18x and up to 25x. The earnings multiple is moderate.
- **Pricey:** Forward P/E is at least 35x but below 50x. The price assumes substantial future earnings strength.
- **Very pricey:** Forward P/E is 50x or higher. The price is especially sensitive to earnings expectations.
- **Unclear:** Forward P/E is above 25x but below 35x, the estimate is missing, or expected EPS is zero or negative. This first-pass guide does not assign a clear valuation tag.

The app’s displayed valuation tag combines Forward P/E with FCF yield, price/sales, and EV/EBITDA, so it can differ from these individual-metric tags. A Cheap tag also requires available FCF yield and price/sales values to pass the app’s checks; other valuation measures can trigger a Pricey or Very pricey tag.

These thresholds should be treated as a first-pass signal. A high multiple may reflect strong expected growth, while a low multiple may reflect declining earnings, cyclical peak profits, or weak estimate confidence. Read the tag together with sector, revenue and EPS growth, free cash flow, debt, and the reliability of the earnings estimate.
