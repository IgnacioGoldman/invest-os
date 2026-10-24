# InvestOS — Automated Investment Strategy & Portfolio Simulation

## OBJECTIVE

Implement a complete, end-to-end automated investment
simulation feature within the existing InvestOS application.

The objective is to evaluate whether an investment strategy
combining deterministic financial screening, financial risk
detection, and AI-assisted investment analysis can outperform
a passive investment in VWCE over time.

The system must:

1. Automatically identify promising companies.
2. Analyze those companies using AI.
3. Simulate investments in selected stocks.
4. Monitor existing investments.
5. Hold investments while their investment thesis remains valid.
6. Sell or replace investments when justified.
7. Maintain an accurate historical record of every transaction.
8. Compare InvestOS performance against VWCE.
9. Run automatically using GitHub Actions.
10. Display all results within the existing InvestOS application.

This is a SIMULATION.

Do not implement real brokerage transactions.

The system must operate autonomously once deployed and
provided with the necessary external API credentials.

---

# 1. IMPORTANT IMPLEMENTATION PRINCIPLES

Before implementing anything:

Inspect the existing InvestOS codebase.

Understand:

- Existing application architecture.
- Existing Portfolio tab.
- Existing Explore functionality.
- Existing financial metrics.
- Existing financial data provider.
- Existing stock filtering logic.
- Existing red-flag / anti-pattern detection.
- Existing Forward P/E valuation classification.
- Existing stock detail presentation.
- Existing GitHub Pages deployment.
- Existing GitHub Actions workflows.
- Existing styling and component conventions.

Reuse these components wherever possible.

DO NOT:

- Rebuild the application.
- Introduce a separate application.
- Introduce a new scoring framework.
- Duplicate financial calculations.
- Replace existing filtering mechanisms.
- Modify unrelated functionality.
- Introduce unnecessary infrastructure.
- Create a backend server.
- Introduce real-money trading.
- Redesign the entire Portfolio tab.
- Invent financial information.
- Generate fictional investment performance.
- Leave implementation decisions unresolved.

This specification defines the V1 behavior.

Implement the specified behavior directly.

Do not respond with a list of architectural alternatives
or ask the user to select an implementation approach.

When implementation details depend on the existing codebase,
follow its established conventions.

The final deliverable must be working functionality,
not merely an implementation proposal.

---

# 2. INVESTMENT STRATEGY

## Core Philosophy

The objective is NOT to generate frequent trades.

The objective is to identify strong businesses at reasonable
valuations and remain invested while the original investment
thesis remains valid.

InvestOS should:

BUY:
When a company has attractive business fundamentals,
reasonable valuation, acceptable risks, and a compelling
AI-supported investment case.

HOLD:
While the company remains a strong investment and the
original investment thesis remains valid.

SELL:
When the investment thesis materially deteriorates,
or when a clearly superior investment opportunity
justifies reallocating capital.

The system must NOT:

- Sell automatically after gaining 5%.
- Sell automatically after gaining 10%.
- Sell automatically after gaining 20%.
- Take profits simply because a stock appreciated.
- Rotate stocks merely to create activity.
- Assume that expensive stocks must immediately be sold.
- Assume that every day requires a transaction.

Doing nothing is a valid investment decision.

The strategy should prioritize long-term compounding
over frequent trading.

---

# 3. INITIAL SIMULATION PARAMETERS

Use these fixed V1 assumptions.

Starting capital:
€10,000

Simulation currency:
EUR

Maximum simultaneous stock positions:
4

Maximum initial allocation to an individual position:
25% of total portfolio equity.

The strategy may hold fewer than four stocks.

Uninvested funds remain as cash.

Cash does not earn interest in V1.

Do not use:
- Leverage.
- Margin.
- Short selling.
- Options.
- Automatic additional contributions.

Fractional simulated shares are permitted, with quantities
stored at sufficient precision for reliable accounting.

Do not force daily or monthly portfolio rebalancing.

The portfolio must maintain accurate cash and position
balances after every transaction.

Use a fixed simulated transaction cost of 0.10% per
purchase or sale for both the strategy and the benchmark.

This is a V1 modeling assumption covering basic
transaction friction, not a claim about actual broker fees.

Explicitly disclose that taxes and potentially
additional real-world execution costs are excluded.

---

# 4. DETERMINISTIC COMPANY SCREENING

Reuse the existing InvestOS financial metrics.

The application already uses business metrics such as:

- Revenue Growth YoY.
- Operating Margin.

It also uses valuation information such as:

- Forward P/E.

And an existing system of:

