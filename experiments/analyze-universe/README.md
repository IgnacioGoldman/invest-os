# Full-universe Analyze experiment

**Completed locally in the Codex conversation: all 200 stocks, prices dated 23 October 2026.**

- [Complete five-column ranking](runs/2026-10-25/ranking.md)
- [Colored, searchable table](runs/2026-10-25/ranking.html)
- [CSV](runs/2026-10-25/ranking.csv)
- [Validation and execution record](runs/2026-10-25/result-metadata.json)

The purpose is to assess all companies before applying deterministic eligibility, then compare retained symbols with the AI ranking. This diagnoses selection agreement with an independent qualitative review; it does not establish future returns or prove that rejected companies are investments worth buying.

## Exact workflow reused

The existing Analyze action in `MobileStockExplorer.prepareSelectedStocks` passes list snapshots to `frontend/src/aiAnalysis.ts::prepareStockAnalysis`, which invokes `aiBriefData.ts::compactAnalysisStock` and the Markdown prompt at `frontend/src/prompts/stock-analysis.md`. It generates a prompt for an AI; it has no fixed execution model or numerical investment score.

`prepare.cjs` executes those exact TypeScript functions. The current run archives their source, hashes, full prompt, full list-snapshot dataset and 200-company universe. Both `new Date()` and `Date.now()` are frozen to the preparation timestamp for consistent freshness checks. No screening condition removes a company.

The financial metrics, histories, reported/computed/proxy tiers, source indices, fiscal periods, currencies, warnings, coverage, million-unit scaling and seven-significant-digit formatting are unchanged. Technical context retains available 1M/3M/6M/1Y/2Y/5Y support zones/distances, one-year return, distance from the 52-week high and dated price/earnings context. There are no new indicators, thresholds or numerical investment scores.

Static Analyze uses **one fundamentals quarter, 12 revenue quarters and two annual rows** from the list snapshot. Although its formatter can include eight fundamentals quarters when supplied, the existing static Analyze handler does not fetch full detail histories. This experiment preserves that distinction. Missing and inconsistent data remain explicit.

## Conversation execution

At the user's direction, the final analysis was authored **here in the conversation**, without a Gemini or other model API. The existing instructions were followed through individual company review, independent business-quality/valuation tags and then global comparison. `read_local.py` is a read-only worksheet over the exact archived compact JSON; it does not recalculate financial metrics or determine tags/ranks. Individual conclusions are in `local-assessments.tsv`; the separately authored qualitative global ordering is in `local-rank-order.txt`. `render_local.py` only validates and exports those judgments.

Business quality and valuation have equal importance. Assessments use Strong / Solid / Average / Weak / Poor / Unknown and Cheap / Fair / Expensive / Unknown. The order reflects the evidence, trade-offs and uncertainty behind those categories; there is no numerical mapping from tags to scores. Unknown is not an automatic last-place category. Individual tags were not changed to force an ordering.

The universe was read in sections rather than in a single full-context inference. This is not a bit-for-bit replay of an unspecified ChatGPT session, and qualitative model judgments need not reproduce on another run. The original full prompt and all source data are available for review.

Targeted primary-source checks cover six companies: ADBE, INTU, APH, BSX, ANIP and FIX. [Research notes](runs/2026-10-25/research-notes.json) distinguish confirmations and new findings from the untouched supplied dataset, including debt/capex differences. Other company facts derive from the saved snapshots; business-model interpretations and risks are analytical judgments. Quotes and normalized earnings have not all been independently verified. Each final table row links to its original compact evidence, including full source identifiers and dates. This is provisional research, not comprehensive due diligence on 200 companies.

## Isolation and later filter comparison

All writes stay inside `experiments/analyze-universe`. Application code, public dataset, saved filters, portfolio simulation, positions, orders and deployment are unchanged. No credentials appear in the artifacts.

`deterministic-control.json` freezes the existing **Auto fixed entry strategy** separately through `screen_stock`, its existing filter evaluator and full detail snapshots, as used by the simulation. It records eligible symbols, the shortlist assuming no holdings/pending orders, rejection reasons and source hashes. The base revenue / operating-margin / zero-red-flag expression before Auto's forward-P/E gate is recorded separately. Membership was not used to assign AI ranks.

