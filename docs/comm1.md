# Investful OS — Improve Revenue Growth Analysis, Restore Historical Charts, and Extend Filtering

## Objective

Improve how Investful OS evaluates revenue growth by considering multiple historical quarters rather than relying exclusively on the latest Revenue Growth YoY value.

We want to distinguish between:
1. Companies growing strongly right now.
2. Companies whose growth is accelerating or decelerating.
3. Companies showing consistent growth versus irregular or isolated spikes.

These three signals must be:
- Calculated using historical quarterly data.
- Displayed clearly on the Stock Details page.
- Available as conditions in the existing filtering system.
- Consistent with the application's existing UI and color conventions.

IMPORTANT: Some of this functionality existed previously and may have been lost during UI changes. Inspect the existing implementation before making changes. Restore or reuse existing functionality wherever possible rather than rebuilding everything.

---

## 1. Revenue Growth YoY — Preserve Existing Functionality

The application already calculates Revenue Growth Year over Year.

This metric must remain available.

It represents the revenue growth of the latest reported quarter compared with the equivalent quarter one year earlier.

Requirements:

- Preserve the existing calculation.
- Preserve the existing classification system:
  - Strong
  - Solid
  - Flat
  - Weak
  - Unavailable/Unclear
- Preserve the existing semantic colors.
- Display the latest percentage prominently in Stock Details.
- Make the metric available in filters.

### Restore Historical Chart

Previously, clicking the Revenue Growth YoY metric displayed a historical chart at the bottom of the Stock Details page.

That functionality has disappeared.

Restore it.

Expected behavior:

1. User opens Stock Details.
2. User clicks Revenue Growth YoY.
3. A historical chart appears in the existing chart/detail area at the bottom.
4. The chart displays the quarterly Revenue Growth YoY values.
5. Individual quarterly values can be inspected.
6. The data is displayed chronologically.
7. Negative growth must be represented correctly.

Reuse the original chart component and interaction pattern if they still exist.

Do not introduce a completely different UI unnecessarily.

---

## 2. Revenue Growth Momentum — Preserve and Improve

The application previously calculated Revenue Growth Momentum.

It also had a useful visual presentation that may have disappeared.

Investigate the existing implementation and restore the functionality and presentation where necessary.

Momentum answers:

"Is the company's revenue growth accelerating, decelerating, or remaining relatively stable?"

### Calculation

Use multiple consecutive quarterly Revenue Growth YoY observations.

Prefer the latest 6–8 quarters where data is available.

Avoid classifying a company as accelerating simply because its latest quarter experienced an isolated spike.

For example:

Company A:
1%, 1%, 1%, 1%, 1%, 100%

Company B:
12%, 14%, 16%, 18%, 20%, 22%

Company A should not automatically receive a strong acceleration signal based exclusively on its latest quarter.

Company B demonstrates a much more convincing acceleration pattern.

The calculation should consider sustained changes over multiple quarters.

Possible classifications:

- Accelerating
- Stable
- Decelerating
- Unclear / Insufficient Data

Prefer a robust comparison of recent and earlier growth observations, with safeguards against isolated outliers.

Define and document the thresholds and minimum evidence required for each classification.

### UI

Display Revenue Growth Momentum in Stock Details.

Reuse the previous visual presentation if possible.

Maintain the existing application's semantic colors and compact design.

Allow users to inspect the historical data supporting the momentum classification.

Momentum must also be available as a filtering condition.

---

## 3. NEW: Revenue Growth Consistency

Introduce a new derived metric:

Revenue Growth Consistency

This answers:

"Has the company's revenue growth followed a reasonably consistent pattern, or has it been irregular?"

### Classification

Keep this metric simple.

Use:

- Steady
- Choppy
- Insufficient Data

Do NOT introduce a numerical 1–10 consistency score at this stage.

### Calculation

Evaluate the historical quarterly Revenue Growth YoY series.

Prefer 6–8 quarters.

Consider:

- Variability across quarters.
- Large isolated spikes.
- Sudden reversals.
- Repeated positive or negative growth patterns.
- Whether apparent acceleration is sustained or driven by one exceptional quarter.