- Financial anti-patterns.
- Red flags.
- Total red-flag count.

Preserve the distinction between these categories.

Business fundamentals describe the operating company.

Valuation measures describe the price investors pay.

Anti-patterns identify particular investment risks.

AI provides deeper contextual analysis.

Do not combine everything into a new composite score.

## Initial Candidate Eligibility

For V1, a new investment candidate must satisfy:

1. Revenue Growth YoY classified as Strong or Solid.

2. Operating Margin greater than zero.

3. Forward P/E valuation classified as Cheap or Fair.

4. Total detected red flags equals zero.

5. All financial inputs necessary for these conditions
   must be available and sufficiently reliable.

Use the existing metric classification definitions.

Do not redefine the boundaries between Strong, Solid,
Cheap, or Fair.

A company with unavailable required metrics must not
automatically qualify.

If a red-flag rule cannot be evaluated because data is
missing, do not interpret that as proof of zero risk.

Use existing data-availability and applicability
conventions to determine eligibility.

## Priced for Perfection

Reuse the previously specified valuation anti-pattern:

Identifier:
priced_for_perfection

Trigger when BOTH conditions hold:

Price-to-Sales > 10

AND

Free Cash Flow Yield < 2%

Where:

Price-to-Sales =
Market Capitalization / TTM Revenue

Free Cash Flow Yield =
TTM Free Cash Flow / Market Capitalization

When triggered, this contributes exactly one additional
red flag to the existing red-flag count.

If this rule is already implemented, reuse it.

If it has not yet been implemented, integrate it using
the existing anti-pattern architecture.

Do not create a separate red-flag system.

Treat it as a warning, not definitive proof that a stock
is overvalued.

---

# 5. DAILY SCREENING PROCESS

Each eligible trading day:

1. Load the latest available financial information.

2. Evaluate existing financial metrics.

3. Evaluate all applicable anti-patterns.

4. Calculate the existing total red-flag count.

5. Apply the candidate eligibility rules.

6. Identify companies that qualify for deeper analysis.

7. Include current simulated holdings for monitoring.

8. Prepare one consolidated AI analysis request.

Only one AI analysis request should be necessary
for the day's investment review.

If more than 20 eligible new candidates exist:

Select up to 20 using this deterministic order:

1. Cheap valuation before Fair.
2. Strong revenue growth before Solid.
3. Higher operating margin first.
4. Alphabetical ticker order as final tie-breaker.

Always include current holdings separately so the AI
can assess whether existing investments should be retained.

Do not use the AI to invent or estimate missing financial
statement values.

---

# 6. AI INVESTMENT ANALYSIS

Use the OpenAI API.

Initial model:

gpt-6.1-sol

Reasoning effort:

High

Use the officially supported API model identifier and
the current OpenAI SDK.

Prefer the Responses API and structured output.

Run the AI analysis server-side in GitHub Actions.

Never expose the API key in browser JavaScript,
GitHub Pages assets, or generated public JSON.

Store the API key in:

OPENAI_API_KEY

as a GitHub Actions secret.

## AI Responsibilities

The AI must examine:

- Business fundamentals.
- Revenue growth.
- Profitability.
- Valuation.
- Financial risks.
- Existing anti-patterns.
- Available financial history.
- Evidence supporting or challenging the investment thesis.
- Existing simulated positions.
- Alternative investment opportunities.

The AI should answer:

1. Is this a strong business?
2. Is the current valuation reasonable?
3. What are the principal risks?
4. Does the company represent a compelling investment?
5. If already owned, is the original investment thesis intact?
6. Is there credible evidence of deterioration?
7. Is another qualifying company materially more attractive?

Use only supplied financial information and properly
identified external evidence, when available.

Do not assume that the AI has live market data.

Do not allow the AI to invent financial results,
analyst estimates, prices, or reporting dates.

## Structured AI Output

Return validated structured data.

For each company include:

- Symbol.
- Business assessment.
- Valuation assessment.
- Investment assessment.
- Thesis status.
- Key supporting evidence.
- Principal risks.
- Relevant source references.
- Explanation.

Investment assessment:

- compelling
- acceptable
- unattractive
- unknown

Thesis status for existing holdings:

- intact
- deteriorating
- broken
- unknown

For replacement opportunities, include:

- Candidate symbol.
- Existing holding being compared.
- Whether the alternative is materially better.
- Supporting comparative evidence.
- Explanation.

Unknown must remain a valid result.

Do not force confident conclusions from insufficient data.

Validate the output against a strict schema.

The AI must not return executable trades.

It returns assessments.

The deterministic portfolio decision engine decides
whether a simulated trade is permitted.

