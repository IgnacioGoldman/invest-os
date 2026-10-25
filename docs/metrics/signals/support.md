# Support

## What it means?

_How close is the stock's price to an area where buyers have recently stepped in?_

Compares the latest closing price with a detected support zone. It shows whether the stock is trading inside or above a price area where earlier declines found buyers. For example, a price of $364 and a support midpoint of $349 gives a distance of about +4.3%. A support zone is an estimate; the price can fall through it.

## How is calculated?

`(latest closing price / support zone midpoint − 1) × 100`.

For each selected window (1M, 3M, 6M, 1Y, 2Y or 5Y), find swing lows in daily price history and group nearby lows into price clusters. Use daily lows when available, otherwise closing prices. Cluster width adjusts for volatility and is capped at 4%.

The 1M window can use one touch. Longer windows need at least two touches separated by at least 15 days. Zones entirely above the latest close, stale zones and areas resembling reclaimed resistance are excluded. The lowest price on the chart therefore does not necessarily qualify as support.

The zone and quote must share a source-linked date within the last seven days. If no valid zone exists or the quote is below it, hide the metric for that window.

## Tags

- **At Support:** the latest price is inside the detected zone, including its boundaries. Distance from the midpoint can be negative.
- **Near Support:** the latest price is above the zone and no more than 6% above its midpoint.
- **Above Support:** the latest price is above the zone and more than 6% above its midpoint.

At Support uses bright green, Near Support light green and Above Support yellow to show proximity.