A steadily accelerating business should generally be classified as Steady.

For example:

12%, 14%, 16%, 18%, 20%, 22%

This is Steady growth, even though the growth rate is increasing.

By contrast:

1%, 2%, 0%, 80%, -5%, 3%

This is Choppy.

Consistency should measure the reliability of the historical pattern, not simply whether the growth percentage remains identical.

Important:

- Steady does not necessarily mean strong.
- A company consistently growing at 2% can be Steady.
- A company consistently declining can also have a steady pattern.
- Consistency must remain separate from growth strength and growth momentum.
- Do not automatically assume a large increase is unsustainable. If the company establishes a new sustained growth pattern, the calculation should recognize that.

Use a transparent, deterministic calculation with documented thresholds.

---

## 4. Stock Details — Display All Three Signals

The Stock Details page should clearly present:

### Revenue Growth YoY
Shows the latest quarterly growth percentage and its existing classification.

Example:
Revenue Growth YoY: 22% — Strong

### Revenue Growth Momentum
Shows the historical direction of growth.

Example:
Momentum: Accelerating

### Revenue Growth Consistency
Shows whether the historical pattern is reliable.

Example:
Consistency: Steady

These should be displayed together within the existing growth/performance section.

Design requirements:

- Compact presentation.
- Clear labels.
- Consistent semantic colors.
- Reuse existing badges, indicators, and components.
- Avoid unnecessary explanatory paragraphs.
- Preserve the existing visual hierarchy.
- Support missing or insufficient data gracefully.

The goal is to make the three signals immediately understandable without overwhelming the user.

---

## 5. Historical Visualization

Users should be able to understand WHY a company received its classifications.

Restore the historical Revenue Growth YoY chart.

The chart should display all available quarterly observations within the selected historical range.

For example:

Q1: 12%
Q2: 14%
Q3: 16%
Q4: 18%
Q5: 20%
Q6: 22%

Requirements:

- Chronological quarterly chart.
- Percentage values.
- Clear handling of negative values.
- Individual values accessible on interaction.
- Consistent styling with the existing application.
- Reuse existing chart infrastructure.
- Maintain the previous click-to-display behavior.

If feasible within the existing UI architecture, Revenue Growth Momentum and Revenue Growth Consistency should use this same historical chart to explain their classifications.

Do not create three redundant charts.

The objective is one reusable historical visualization supporting all three metrics.

---

## 6. Filtering — Make All Three Metrics Available

Extend the existing stock filtering system.

Users must be able to create filter conditions based on:

### Revenue Growth YoY

Preserve existing filtering capabilities.

Support percentage comparisons such as:

Revenue Growth YoY > 15%

Also preserve categorical filtering if already supported.

### Revenue Growth Momentum

Allow categorical filtering:

- Accelerating
- Stable
- Decelerating

Example:

Revenue Growth Momentum = Accelerating

### Revenue Growth Consistency

Allow categorical filtering:

- Steady
- Choppy

Example:

Revenue Growth Consistency = Steady

### Combined Filtering

All three conditions must work together using the existing filter engine.

Example:

Revenue Growth YoY > 15%
AND
Revenue Growth Momentum = Accelerating
AND
Revenue Growth Consistency = Steady

This should identify companies with:

- Strong current growth.
- Sustained acceleration.
- A reasonably consistent historical pattern.

Requirements:

- Integrate with the existing custom-filter creation flow.
- Preserve existing presets.
- Preserve existing filters.
- Follow existing condition operators and AND/OR logic.
- Do not introduce a separate filtering interface.
- Handle unavailable metrics correctly.
- Do not silently treat missing data as zero or as a favorable classification.

Make the derived metrics available to the existing sorting system where the data type supports meaningful sorting. Do not assign arbitrary numerical rankings to categorical labels merely to enable sorting.

---

## 7. Historical Data Requirements

Inspect the existing quarterly financial data model.

The application already collects historical revenue observations.

Reuse that data.

Important distinction:

Six quarterly Revenue Growth YoY observations generally require at least ten consecutive quarters of underlying revenue data.