If the AI call fails or the output is invalid:

- Do not place simulated trades.
- Preserve existing positions.
- Continue market-value accounting where possible.
- Record the failed analysis.
- Display the latest successful analysis date.

---

# 7. BUY RULES

A simulated BUY is permitted only when:

1. The company passes the deterministic entry screen.

2. Its AI investment assessment is "compelling".

3. Sufficient reliable evidence supports that assessment.

4. The company is not already held.

5. The portfolio has fewer than four active positions.

6. Sufficient cash is available.

If several candidates qualify:

Use the AI-supported candidate ordering.

Require explanations grounded in the supplied evidence.

Do not use an invented composite investment score.

Allocate up to 25% of current portfolio equity
to a newly opened position.

Never spend more than available cash.

Account for transaction costs before determining the
final simulated share quantity.

If fewer than four compelling opportunities exist,
leave remaining capital as cash.

Do not invest merely to fill the portfolio.

---

# 8. HOLD RULES

HOLD is the default action for an existing position.

Continue holding when:

- The business remains fundamentally sound.
- The investment thesis is intact.
- No material deterioration has been established.
- There is insufficient evidence to justify selling.
- No clearly superior replacement opportunity exists.

An increase in stock price does not independently
justify selling.

A position may remain attractive even after its
Forward P/E classification moves from Cheap to Fair.

A valuation warning should trigger reassessment,
not automatic liquidation.

Do not sell merely because another company has
slightly higher growth or a marginally cheaper valuation.

Do not automatically rebalance existing positions.

---

# 9. SELL AND REALLOCATION RULES

A SELL requires a documented reason.

V1 supports two reasons:

A. Investment thesis deterioration.

B. Reallocation to a materially better opportunity.

## A. Thesis Deterioration

A position can be sold when:

1. AI assessment identifies the thesis as broken.

AND

2. The conclusion is supported by identifiable evidence
   from the supplied financial or business data.

For the deterministic V1 gate, require at least one
of the following confirmed business deterioration signals:

- Revenue growth classification becomes Weak.
- Operating Margin becomes negative.

Do not treat missing data as deterioration.

If the thesis is broken and the evidence confirms
material deterioration, sell the position.

The proceeds remain as cash unless another qualifying
investment is available.

## B. Reallocation to a Better Opportunity

An existing holding becomes eligible for replacement when
at least one relevant investment characteristic deteriorates:

- Forward P/E classification becomes Expensive.
- One or more applicable financial red flags appear.
- Revenue growth is no longer Strong or Solid.
- Business profitability deteriorates.

This alone does not trigger a sale.

A replacement requires ALL of the following:

1. An existing holding is eligible for replacement.

2. The AI assessment indicates deterioration or a
   materially weakened investment case.

3. A new company satisfies all BUY requirements.

4. The AI identifies that candidate as materially
   more attractive than the current holding.

5. The comparison provides specific evidence explaining
   why the replacement is justified.

6. All required information is reliable.

When those conditions hold:

- Sell the existing simulated holding.
- Return proceeds to cash.
- Open the replacement position using available proceeds,
  respecting the maximum allocation rule.
- Record both transactions.
- Link the replacement BUY to its preceding SELL.
- Store the reason for the decision.

If no compelling alternative exists:

Continue holding unless the hard deterioration
conditions in section A are satisfied.

Do not implement:
- Fixed profit targets.
- Trailing stops.
- Automatic monthly rotation.
- Forced selling after a fixed holding period.

All sell decisions must be auditable.

---

# 10. EXECUTION TIMING AND LOOK-AHEAD PREVENTION

This is essential for a credible simulation.

The AI evaluates information available after the
relevant market close.

A decision made using today's closing data cannot be
executed retrospectively at today's closing price.

Use the following sequence:

DAY T:

- Obtain available financial and market data.
- Run deterministic screening.
- Run AI analysis.
- Generate the permitted investment decisions.
- Store pending simulated orders.

NEXT ELIGIBLE TRADING SESSION:

- Execute pending orders using that session's
  verified closing price.

This produces a one-session execution delay.

It avoids benefiting from information unavailable
at the simulated execution time.

Never execute an order using a historical price selected
after observing future performance.

Record separately:

- Decision timestamp.
- Decision market-data cutoff.
- Execution date.
- Execution price.
- Execution currency.
- EUR conversion rate.
- Execution fees.

For replacements:

Process the simulated sale before the replacement purchase.

Do not allow purchases to spend proceeds that have
not yet been recorded.

Ensure deterministic execution order and replayability.

If valid execution prices are unavailable:

