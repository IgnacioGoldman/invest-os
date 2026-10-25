# Operating Margin Trend

## What it means?

_Is the company keeping more or less operating profit from its sales?_

Compares the company's latest quarterly operating margin with the same quarter one year earlier. It shows whether operating profitability is improving, staying the same or declining. For example, a margin rising from 15% to 20% is an improvement of 5 percentage points. A company can improve its margin while still making an operating loss.

## How is calculated?

`latest fiscal-quarter operating margin − operating margin in the same fiscal quarter last year`, in percentage points.

Each margin is `operating income / revenue × 100` and must pass the [Operating Margin](operating-margin.md) input checks. Both quarters must use matching currencies and definitions. If the prior-year margin is unavailable, the current Operating Margin can still be shown without the trend.

## Tags

- **Improving:** the operating margin increased; the change is above 0 percentage points.
- **Stable:** the operating margin is unchanged; the change is 0 percentage points.
- **Declining:** the operating margin decreased; the change is below 0 percentage points.

Tags use the unrounded change, with a tolerance of 1e−10 percentage points to remove floating-point noise at zero.
