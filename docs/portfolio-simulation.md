# Forward paper portfolio simulation

InvestOS and accumulating VWCE begin with €10,000 on the feature's actual activation date, **2026-10-24**, in EUR. There are no transactions before activation, backtested stock selections or invented returns. Initially both portfolios are cash. The first valid execution session after activation purchases the benchmark; the strategy waits for qualified, evidenced investment decisions.

## Architecture and persisted records

- `backend/app/services/simulation/accounting.py`: the common ledger, cash, average cost, split/dividend handling, executions, positions and performance engine for both portfolios.
- `strategy.py` and `screening.py`: fixed entry/hold/exit rules, using the existing screening projection and saved-filter evaluator. No new numerical investment score.
- `analysis.py` and `backend/app/prompts/portfolio-review.md`: one source-bound structured AI review for candidates plus holdings. No executable trades in the response.
- `market.py`: the existing yfinance and Frankfurter integrations extended to retain dated FX and corporate actions. No paid market-data dependency.
- `engine.py`: versioned state, session idempotency, AI-attempt journal, immutable history and the public projection.
- `scripts/run_portfolio_simulation.py`: explicit initialize / market / prepare / claim / analyze / finalize / verify / publish phases.
- `data/simulation/state.json`: authoritative, version-controlled metadata, sessions, screening results, source evidence, assessments, orders, transactions, historical market observations, daily snapshots and actual reported AI token usage.
- `frontend/public/data/simulation/index.json`: one atomic public projection containing only hypothetical portfolios and public financial analysis. It contains no private money entries, API key, raw model request registry or account data.
- `frontend/src/components/PortfolioSimulation.tsx`: comparison and drill-down in the Auto tab. Personal source balances and invested/uninvested amounts stay in the separate Portfolio tab. Guests can access Explore and Auto; Watchlist and Portfolio require sign-in.

Every transaction has a stable identifier, portfolio/position/decision identifiers, original-currency price and gross value, EUR FX rate/date/source, execution time, fees, cash movement and rationale. SELL records include realized EUR P/L. Replacements link the BUY to its preceding SELL order and preserve the former position. A hash chain detects inconsistent ledger edits. Positions and account values are reproducible from transactions; closed positions are never overwritten by current holdings.

Screening history distinguishes rejected, eligible, shortlisted, AI-rejected, unselected, purchased, held and sold companies. Each selected company's original financial inputs, timestamps and source identifiers remain in that session's frozen request. The user interface shows concise explanations and expandable evidence rather than raw API payloads. Historical sessions are append-only; later holdings do not rewrite prior equity.

## Exact V1 rules

New candidates require all of: revenue strength **Strong** (≥20% YoY) or **Solid** (≥8%, <20%); validated operating margin >0%; validated forward P/E **Cheap** or **Fair**; and a complete, current red-flag count =0. All four concern groups, including Priced for Perfection, must be assessed. Unsupported industries, missing facts, incomplete coverage and stale data never qualify automatically.

Forward P/E reuses the original InvestOS research boundaries: positive multiple ≤18 is Cheap; >18 through 25 is Fair; ≥35 is Expensive (the former Pricey/Very pricey bands). The original 25–35 unclear interval remains Unknown, preserving the old boundaries. The existing strict source, forecast-horizon, currency and seven-day estimate/quote checks still apply. This research classification is used for this simulation's fixed gate; retired first-filter valuation cards are not restored.

If more than 20 new companies qualify, sort Cheap before Fair, Strong before Solid, operating margin descending, then ticker ascending. Always review current holdings separately. Already-owned and pending-purchase symbols are not new candidates.

**BUY:** pass the complete entry screen; AI investment assessment compelling; at least two valid company evidence references, including business performance and the sourced forward valuation; a substantive explanation; not already held; fewer than four positions including reserved purchases; and available cash. Follow the AI's validated ordering of shortlisted candidates. Each new position's total outlay including the 0.10% purchase fee is limited to 25% of equity and available cash. Fractional quantities are floored to twelve decimal places. Missing current inputs fail the gate. Unused capital stays cash without interest.

**HOLD:** default for existing positions. An intact thesis, insufficient evidence, unknown assessment, missing inputs, valuation becoming expensive by itself or an unsupported replacement all retain the position. Appreciation and profit percentages never trigger a sale. No forced rebalancing, stops, leverage, shorting, options or contributions.

**SELL for broken thesis:** AI thesis broken, adequate source-bound evidence, and at least one current validated deterioration fact: Weak revenue growth (<0%) or negative operating margin. Evidence must reference that deteriorating metric. Missing data is not deterioration. Proceeds remain cash until a separate purchase is justified.