Keep the order pending until the next eligible session,
or record a clearly identified failure.

Never invent execution prices.

---

# 11. BENCHMARK PORTFOLIO — VWCE

Create a passive benchmark portfolio.

Benchmark:

VWCE

Use the accumulating Vanguard FTSE All-World UCITS ETF.

Resolve the correct instrument through the existing
data provider, using the fund identity and an
appropriate EUR-denominated listing.

Do not assume that a similarly named ticker from
another exchange is interchangeable.

Initial capital:

€10,000

The VWCE portfolio must:

1. Begin on the same simulation start date.
2. Use the same starting capital.
3. Purchase VWCE at the first eligible execution session.
4. Account for the same simulated transaction-cost rule.
5. Hold the investment.
6. Reinvest distributions through the accumulating
   fund structure.
7. Receive no additional contributions.

The benchmark does not use AI.

The benchmark does not rotate investments.

VWCE represents the passive alternative against which
InvestOS performance is measured.

Do not include historical VWCE performance from before
the InvestOS simulation began in the comparative return.

Both portfolios must start at the same baseline.

---

# 12. PERFORMANCE HISTORY — MAIN COMPARISON

THIS IS A CORE FEATURE.

The user must be able to see the historical performance
of both portfolios.

Inside the existing Portfolio tab, add a section for:

INVESTOS STRATEGY VS VWCE

## Main Visualization

Display one interactive line chart.

Line 1:
VWCE

Line 2:
InvestOS Strategy

Both lines start at the same initial value:

€10,000

X-axis:
Date

Y-axis:
Portfolio value in EUR

The chart must show how both portfolio values
have evolved over time.

Each portfolio value must include:

- Market value of investments.
- Uninvested cash.
- Realized gains and losses.
- Applicable transaction costs.
- Relevant recorded corporate actions.

Use daily historical portfolio valuation snapshots.

Do not reconstruct historical performance using
today's holdings.

This is critical.

The strategy may own different stocks at different times.

Historical returns must reflect the positions that
were actually held on each historical date.

## Example

DAY 1:

VWCE = €10,000
InvestOS = €10,000

DAY 30:

VWCE = €10,350
InvestOS = €10,600

DAY 60:

VWCE = €10,100
InvestOS = €10,900

These are illustration-only examples.

Never use these values as real application data.

## Chart Interaction

When a user selects a date:

Display:

- Selected date.
- VWCE portfolio value.
- InvestOS portfolio value.
- VWCE return since inception.
- InvestOS return since inception.
- Difference in percentage points.

The visual design must work on mobile.

Use the application's existing charting library if present.

Otherwise, use the smallest appropriate dependency.

Follow existing InvestOS colors, typography,
spacing, and interaction conventions.

Clearly distinguish the two lines.

---

# 13. INVESTOS PERFORMANCE DRILL-DOWN

THIS IS ALSO A CORE REQUIREMENT.

The user must be able to open the InvestOS Strategy
from the comparison chart.

For example:

Tap the InvestOS line or its label,
or select the InvestOS Strategy detail action.

Open a detailed view explaining the strategy's
historical performance.

Do not create a separate top-level application tab.

Keep the experience integrated into the existing
Portfolio section.

The detail view must explain:

- What the strategy currently owns.
- What the strategy owned previously.
- When each investment was opened.
- At what price.
- How much was invested.
- How the investment performed.
- When it was sold.
- At what price it was sold.
- Why it was sold.
- Which stock replaced it.
- What the portfolio did afterward.

The goal is complete transparency.

A user must be able to reconstruct the strategy's
investment history.

---

# 14. CURRENT HOLDINGS VIEW

Display the current InvestOS holdings.

For each position:

- Company name.
- Ticker.
- Purchase date.
- Average purchase price.
- Number of shares.
- Total invested capital.
- Current market price.
- Current market value.
- Unrealized gain or loss.
- Unrealized return percentage.
- Current investment thesis status.
- Last AI assessment date.

When relevant, provide access to the latest AI
investment explanation.

Display separately:

- Total portfolio value.
- Invested amount.
- Available cash.
- Realized profit/loss.
- Unrealized profit/loss.
- Total strategy return.

Use data calculated from the transaction ledger.

Do not allow AI-generated numbers to replace
calculated position values.

---

# 15. HISTORICAL HOLDINGS VIEW

The user must be able to inspect positions
that were previously owned and later sold.

For every closed position display:

- Company name.
- Ticker.
- First purchase date.
- Purchase price.
- Total purchase amount.
- Sale date.
- Sale price.
- Total proceeds.
- Total transaction costs.
- Realized gain or loss.
- Realized percentage return.
- Holding duration.
- Reason for selling.
- Replacement investment, if applicable.

