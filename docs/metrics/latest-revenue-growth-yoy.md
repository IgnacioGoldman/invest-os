# Revenue Growth YoY

`(latest fiscal-quarter revenue / revenue in the same fiscal quarter last year − 1) × 100`.

Signed direction aliases are deterministic: **Growing** >0%; **Flat** =0%; **Declining** <0%. GOOG Q2 2026 is +24.23% · Growing. The restored strength badge uses the original 20/8/0 bands: **Strong** ≥20%; **Solid** ≥8% and <20%; **Flat** ≥0% and <8%; **Weak** <0%. These are descriptions of reported growth, not investment ratings. `strength` is separate from the existing signed `status`, so saved Growing (>0%), Flat (=0%) and Declining (<0%) rules keep their exact semantics. New Strong, Solid, Flat growth and Weak conditions use the strength bands. The filter editor calls the 0–<8% strength condition “Flat growth” to distinguish it from the existing exact-zero “Flat” rule. High Growth and Moderate Growth legacy aliases map to Strong and Solid. A 1e-10 pp tolerance handles floating-point representation at 8% and 20% boundaries.

Click the card to inspect the restored quarterly bar chart: latest eight observations or all available history, chronological, with negative bars and accessible per-quarter values. Momentum and consistency open this same chart component. Only validated, recomputed source-linked observations appear.

Require finite public quarterly amounts, positive prior-year revenue, nonnegative current revenue, known matching currency, a unique fiscal quarter, and actual period ends 350–380 days apart. Check a stored growth rate against the recomputed result; a mismatch hides the card. Use the latest available report, never search backwards for an older usable observation. Quarter-end age must be 0–140 calendar days, reusing the existing revenue-screen freshness rule. A fresh stock quote does not refresh the financial fact.

When validation fails, omit the card and its detail panel; never insert zero or a placeholder. Preserve both sources, fiscal periods, as-of date, formula and freshness deadline. Validate provenance structure and calculations, without claiming independent verification of publisher figures. Acquisitions, revenue-definition changes and currency effects remain research limitations.