**REPLACE:** an existing position has reliable required inputs and at least one deteriorated entry characteristic (Expensive forward P/E, detected flags, growth outside Strong/Solid, or non-positive operating margin); its AI thesis is deteriorating/broken; an unowned candidate meets every BUY condition; and the AI comparison explicitly says materially better with a substantive explanation and valid evidence from both companies. The sale and dependent purchase are linked. The BUY respects the allocation/cash limits. It cannot use proceeds before the sale actually executes.

These are screening and simulated portfolio policies, not universal valuation standards or a forecast that the strategy will outperform.

## Execution, FX and accounting

Decisions made after market close T create pending orders. No order executes at T's already observed close. Execution uses the next available eligible session's verified closing price, strictly after the recorded decision timestamp and market cutoff. Missing/invalid prices or FX keep an order pending. The benchmark uses the same 0.10% fee and execution delay convention.

Orders execute in chronological exchange-close order, with sales before purchases only at the same timestamp. A European replacement BUY cannot spend the proceeds of a later-closing US SELL; it waits for a later valid close. Allocation equity uses only prices available at that execution time, carrying earlier valid closes when another exchange has not closed. Reported splits adjust carried prices and quantities consistently. No later US close sizes an earlier European purchase.

The benchmark is **VWCE.DE, Xetra EUR, ISIN IE00BK5BQT80**, accumulating Vanguard FTSE All-World UCITS ETF. The [issuer's listing information](https://www.vanguard.co.uk/professional/product/etf/equity/9679/ftse-all-world-ucits-etf-usd-accumulating) identifies this EUR listing and ISIN. Before its purchase, the provider must match the symbol, ETF type, name, currency and exchange; a conflicting ISIN is rejected. It buys and holds with no AI or contributions. Its fund structure handles accumulation internally.

Historical FX uses the existing [Frankfurter time-series API](https://frankfurter.dev/v1/), with the historical reference rate on or before each execution/valuation date, at most seven days old. The rate is EUR per unit of the quote currency; GBp uses the corresponding pence adjustment. EUR is identity. Execution FX is a dated public reference-rate assumption, not an actual broker fill. Today's rate never reconstructs an older snapshot. A carried nontrading-day security price is converted with the valuation date's latest available historical FX, preserving both dates separately.

[yfinance history](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html) is fetched with `auto_adjust=False`, explicit actions and no price repair/interpolation. The adapter reverses later reported split adjustments within the fetched recovery window to obtain as-traded price units; the ledger adjusts quantities on each split date with unchanged EUR basis. Already recorded observations and transactions are not overwritten on a later download. Cash dividends are credited to owners from before the ex-date, using split-adjusted entitlement and that day's dated FX. Crediting on the ex-date rather than payment date is an explicit V1 simplification. Adjusted-close returns are not added to these dividends.

Both portfolios track cash, invested value, realized/unrealized P/L, fees, recorded dividends, equity, return since inception and maximum observed daily drawdown. Annualized return appears only after at least 365 days. The first paired snapshot is exactly €10,000 each. Nontrading days do not invent candles; a previous valid close can value a holding with its original date and an explicit stale-price indication. Missing corporate actions, delistings, spin-offs or other unsupported actions can limit total-return accuracy; capital-gain distributions requiring unsupported reconciliation stop accounting safely. The display explicitly says recorded-action returns may be incomplete. Taxes and additional real-world execution costs are excluded.

## AI API and expenses

The implementation uses Google Gemini via the native [`generateContent` REST API](https://ai.google.dev/api/generate-content), with the model read from `GEMINI_MODEL` (default `gemini-3-flash-preview`). Requests explicitly set `generationConfig.thinkingConfig.thinkingLevel` to `"high"`, following [Google's thinking configuration](https://ai.google.dev/gemini-api/docs/thinking), and send the Pydantic JSON schema through [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output). The existing pinned `requests` dependency handles HTTP; no provider SDK is needed. The system prompt is Markdown, separate from the existing manual-copy AI brief. Analysis version 2 identifies the Gemini integration; saved historical reviews and paid-attempt records are retained. Each prepared request freezes its configured model, and the usage/decision journals retain the model version reported by Gemini when available.

Pydantic schemas forbid extra fields and restrict investment/thesis enums. Semantic validation requires one assessment per supplied symbol, a complete candidate permutation, known source IDs belonging to the correct company, and valid comparative evidence. Unknown remains a valid conclusion. No external research tool is enabled in V1; source links do not imply their contents were read. Structured outputs constrain format; deterministic gates still check evidence and data availability. They cannot establish that a model's analytical judgment is correct.

There is at most one automatic paid request per logical session. Before contacting Gemini, the workflow commits a claimed attempt and its run/attempt owner to Git. HTTP retries and redirects are disabled. A saved success is reused; failed or indeterminate attempts are not automatically reissued. If a process loses the response after reservation, that session has an indeterminate analysis/cost and no new strategy orders. It is safer to miss one review than charge repeatedly. A prepared request more than 24 hours old expires. A later eligible session can receive a new review.

Actual API-reported token usage is preserved, including received usage for blocked, truncated, malformed or semantically invalid responses. Raw Gemini usage metadata is retained alongside normalized input/output counts; output includes both candidate and thinking tokens. The UI separates estimated USD API operating expenses from modeled trading fees. For `gemini-3-flash-preview`, estimates use the [documented Standard text rates](https://ai.google.dev/gemini-api/docs/pricing#gemini-3-flash-preview): $0.50 per million uncached input tokens, $0.05 cached input and $3.00 output including thinking, as of 2026-10-25. Other configured models or unknown usage have unknown cost. These estimates are not an invoice. AI expenses are not deducted from investment returns, and net economic return remains unavailable without complete expense information. No net-of-AI-cost outperformance is claimed.

## Automation, configuration and deployment

`.github/workflows/portfolio-simulation.yml` runs Monday–Friday at **23:35 Europe/Stockholm**, using [GitHub's timezone-aware schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). It shares the existing Pages concurrency lock with stock refreshes. GitHub schedules can be delayed; actual decision timestamps and the execution delay still apply.

The workflow tests the engine, checks actual available sessions and skips unnecessary universe refreshes when there is no new session, refreshes stock prices/valuation inputs with the existing saved financial data, fetches the required session prices/actions and historical FX, completes earlier pending orders, accounts both portfolios, screens the full universe, prepares one consolidated review, commits the paid-attempt checkpoint, calls Gemini, validates the response, applies the fixed rules, reconciles the ledger, commits generated data and builds/deploys GitHub Pages. Fundamentals come from the existing daily fundamentals workflow; this feature does not duplicate SEC collection. Actual verified candle dates determine whether a market session needs processing. Known US and European timezones use normal closing times as conservative early-close bounds; same-day incomplete candles are excluded. Unsupported exchange timezones are unavailable rather than guessed.

Local runs automatically load **`GEMINI_API_KEY`** and **`GEMINI_MODEL`** from the root `.env`, without overriding process environment variables. The existing local Gemini configuration is sufficient; no credential needs to be copied into frontend files. An empty or omitted model defaults to `gemini-3-flash-preview`.

For GitHub Actions, set **`GEMINI_API_KEY`** as a repository Actions secret and optionally set **`GEMINI_MODEL`** as a repository Actions variable. The workflow defaults to `gemini-3-flash-preview`. The key exists only in the analysis step, never in Vite environment variables or generated data; other steps receive only `GEMINI_API_KEY_CONFIGURED`. A local `.env` does not configure repository secrets. The existing Supabase secrets continue to support personal data; no new database/server or migration is required. Without the Gemini key, the benchmark/accounting can run and the strategy records no unsupported trades.

Once the key is set, normal scheduled sessions need no manual intervention. Manual recovery/testing uses:

```sh
gh workflow run portfolio-simulation.yml --ref main
gh run list --workflow portfolio-simulation.yml
```

A manual run on a weekend can verify setup without inventing a trading session. Inspect the workflow summary, artifact and `data/simulation/state.json` for failure stage, latest successful update, request state and order status. An interrupted paid request is deliberately not auto-retried for the same session. API failure preserves holdings and permits valid market accounting to continue. A failed publication leaves the prior deployed artifact and its old update date visible.

Each phase writes state atomically; the public dashboard is one JSON projection. Pages publishes the complete built artifact atomically. The normal full stock export also regenerates simulation data from the durable state after rebuilding its output directory, so a daily fundamentals export cannot erase the simulation.

Local offline verification:

```sh
.venv/bin/python -m unittest discover -s scripts
.venv/bin/python scripts/run_portfolio_simulation.py --phase verify
npm --prefix frontend run test:simulation
npm --prefix frontend run test:metrics
npm --prefix frontend run test:routing
npm --prefix frontend run build
```

The state is explicitly initialized once; missing state in another phase is an error rather than a silent reset. Tests use synthetic prices/FX and mocked AI exclusively inside fixtures. They never populate published performance history.

## Provider limitations observed in the current stock model

Bare Yahoo `forwardEps`/`forwardPE` frequently lacks a verifiable forecast horizon or estimate revision date. The existing collector correctly makes these estimates unavailable. Such companies cannot pass this V1 entry screen; the simulation does not weaken the check or invent a forecast. The Priced for Perfection rule also requires four comparable cash-flow/revenue quarters in the listing currency; where a reliable quarterly FX bridge is absent, coverage remains incomplete. Conservative entry coverage can therefore leave the strategy in cash even when other displayed business metrics are positive. This is valid behavior under the requested rules.

Free market-data/FX services can be unavailable or revise history. Recorded history is retained, stale dates are displayed, and unsupported required data cannot produce simulated trades. Complete corporate-action/total-return coverage and actual API invoices are not guaranteed by these providers. These limitations and any missing external API credential are explicit; no unsupported capability or historical return is presented as operational.