If the position was purchased or sold in multiple
transactions, preserve every transaction and calculate
the aggregate results correctly.

Do not lose historical positions when they are sold.

Do not overwrite previous investment records.

---

# 16. TRANSACTION HISTORY

Maintain an immutable, chronological transaction ledger.

Every BUY and SELL must generate a transaction record.

Required fields:

- Unique transaction ID.
- Portfolio ID.
- Symbol.
- Transaction type.
- Decision date and timestamp.
- Execution date and timestamp.
- Execution price.
- Price currency.
- EUR exchange rate.
- Quantity.
- Gross transaction value.
- Fees.
- Net cash impact.
- Position ID.
- Related decision ID.
- Replacement relationship, when relevant.
- Investment rationale reference.

The history must support questions such as:

"What stocks did InvestOS own in March?"

"When did InvestOS buy Adobe?"

"What was the purchase price?"

"How much did the position gain?"

"When was it sold?"

"Why did InvestOS sell it?"

"What replaced it?"

"Did the replacement outperform the previous investment?"

Do not derive this information from the latest AI response.

Use persistent historical transaction records.

---

# 17. INVESTMENT DECISION HISTORY

In addition to transactions, maintain a decision history.

Transactions explain what happened.

Decisions explain why.

Every daily investment review should record:

- Analysis date.
- Financial-data timestamps.
- Candidate companies considered.
- Existing holdings reviewed.
- Relevant financial metrics.
- Relevant detected red flags.
- AI conclusions.
- Permitted portfolio actions.
- Final decision for each relevant position.
- Explanation.
- Model identifier.
- Analysis version.
- Execution status.

Possible actions:

BUY
HOLD
SELL
REPLACE
NO_ACTION

A HOLD or NO_ACTION decision must not create
a transaction.

The history should make it possible to distinguish
between:

- A stock that was never considered.
- A stock that failed deterministic screening.
- A stock that passed screening but failed AI analysis.
- A stock that was considered but not selected.
- A stock that was purchased.
- A stock that was deliberately retained.
- A stock that was sold.

Keep the user-facing presentation simple.

Do not display raw API payloads in the interface.

Use concise, understandable explanations.

---

# 18. HISTORICAL INVESTMENT TIMELINE

Within the InvestOS Strategy detail view,
include a chronological investment timeline.

The timeline should make portfolio changes easy
to understand.

Illustrative example:

January 12
BUY — Adobe

February 4
BUY — Uber

March 15
HOLD — Adobe

April 8
SELL — Adobe
Reason: Investment thesis deteriorated.

April 9
BUY — Company X
Replacement for Adobe.

These are fictional examples.

They must not appear as actual historical transactions.

Use real simulated events from the ledger.

Where appropriate, show BUY and SELL markers on
historical charts.

A user should be able to understand the sequence
without reading every AI analysis.

---

# 19. PERFORMANCE ACCOUNTING

Implement one deterministic portfolio accounting engine.

It must calculate:

- Cash balance.
- Open positions.
- Position quantities.
- Position cost basis.
- Realized gains/losses.
- Unrealized gains/losses.
- Daily portfolio market value.
- Daily portfolio equity.
- Total return.
- Annualized return when meaningful.
- Maximum drawdown.
- Transaction costs.

Use the same accounting conventions for
VWCE and InvestOS.

## Base Currency

All portfolio comparisons must be expressed in EUR.

For stocks priced in USD or other currencies:

Store original-currency transaction values.

Use the appropriate historical FX rate for
execution and valuation.

Do not use today's FX rate to reconstruct
historical portfolio values.

## Corporate Actions

Correctly account for:

- Stock splits.
- Cash dividends, when data is available.
- Other relevant corporate actions supported by
  the existing data provider.

Avoid double-counting dividends when adjusted-price
series are used.

If complete total-return data is unavailable,
clearly label the limitations.

Do not present price-only returns as fully accurate
total returns.

## Data Freshness

Use the latest valid available closing price.

If an instrument did not trade on a date, preserve
the last valid valuation price and identify stale data
where appropriate.

Never invent intermediate market prices.

## AI Operating Expenses

Record the actual token usage reported by the API.

Keep an AI operating-cost history.

Display these costs separately from transaction fees.

Do not silently claim net-of-AI-cost outperformance
when API expenses have not been deducted.

Distinguish clearly between:

- Investment performance after modeled trading costs.
- AI operating expenses.
- Net economic performance if all required expense
  information is available.

