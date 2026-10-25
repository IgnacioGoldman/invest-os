# Forward P/E

## What it means?

_How much does the share price imply for each unit of forecast earnings?_

Divides the current listing share price by a sourced annual forward EPS estimate. The estimate's horizon, date and accounting adjustments affect the comparison.

## How is calculated?

`current listing share price / positive annual forward EPS estimate`.

Require a provider source, estimate-as-of date, listing currency and an identifiable annual forecast horizon (fiscal year or next twelve months). Collection time alone is not an analyst revision date. Bare Yahoo `forwardPE` or `forwardEps` without a forecast horizon is insufficient. Never substitute historical EPS CAGR extrapolation or EPS reverse-engineered from a P/E. Missing, stale, loss-making, zero, currency-incompatible or undocumented inputs leave the value unavailable.

## How to interpret it?

A Forward P/E of 40 does not automatically mean expensive, and 10 does not automatically mean cheap. Growth expectations, risk and forecast reliability matter. A sourced forecast horizon and matching currency are required; quote and estimate must be no older than seven days. Historical EPS extrapolation is excluded.

This is a contextual metric. It has no deterministic classification rules or tags and does not participate in saved-filter matching, rankings or automatic scores.

## Display and history

Available in the expandable **Contextual metrics** section of stock details. The card opens its question, description, calculation, reporting dates, source identifiers and explanatory notes. Values and charts use neutral styling. Missing values remain unavailable, never zero.

No comparable saved ratio history is currently supplied. Keep the chart area explicit about missing history; never repeat the current value to fabricate a trend.

Source identifiers preserve provenance, not independent verification. See the [metric index](../README.md).