Eight YoY observations require twelve quarters.

This is because each YoY growth observation compares a quarter against the same quarter in the previous year.

Requirements:

- Calculate YoY growth using the corresponding prior-year quarter.
- Prefer 8 YoY observations when available.
- Support 6 observations as the normal minimum for full historical classification.
- Handle shorter histories as insufficient data for classifications that cannot be supported.
- Handle missing quarters correctly.
- Avoid treating incomplete data as consecutive observations.
- Avoid confusing QoQ growth with YoY growth.
- Avoid look-ahead bias.
- Avoid invented or interpolated financial values.

The latest Revenue Growth YoY metric should remain available even if there is insufficient history to calculate Momentum or Consistency.

Use existing data-fetching and caching mechanisms wherever possible.

Avoid unnecessary additional API requests.

---

## 8. Architecture and Maintainability

These metrics should be implemented as reusable derived metrics.

Do not duplicate calculation logic across:

- Stock Details
- Explore
- Filtering
- AI analysis/export functionality

Prefer a single source of truth for:

- Revenue Growth YoY
- Revenue Growth Momentum
- Revenue Growth Consistency

Ensure the same company receives consistent classifications everywhere in the application.

If the existing AI analysis payload includes stock metrics, expose the three signals and their supporting quarterly observations through the established payload structure.

Do not add a separate AI scoring system.

Do not introduce a new composite revenue growth score.

Keep the three signals independent.

---

## 9. Testing

Add or update tests covering:

### Strong and Steady Growth

12%, 14%, 16%, 18%, 20%, 22%

Expected:
- Sustained accelerating momentum.
- Steady consistency.

### Isolated Spike

1%, 1%, 1%, 1%, 1%, 100%

Expected:
- Latest growth is very strong.
- Momentum must not automatically be classified as sustained acceleration.
- Consistency identifies the isolated spike as choppy.

### Stable Low Growth

2%, 2%, 3%, 2%, 2%, 3%

Expected:
- Relatively stable momentum.
- Steady consistency.
- Low historical growth strength.

### Decelerating Growth

30%, 26%, 22%, 18%, 14%, 10%

Expected:
- Decelerating momentum.
- Steady consistency.

### Irregular Growth

15%, -5%, 30%, 2%, 40%, -10%

Expected:
- Choppy consistency.
- Momentum should not misleadingly suggest reliable acceleration.

Also test:

- Missing quarters.
- Insufficient historical data.
- Negative revenue growth.
- Zero prior-year revenue.
- Existing filters.
- Combined filter conditions.
- Historical chart interaction.
- Consistency between displayed metrics and filtering calculations.

---

## 10. Implementation Instructions

Before changing code:

1. Inspect the existing Revenue Growth YoY implementation.
2. Locate the previous Revenue Growth Momentum implementation.
3. Inspect Stock Details and the historical chart components.
4. Determine why clicking Revenue Growth YoY no longer displays its historical chart.
5. Inspect the existing filtering architecture and available metric definitions.
6. Identify which functionality can be restored instead of recreated.

Then implement the changes.

Important:

- Preserve existing functionality.
- Preserve existing visual design.
- Avoid unnecessary refactoring.
- Avoid introducing additional UI complexity.
- Use deterministic calculations.
- Document calculation logic and thresholds.
- Keep performance and API usage efficient.
- Do not modify unrelated features.

## Expected Outcome

After implementation, Investful OS should allow users to:

1. See the latest Revenue Growth YoY and its existing classification.
2. See whether growth is accelerating, stable, or decelerating.
3. See whether historical growth is steady or choppy.
4. Click Revenue Growth YoY and inspect the historical quarterly chart again.
5. Use all three metrics when creating custom stock filters.
6. Distinguish sustainable growth patterns from isolated quarterly spikes.

At completion, provide:

- A summary of what was implemented.
- Which previous functionality was restored.
- The precise calculation rules and thresholds selected.
- Any data limitations.
- Tests performed and their results.
- Any remaining issues.

Do not stop at an implementation plan. Inspect the codebase, implement the functionality, and run the relevant tests.