---

# 20. SIMULATION START DATE AND HISTORICAL INTEGRITY

The simulation begins when the feature is activated.

The first historical data point must represent
the two portfolios at their common starting capital.

Do not invent trades before activation.

Do not generate a fictional investment history.

Do not use present-day financial information
to pretend that the strategy selected historical
stocks in earlier years.

Historical performance should accumulate through
real scheduled simulation runs.

A retrospective backtest is NOT part of V1.

The user should see the genuine forward-running
paper-trading history.

If the simulation is only three days old,
the chart should show three days of available history,
not several years of fabricated strategy performance.

---

# 21. PERSISTENT DATA MODEL

Implement persistent storage appropriate for
a static GitHub Pages application.

Prefer version-controlled structured data generated
by GitHub Actions.

Reuse existing persistence conventions if suitable.

The design must support at least:

simulation_metadata

- Simulation identifier.
- Start date.
- Initial capital.
- Currency.
- Strategy version.
- Latest successful update.

portfolio_snapshots

- Date.
- Portfolio ID.
- Total equity.
- Cash.
- Invested value.
- Daily return.
- Cumulative return.

positions

- Position ID.
- Portfolio ID.
- Symbol.
- Status.
- Entry date.
- Exit date when closed.
- Quantity.
- Cost basis.
- Realized P/L when closed.

transactions

- Complete transaction ledger.

investment_decisions

- Complete decision history.
- AI assessments.
- Supporting evidence references.
- Decision reasons.

ai_usage

- Request date.
- Model.
- Token usage.
- Available cost information.
- Status.

Preserve historical records.

Never replace the ledger with a snapshot
of the latest holdings.

Daily records must allow historical portfolio
reconstruction.

Use stable identifiers.

Avoid duplicate daily snapshots and transactions.

---

# 22. AUTOMATION — GITHUB ACTIONS

The application already uses GitHub Pages.

Do not introduce a dedicated server.

Implement a scheduled GitHub Actions workflow.

Schedule:

Monday through Friday.

Time:

23:35 Europe/Stockholm.

Use timezone-aware GitHub Actions scheduling.

The purpose is to run after the normal US and
European equity market closes.

The workflow must:

1. Determine whether an eligible market session
   requires processing.

2. Load existing simulation state.

3. Retrieve required financial and market data.

4. Complete pending simulated orders using valid
   execution-session prices.

5. Update existing holdings and portfolio valuation.

6. Run deterministic company screening.

7. Make one consolidated OpenAI API request.

8. Validate the structured AI response.

9. Apply deterministic BUY/HOLD/SELL rules.

10. Record investment decisions.

11. Create pending simulated orders if justified.

12. Update portfolio history.

13. Update VWCE benchmark history.

14. Save generated simulation data.

15. Publish updated data to GitHub Pages.

The workflow must also support manual execution
for testing and recovery.

## Idempotency

Running the workflow twice for the same logical
session must not:

- Duplicate simulated purchases.
- Duplicate simulated sales.
- Double-count transaction costs.
- Duplicate historical snapshots.
- Generate conflicting decisions.
- Issue unnecessary additional AI calls.

Store processing status by market session date.

Use GitHub Actions concurrency controls to prevent
overlapping state mutations.

When a successful AI assessment already exists
for a session, reuse it.

Do not automatically retry paid AI analysis
multiple times for the same session.

## Failures

If financial data is unavailable:

Do not fabricate prices.

If the API key is unavailable:

Do not call the AI.

If the AI fails:

Do not create trades.

If generated data cannot be published:

Do not pretend that the dashboard is current.

Record the last successful update.

Show an appropriate stale-data state.

Ensure that a failed run does not corrupt
the historical portfolio ledger.

---

# 23. GITHUB PAGES INTEGRATION

GitHub Pages remains the frontend hosting environment.

The browser reads generated simulation data.

The browser must not:

- Call the OpenAI API directly.
- Access private API keys.
- Execute simulation trades.
- Recalculate historical transactions using AI.
- Store authoritative portfolio state.

Implement all investment decisions and accounting
in the scheduled workflow.

Generate static data outputs suitable for
the existing frontend.

Use an atomic publishing approach so readers
never observe partially written portfolio state.

Do not place private financial information,
credentials, or sensitive raw analysis inputs
into publicly served GitHub Pages files.

This V1 simulation uses hypothetical starting capital,
not real brokerage-account information.

---

# 24. USER INTERFACE

Integrate into the existing Portfolio tab.

Do not create a new top-level navigation tab.

## Main Portfolio Simulation Section

Display:

INVESTOS VS VWCE

At the top:

VWCE
Current portfolio value
Return since inception

InvestOS Strategy
Current portfolio value
Return since inception

Then:

Interactive two-line historical performance chart.

Both portfolios must use:

- Same start date.
- Same starting capital.
- Same valuation currency.
- Comparable accounting conventions.

Below the chart:

Latest update date.

A simple way to open the InvestOS Strategy details.

## InvestOS Strategy Details

Organize the information into:

1. Performance.
2. Current holdings.
3. Investment history.

Performance:

- Historical value.
- Cumulative return.
- Realized/unrealized results.
- Cash.
- Relevant costs.

Current holdings:

- Positions currently owned.
- Purchase dates.
- Purchase prices.
- Current values.
- Investment returns.

Investment history:

- Previous positions.
- All BUY/SELL transactions.
- Historical allocation changes.
- Investment decision explanations.
- Replacements.

The experience should be mobile-first.

Use the existing design system.

Avoid excessive text and unnecessary panels.

Prioritize clarity.

The user should be able to understand the portfolio's
performance at a glance and then investigate any
specific investment.

---

# 25. VALIDATION SCENARIOS

Implement comprehensive tests.

At minimum test the following cases.

## Case 1 — Initial Investment

Starting capital:

€10,000

A company passes deterministic screening.

AI assessment:

Compelling.

Expected:

- Simulated BUY decision.
- Purchase at a later valid execution price.
- Correct number of shares.
- Correct transaction costs.
- Correct remaining cash.
- New position displayed.
- Transaction recorded.
- Historical portfolio valuation updated.

## Case 2 — No Qualifying Stocks

No companies satisfy the BUY rules.

Expected:

- No purchases.
- Cash remains available.
- VWCE benchmark continues independently.
- No fictional investment returns.
- Decision history records NO_ACTION.

## Case 3 — Holding a Winner

An existing stock increases by 20%.

The investment thesis remains intact.

Expected:

- Continue holding.
- No automatic profit-taking.
- Unrealized gain updates.
- No SELL transaction.

## Case 4 — Valuation Becomes Expensive

An existing stock moves from Fair to Expensive.

Business remains strong.

No materially better alternative is identified.

Expected:

- Reassessment occurs.
- No automatic sale.
- Position remains open.
- Decision explanation is recorded.

## Case 5 — Thesis Deterioration

An existing company's reported financials
materially deteriorate.

AI identifies a broken thesis supported by
the required evidence.

Expected:

- SELL decision.
- Simulated sale at next valid execution price.
- Realized P/L calculated.
- Position marked closed.
- Historical transaction retained.
- Cash balance updated.

## Case 6 — Replacement Opportunity

An existing holding meets replacement conditions.

A new company qualifies as a compelling,
materially superior opportunity.

Expected:

- SELL decision for existing holding.
- BUY decision for replacement.
- Correct execution ordering.
- Correct cash accounting.
- Both transactions recorded.
- Replacement relationship preserved.
- Historical holdings display both companies.
- Portfolio performance history remains continuous.

## Case 7 — Missing Financial Data

Required company metrics are unavailable.

Expected:

- Company does not automatically qualify.
- Missing values are not replaced with zero.
- No unsupported AI conclusion.
- No unauthorized simulated trade.

## Case 8 — AI Failure

OpenAI request fails or returns invalid output.

Expected:

- No new trades.
- Existing positions preserved.
- Error recorded.
- Portfolio accounting continues where valid.
- No duplicate requests caused by retries.

## Case 9 — Duplicate Workflow Execution

Run the same session twice.

Expected:

- No duplicate transactions.
- No duplicate snapshot.
- No duplicate AI analysis.
- Identical final portfolio state.

## Case 10 — Historical Accuracy

Buy Company A.

Hold for several sessions.

Sell Company A.

Buy Company B.

Expected:

- Historical equity reflects Company A's prices
  only while Company A was owned.
- Later equity reflects Company B after purchase.
- Historical performance is not recalculated as
  if Company B had always been owned.
- Realized gains and cash movements are preserved.
- VWCE comparison uses the same calendar baseline.

## Case 11 — No Look-Ahead

Generate a BUY signal using market close T.

Expected:

- No execution at close T.
- Execution at the next valid session's close.
- Historical snapshots reflect the actual
  execution timing.

## Case 12 — Currency and Corporate Actions

Test:

- USD-denominated stock.
- EUR portfolio.
- Historical FX conversion.
- Stock split.
- Cash dividend where supported.

Expected:

- Correct EUR portfolio valuation.
- Correct position quantity and cost basis.
- No dividend double-counting.
- No invented corporate-action data.