This is Auto's fixed policy, not a substitute for the user's private saved filters. A follow-up for a particular saved filter should use its actual expression with the frozen dataset/date. It can join retained symbols to `ranking.json`, report their ranks, top-10/20/50 coverage and high-ranked exclusions, and distinguish missing evidence from observed threshold failures. The current five-column ranking intentionally contains no membership overlay.

## Reproduction and checks

Prepare a new isolated dataset, then analyze it here in a conversation:

```sh
.venv/bin/python experiments/analyze-universe/run.py prepare --run-dir experiments/analyze-universe/runs/NEW-RUN
```

Preparation refuses to overwrite an existing frozen run. This command invokes no model API. To verify and regenerate the completed exports without any AI inference or network requests:

```sh
.venv/bin/python experiments/analyze-universe/run.py verify --run-dir experiments/analyze-universe/runs/2026-10-25
.venv/bin/python experiments/analyze-universe/render_local.py --run-dir experiments/analyze-universe/runs/2026-10-25
.venv/bin/python -m unittest discover -s experiments/analyze-universe -p 'test_*.py'
npm --prefix frontend run test:metrics
```

Validation requires all 200 symbols exactly once, consecutive ranks, allowed descriptive tags and exactly the requested five columns. The HTML export is searchable, the CSV is spreadsheet-ready, and JSON preserves explicit symbols for later joins. No script computes the investment ordering from financial thresholds.

The HTML additionally includes **Proximity to support**, calculated with the archived frontend's `supportMetric` at the original preparation time. It shows an enclosing support zone first, or otherwise the nearest valid midpoint across all six existing timeframes, with the original At Support / Near Support / Above Support labels and signed distance. Expand a cell for all valid timeframes and price zones. Missing valid zones are Unknown. `support-context.json` records this display context; the investment ordering and original five-column Markdown/CSV/JSON assessments are preserved.

The HTML opens as a **filter playground over all 200 stocks**, with the current app's **Pullback** (1M/3M/6M) and **Support** (1Y/2Y/5Y) defaults. Both require Strong/Solid revenue growth, profitable operations and zero red flags in a complete assessment. With the captured financial refresh they select **17** and **9** stocks respectively. Cards compare matching counts, original top-20/top-50 coverage and average original rank. Create or customize named filters using AND/OR conditions, support timeframes, numeric thresholds, red/green counts and original review tags; edit/delete saved filters, search/sort results and export the visible cohort to CSV. Custom filters are stored in this browser for this page, with a session-only fallback when storage is unavailable. The HTML embeds its UI/data and works directly over `file://`. `filter_playground.cjs` reads the current app's preset definitions and metric functions at the saved evaluation date; it does not fetch new data. Unknown or incomplete numeric inputs do not pass. The existing **64 supported / 34 financial passes / 30 non-passes** remain available in [the full support audit](runs/2026-10-25/filter-research/support-audit.md) and can be reproduced in the custom builder. Regenerating the HTML also regenerates this audit from the captured inputs.

The 26 October debugging follow-up adds operating-margin rejection metadata to the backend validator and uses it to explain the frozen run's **29 Unknown margins (11 at/near support)**. The HTML and [margin diagnostics](runs/2026-10-25/filter-research/operating-margin-diagnostics.md) distinguish missing inputs, financial-sector exclusions, proxy estimates, stale/future reports, conflicting revenue and extreme margins. Causes can overlap. Explanations use the frozen facts and evaluation date; eligibility still uses the archived metrics. The 64/33/31 counts, qualitative ranks and frozen inputs are unchanged. This follow-up does not backfill missing reports or repair the underlying source conflicts, including AXFO.ST's malformed year 4602.

