# Completed in the conversation

All 200 stocks were individually assessed and ranked on 25 October 2026 using the existing Analyze prompt, data formatter and descriptive methodology. Quotes are dated 23 October 2026.

- [Full ranking](ranking.md)
- [Colored searchable table](ranking.html)
- [CSV](ranking.csv)
- [Research checks](research-notes.json)
- [Validation](result-metadata.json)
- [Support and three-rule audit](filter-research/support-audit.md)

The HTML defaults to the 64 stocks at/near support. Select the financial-rule result to show the 33 that pass all three rules or the 31 that do not; each row explains its result. Unchecking the support filter restores all 200 stocks. Original ranks and assessments are preserved.

Business quality and valuation receive equal importance. Every company appears exactly once. Assessments are provisional, and the dataset's missing forecasts, inconsistent inputs and sector limitations are reflected in rationales/Unknown labels. Selected primary-source checks cover six companies; they are distinguished from saved snapshot facts.

The analysis was authored here in the Codex conversation. No successful Gemini generation contributed to the ranking. Failed API attempts are archived under `failed-api-history`; the active runner makes no model API calls.

The deterministic control and original dataset are preserved for the later membership-versus-ranking comparison. Application code, production data and the paper portfolio are unchanged.