## Case 13 — Portfolio Comparison

Both portfolios begin at €10,000.

Expected:

- Both start from the same date and value.
- VWCE follows buy-and-hold.
- InvestOS reflects its actual trading ledger.
- Chart values reconcile to snapshots.
- Transaction costs are correctly applied.
- Percentage returns use the correct denominator.

---

# 26. DOCUMENTATION

Document the implemented architecture.

Explain:

- How daily automation works.
- Where investment rules are defined.
- How deterministic screening works.
- How AI analysis is performed.
- How candidates are selected.
- How BUY/HOLD/SELL decisions work.
- How simulated execution works.
- How portfolio history is stored.
- How performance is calculated.
- How VWCE is tracked.
- How GitHub Pages receives updates.
- How the OpenAI API key is configured.
- How to inspect failed runs.
- How to validate recorded transactions.

Describe the exact assumptions made in V1.

Clearly distinguish:

- Existing functionality reused.
- New functionality implemented.
- Any unavoidable limitations in the available
  financial-data provider.

Do not describe unsupported functionality
as already implemented.

---

# 27. IMPLEMENTATION CONSTRAINTS

Keep changes focused on this feature.

Avoid unnecessary refactoring.

Reuse current application architecture.

Reuse existing stock and financial data models.

Reuse existing anti-pattern detection.

Reuse existing filters and classification rules.

Reuse existing UI components.

Do not implement real-money brokerage integration.

Do not implement automated tax filing.

Do not create unrelated dashboards.

Do not add social functionality.

Do not introduce unrelated prediction models.

Do not create a second stock-scoring architecture.

Do not require a dedicated server.

Do not introduce paid market-data dependencies
without establishing that they are necessary.

If an essential capability is missing from the
existing financial-data provider, identify the exact
missing capability rather than fabricating data.

Implement all functionality supported by the
available codebase and data integrations.

Only external credentials and genuinely unavailable
provider capabilities may remain deployment blockers.

---

# 28. DEFINITION OF DONE

The feature is complete when:

1. The simulation can be initialized with €10,000.

2. VWCE and InvestOS start from the same baseline.

3. Financial screening runs automatically.

4. The existing anti-pattern system is integrated.

5. OpenAI analyzes eligible companies and holdings.

6. The decision engine determines BUY/HOLD/SELL.

7. Simulated orders execute without look-ahead.

8. Portfolio cash and positions are tracked accurately.

9. The strategy runs through GitHub Actions.

10. Historical portfolio data persists across runs.

11. GitHub Pages displays the two-line
    VWCE vs InvestOS historical chart.

12. The InvestOS drill-down displays current holdings.

13. The drill-down displays historical holdings.

14. Every purchase and sale includes its date,
    execution price, quantity, and result.

15. Every sale can be traced to its investment reason.

16. Every replacement can be linked to the
    previous investment.

17. The transaction ledger supports historical
    portfolio reconstruction.

18. VWCE and InvestOS performance calculations
    reconcile to their respective accounting records.

19. Duplicate runs cannot create duplicate trades.

20. Tests pass.

21. Existing InvestOS functionality remains intact.

22. The application clearly identifies the latest
    successful simulation update.

23. No external API secrets are exposed.

---

# 29. FINAL INSTRUCTIONS TO CODEX

Do not stop after analyzing the repository.

Do not stop after writing an implementation plan.

Do not leave placeholder functions.

Do not implement only the UI.

Do not implement only the daily automation.

Do not create fake historical results to make
the dashboard appear populated.

Inspect the codebase and implement the complete
end-to-end simulated investment system.

Use the fixed V1 rules in this specification.

Reuse the existing InvestOS architecture.

Make the smallest coherent set of changes necessary.

Run the relevant tests.

At completion provide:

1. Summary of implementation.
2. Architecture overview.
3. Files created or modified.
4. Exact implemented BUY rules.
5. Exact implemented HOLD rules.
6. Exact implemented SELL and replacement rules.
7. Explanation of AI integration.
8. Explanation of GitHub Actions automation.
9. Explanation of simulation persistence.
10. Explanation of performance accounting.
11. Confirmation of historical transaction tracking.
12. Confirmation of VWCE comparison.
13. Tests executed and results.
14. Any missing external credentials.
15. Any actual data-provider limitations.
16. Exact deployment steps, if any remain.

The final objective is an operational InvestOS simulation
that continuously evaluates its investment strategy
against passive VWCE investing while preserving a
complete, auditable history of every investment decision.

IMPLEMENT THE FEATURE.