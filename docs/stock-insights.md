# Stock research screening

Invest OS surfaces stocks worth researching. It does not generate investment-quality ratings, composite conviction scores or buy/sell conclusions. The [metric index](metrics/README.md) documents the current six financial cards, optional details, neutral price/earnings context and retired metrics.

Financial values come from a shared deterministic screening projection that checks source periods, currency, denominator effects, estimate freshness and anomalies. Cards, filters, badge evaluation and AI exports use that projection. Missing or unreliable inputs are Unknown/Needs Review, never zero. A source identifier preserves provenance; it does not independently verify a value.

Raw reported facts, historical ratios and filing context remain in AI briefs, including exceptional-earnings and recent negative-FCF warnings. The brief requests evidence and research priorities. Retired saved filters require explicit edits before matching stocks; they are never silently broadened.
