# Support

Support is the app's estimate of a price area where buyers have recently stepped in. It is a research signal, not a guarantee that the price will hold.

## What It Means

A support zone is not simply the lowest price on the chart. The app looks for swing lows that happen around the same price area and treats that cluster as a possible floor.

The support value is shown as distance from the latest close to the support zone midpoint.

Example:

- Current price: `$364`
- Support midpoint: `$349`
- Support distance: about `+4%`

That means the latest close is about 4% above the detected support area.

## How It Is Calculated

For each window, such as 1M, 3M, 6M, 1Y, 2Y, or 5Y, the app:

1. Looks at daily price history.
2. Finds swing lows using the daily low price when available, otherwise the close.
3. Groups nearby swing lows into price clusters.
4. Uses a wider cluster for more volatile stocks, capped at 4%.
5. Requires enough separated touches for the window.
6. Filters out zones above the latest close, stale zones, and areas that look more like reclaimed resistance than support.
7. Reports the distance from the latest close to the selected zone midpoint.

Short windows can be more tactical. The 1M window can use one touch. Longer windows, including 3M, 6M, 1Y, 2Y, and 5Y, need at least two touches separated by at least 15 days.

## Why The Lowest Price May Not Be Support

Sometimes a stock drops sharply, bounces, and still does not mark that low as support. One bounce is only one event. For a longer window, the app wants to see the same area tested again.

For TSLA, the 1Y chart can show support near `$348` even though the price dropped to roughly `$298` and then rebounded. The `$298` area was a single swing-low event in that 1Y history. The `$348` area had two qualifying touches in the same cluster, so the app treated `$348` as the 1Y support zone.

## How To Use It

Use support as a setup clue:

- Near support can mean the current price is close to a recent floor.
- Far above support can mean the current price has already moved a long way from the detected floor.
- No support means the app did not find a usable zone for that window.

Support should be read together with trend, business quality, valuation, news, and your own risk rules.
