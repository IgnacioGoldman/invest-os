# Revenue Growth Consistency

A categorical pattern signal, independent of growth strength, direction, valuation and momentum. It is **Steady** or **Choppy**, with no numerical ranking. Insufficient, stale or invalid history hides the card and fails categorical filters.

Use the same latest consecutive, comparable YoY observations as momentum: prefer eight; require six. Eight YoY observations require twelve quarterly revenue amounts; six require ten. Never bridge missing quarters or replace missing latest inputs with an older window. Each rate is recomputed from matching fiscal quarters, positive prior-year revenue, nonnegative current revenue, matching currencies and period ends 350–380 days apart. Adjacent observations must be 60–120 days apart. Sources, reporting dates, periods and the 140-day freshness deadline remain in the shared screening projection.

Let `g` be the six or eight growth percentages in chronological order. Set `tolerance = max(3 pp, 0.25 × median(abs(g)))`. Calculate `max(abs(g[i] - 2*g[i-1] + g[i-2]))`, the largest change in quarterly growth pace. If this is at most the tolerance, classify **Steady**. This allows a straight accelerating or declining trend rather than requiring identical percentages.

Also classify **Steady** for a sustained level shift: some split has at least three observations on each side, and every observation on each side is within the same tolerance of that side's median. Otherwise classify **Choppy**. A single endpoint spike fails this persistence test. A step from 1%, 1%, 1% to 80%, 80%, 80% establishes a new level and passes.

These explicit initial screening heuristics describe the observed pattern; they do not establish sustainability, investment quality or causation. The 3 pp noise floor follows momentum's existing materiality band; the relative allowance avoids treating small fluctuations at high growth levels as inherently choppy. Boundaries use unrounded values with 1e-10 pp numerical tolerance. Raw values and diagnostics remain inspectable and available to AI research. Consistency is not sortable because its categories have no numerical order.

Examples: 12,14,16,18,20,22 → Steady; 30,26,22,18,14,10 → Steady; 2,2,3,2,2,3 → Steady; 1,1,1,1,1,100 → Choppy; 15,-5,30,2,40,-10 → Choppy.

Supporting source-linked observations are stored once under the revenue metric and shared by the three growth signals, rather than copying the same history into every metric payload.
