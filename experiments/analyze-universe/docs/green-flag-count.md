# Green Flag Count

## What it means

Which positive financial patterns appear in the company's reported data?

Counts [Sustained revenue growth](flags/green/sustained-revenue-growth.md), [Profitable growth](flags/green/profitable-growth.md) and [Cash-backed earnings](flags/green/cash-backed-earnings.md). Each met rule contributes one point, for an exact integer from **0 to 3** when all three are assessed.

The two growth rules overlap. This is a count of rules met, not independent strengths, an investment-quality score or a valuation assessment. Green and red counts are displayed separately and are never netted.

## Coverage and filtering

The [green-flag input requirements](flags/green/README.md#shared-requirements) apply. Missing, invalid, unsupported or stale inputs do not become zero. Partial coverage retains `observed_count`, displayed as **≥N** for confirmed rules; otherwise cells show **Not fully assessed**.

The experiment ranking HTML provides separate Red flags and Green flags columns for every stock. Each cell shows detected rule names and expandable conditions. Its existing financial filter still uses revenue growth, operating margin and red-flag count; green flags do not change membership or the original ranking. This metric is experimental and is not registered in the main app.

Experiment green counts use assessment version 1 and are stored in the captured experiment financial refresh, independently of the main app screening schema. The latest fundamentals quarter-end determines their 140-day validity; market prices do not refresh or expire these business-pattern checks.
