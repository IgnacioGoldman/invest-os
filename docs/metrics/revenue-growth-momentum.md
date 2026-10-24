# Revenue Growth Momentum

Prefer eight comparable consecutive quarterly YoY observations: median(latest four) minus median(previous four), in percentage points. With six or seven usable latest observations, use the latest six: three versus three. Medians for four observations average the middle two. The minimum remains six YoY observations (ten quarterly revenue amounts); eight need twelve amounts.

**Accelerating** ≥+3 pp; **Decelerating** ≤−3 pp; **Steady** strictly between. The existing Stable saved-filter alias means Steady. One extreme quarter cannot by itself move the median of a three/four-quarter group. This is typical growth pace, not a numerical investment score or proof of sustainability. A company can accelerate while shrinking or decelerate while growing strongly.

The backend screening projection recomputes all YoY values from public quarterly revenues, requiring unique fiscal periods, matching currencies, year-ago dates 350–380 days apart and consecutive reporting dates 60–120 days apart. The latest report must be at most 140 days old. Invalid/missing latest data hides the metric; no zero or historical substitution is allowed. Comparison periods, unrounded values, source identifiers, latest-quarter movement and all validated historical observations are preserved. All consumers use this projection. The mirrored standalone Python/TypeScript compatibility helpers are parity-tested across fixtures and the complete stock universe.

Click momentum, revenue or consistency to open the existing shared Revenue Growth YoY chart. Select the latest eight quarters or all available observations; inspect a quarter by touch or keyboard. Negative growth plots below zero. No redundant chart is added.

The existing collection/cache and issuer revenue repairs are reused; no extra network request is needed. Daily fundamentals refresh rebuilds classifications. `scripts/validate_revenue_growth_momentum.py` verifies compatibility-helper parity, while backend and frontend tests check displayed/filter projection parity.
