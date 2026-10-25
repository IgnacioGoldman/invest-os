# Revenue Growth Consistency

## What it means?

_Has quarterly revenue growth followed a regular pattern?_

Looks at how smoothly the company's revenue growth has changed over recent quarters. It helps distinguish a regular trend from sudden spikes and reversals. For example, growth of 12%, 14%, 16%, 18%, 20% and 22% follows a steady pattern, while 15%, −5%, 30%, 2%, 40% and −10% is choppy. A steady pattern can include slowing growth or declining sales.

## How is calculated?

Use the same history as Revenue Growth Momentum: the latest eight comparable consecutive quarterly YoY growth rates, or the latest six when eight are unavailable.

`tolerance = max(3 percentage points, 25% × median(absolute quarterly YoY growth rates))`.

`largest change in growth pace = max(abs(g[i] − 2 × g[i−1] + g[i−2]))`, where `g` contains the growth rates in chronological order.

The pattern is steady when the largest change in growth pace stays within the tolerance. It is also steady when there is a sustained shift to a new level: the history can be split into two groups of at least three quarters each, with every value within the tolerance of its group's median. For example, 1%, 1%, 1%, 80%, 80%, 80% qualifies as a sustained shift. A single spike does not.

## Tags

- **Steady:** growth follows a smooth trend or a sustained shift to a new level.
- **Choppy:** growth has abrupt changes that fail both regularity checks.

At least six comparable observations are required; insufficient history hides the metric rather than assigning a tag.
