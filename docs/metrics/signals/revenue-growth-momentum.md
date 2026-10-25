# Revenue Growth Momentum

## What it means?

_Is the company's growth getting stronger or weaker?_

Compares the company's typical recent revenue growth with its earlier growth. It shows whether sales growth is speeding up, holding a similar pace or slowing down. For example, moving from typical growth of 10% to 16% means growth accelerated by 6 percentage points. Growth can slow down while sales are still increasing.

## How is calculated?

`median(latest four quarterly revenue YoY growth rates) − median(preceding four quarterly revenue YoY growth rates)`, in percentage points.

With only six or seven comparable observations, use the latest six and compare three quarters with the preceding three. At least six consecutive quarterly YoY growth rates are required. The median is the middle value after sorting; for four values, average the middle two. This reduces the influence of an unusual quarter.

## Tags

- **Accelerating:** the recent median growth rate is at least 3 percentage points higher.
- **Steady:** the change is greater than −3 and less than +3 percentage points.
- **Decelerating:** the recent median growth rate is at least 3 percentage points lower.

The saved-filter alias **Stable** means Steady. Tags use the unrounded calculation.