The subsequent local collector repair recovered **14 margins**, leaving **15 Unknown** (14 financial-sector exclusions and MSTR's extreme margin). At the user's request, the existing `runs/2026-10-25/ranking.html` now displays those repaired financial checks, captured as of 26 October in `financial-refresh.json.gz` with a hash manifest. Original qualitative ranks, tags, rationales, archived Analyze evidence and technical support context remain the 25 October experiment. Each HTML row links the original analysis evidence separately from the refreshed financial data. The [repair report](runs/2026-10-26-data-repair/operating-margin-audit.md) records the before/after comparison; support/financial audits alongside the HTML now use the captured refreshed metrics. The supported pass/fail counts remain 64/33/31.

To capture a subsequent local repair and regenerate this display without reranking:

```sh
.venv/bin/python experiments/analyze-universe/audit_support.py \
  --run-dir experiments/analyze-universe/runs/2026-10-25 \
  --refresh-data-dir frontend/public/data --as-of 2026-10-26
.venv/bin/python experiments/analyze-universe/render_local.py \
  --run-dir experiments/analyze-universe/runs/2026-10-25
```

Ordinary regeneration uses the captured financial refresh when present, and the original frozen screening metrics otherwise. It never downloads new data or changes the original input hashes.

The HTML now places separate **Red flags** and **Green flags** columns immediately after Stock for every row. Each shows the assessed count, the names of detected concerns or positive patterns, and expandable conditions and explanations. Green flags use the three experiment-local rules: sustained revenue growth, profitable growth and cash-backed earnings; the two growth rules overlap. Partial assessments show the observed count with coverage, such as **0 detected · 3/4 assessed** for BMY, and list assessed red concern groups. The separate **flags_not_assessed** column names missing red/green checks and their reasons, including missing branches inside an otherwise flagged group. A wholly unavailable assessment remains Not assessed. Partial counts are display evidence, not complete numeric screening values. The support CSV also includes observed red flags, coverage and flags_not_assessed. The 26 October financial capture includes the green assessments computed from full saved histories. Support context and original qualitative ranks are preserved; financial membership follows the captured repaired assessments. Reproducing without that capture leaves unsupported green assessments explicitly unavailable.

## Archived API preflight

Before the user selected conversation execution, the full prompt was counted at 1,425,966 Gemini tokens against a 1,048,576 input limit. Attempted 50-stock generations and a one-stock diagnostic were rejected with HTTP 429. There was no successful Gemini generation and no API-reported generation usage; actual invoice costs are unavailable. The abandoned prompts and responses remain under `failed-api-history` for provenance. Provider execution code was removed from the active runner. These failures do not block the completed conversation-authored ranking.


## Experiment-only green flags

Green-flag calculations, regression tests and rule documentation live in this experiment: `green_flags.py`, `flag_facts.py`, `test_green_flags.py` and [the rule documentation](docs/green-flag-count.md). They share strict quarterly input validation with the app’s red flags, and never register a main-app metric or change app UI, filters, exported snapshots or refresh workflows. Capturing a financial refresh computes green flags directly from full saved histories; rendering uses that captured result. The main app retains its original red-flag metric and screening schema.


## Universe flag refresh

The public-data refresh assessed all 200 symbols and repaired missing inputs for 37. Complete red concern-group assessments rose from **149 to 160**; green assessments rose from **152 to 162**. Red has 21 partial assessments and one without any determined concern group (YPF); green has 20 partial assessments. Another **18 symbols are Not applicable** because these rules exclude financial businesses, REITs and investment funds. Specific missing periods and inputs appear in `flags_not_assessed` and [the universe coverage report](runs/2026-10-25/filter-research/flag-coverage.md), with all-symbol CSV/JSON alongside it. Complete group coverage can coexist with an unassessed branch when another branch has already established that concern.

`refresh_flag_universe.py` uses explicit local paths and public financial sources, without loading application settings, .env files or AI credentials. It preserves saved prices, backs up SQLite before writes, refreshes eligible incomplete symbols sequentially, then assesses the entire universe and republishes the static financial assets. Run it before recapturing and rendering the ranking:

```sh
.venv/bin/python experiments/analyze-universe/refresh_flag_universe.py \
  --collect --output-dir /tmp/invest-os-flag-refresh --as-of 2026-10-26
```

The displayed capture remains evaluated on 26 October, alongside the original 25 October qualitative ranking. Later live evaluations still enforce financial and market-data freshness. No missing input is replaced with an assumed zero, and incomplete counts remain unavailable to numeric filters.
