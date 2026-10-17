# Refresh audit — 17 October 2026

The latest production price refresh is current and internally consistent. The
fundamentals workflow makes real SEC requests and its short runtime is explained
by incremental collection. However, its filing filter and failure reporting have
gaps that prevent treating a green workflow as proof that every issuer's newest
financial report has been incorporated.

This was a read-only production audit. No refresh was dispatched, no deployment
was made, and no application code or stock data was changed. Existing local data
changes were preserved. Downloaded evidence is under `/tmp/invest-os-audit/`.

## Production evidence

| Check | Observed result |
| --- | --- |
| Latest fundamentals workflow | [16 October run](https://github.com/IgnacioGoldman/invest-os/actions/runs/38920083737): success; approximately 3m39s including setup and deployment |
| Fundamentals collection step | 44s: approximately 38s of SEC preflight checks, then 6s of parallel collection |
| Fundamentals disposition | 77 stocks: 70 preserved, 7 recollected, 0 failures |
| Recollected stocks | AXFO.ST and NIBE-B.ST as non-SEC issuers; V, DT, YPF, TER and INTU for missing current inputs |
| Fresh SEC comparison | All 75 SEC issuers matched the accession selected by the app's existing relevance rules; no request errors during this audit |
| Latest price workflow | [16 October run](https://github.com/IgnacioGoldman/invest-os/actions/runs/38978470251): success; approximately 2m10s overall, 32s in the refresh step |
| Live data | [Published metadata](https://ignaciogoldman.github.io/invest-os/data/meta.json): generated 16 October at 22:55 UTC; all 77 prices dated 16 October |
| Published chart histories | All 77 latest candle dates and closes agree with their displayed current prices |
| Fresh Yahoo comparison | AAPL, MSFT, NVDA, CALM, AXFO.ST and NIBE-B.ST all agree with separately fetched Yahoo quotes to the displayed cent |
| Valuation arithmetic | 381 available calculations checked: market cap, P/E, price/sales and FCF yield for 77 stocks, plus EV/EBITDA for 73; no mismatches against saved inputs |
| Existing regression tests | 61 passed across incremental SEC, price refresh, refresh separation, static validation, fundamentals fallback and provider suites |

Saturday 17 October follows Friday's market session, so 16 October is the expected
latest price date. The local working copy has older exported data; the production
findings above use freshly downloaded live files, rather than that local copy.

## Why fundamentals finish quickly

The daily workflow uses `--incremental-sec`, `--reuse-saved-prices`,
`--repair-current-data`, `--repair-revenue-history` and `--skip-filing-details`.

It fetches recent SEC submissions metadata for each SEC issuer and compares the
latest relevant accession with its saved state. Healthy unchanged companies keep
their saved fundamentals. Changed or incomplete companies are collected using
the SEC Company Facts API, with supported issuer/vendor supplementation. Non-SEC
companies are collected separately. Company Facts supplies aggregated financial
facts in one JSON request per issuer; this is not a crawl and parse of every new
filing document. These endpoints and their behavior are described in the
[SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

On the inspected run, all five recollected SEC companies had repair reasons;
the other two were non-SEC companies. Most of the universe needed only the
metadata check. Approximately 38 seconds for 75 checks also agrees with the
provider's half-second SEC request pacing. The workflow does not restore the raw
SEC cache between jobs, so its fresh-run speed is not explained by reusing a
previous runner's cached SEC responses.

The price workflow requests recent Yahoo daily candles, with Stooq as fallback,
merges overlapping dates into saved history, and recalculates prices, returns,
support metrics and valuations from saved financial inputs. It disables SEC
requests. These prices are daily candles, which can include the developing daily
bar during market hours; the workflow does not provide streaming quotes.

## Findings requiring follow-up

### 1. Generic 6-K financial reports can be ignored

`scripts/open_data_poc.py:_is_relevant_sec_filing` recognizes 6-K reports only if
the document filename or description contains selected words such as `earnings`,
`results` or `quarter`.

A concrete example in fresh SEC metadata is Novartis accession
`0001114448-26-000012`, filed 21 July 2026, document `nvs-20260630.htm`, description
`6-K`. The filter returns false. Its saved gate consequently points to the
4 February 20-F instead. Matching this gate against fresh SEC metadata therefore
does not establish that every actual financial filing was recognized.

Novartis's currently saved revenue already includes Q2 2026 from its issuer
report. This audit did not establish a missing current revenue quarter. The
problem is future detection: an unchanged gate can skip collection and thereby
skip the issuer report check inside `refresh_issuer_revenue` as well.

Recommended correction: schedule supported issuer report discovery independently
of the SEC accession gate and handle generic foreign-issuer 6-K reports without
requiring descriptive financial keywords. Metadata alone is insufficient to
classify all such reports reliably.

### 2. Failed SEC checks can be reported as unchanged

`OpenDataProvider._fetch_sec_submissions` returns `None` after request failure.
The incremental gate accepts a missing latest accession as a reason to preserve
an existing snapshot and labels it `sec_filings_unchanged`.

Reproduced using the live AAPL snapshot and a simulated unavailable submissions
response: zero selected, one preserved, reason `sec_filings_unchanged`.
CIK-resolution failures also have a separate preserve-existing path. Static
validation does not reject either condition solely because freshness was not
verified.

The inspected production logs did not show this SEC failure. This is a confirmed
error-path weakness, not evidence that Friday's SEC requests failed.

Recommended correction: distinguish verified unchanged, updated, and unverified
preservation; expose source errors and counts in the report and workflow summary,
and prevent an unverified run from claiming fully checked fundamentals.

### 3. Price fallback can pass with old data

`fetch_updated_history` retains baseline candles if recent price retrieval is
empty. That result is counted as collected, and the snapshot generation timestamp
advances. The validator rejects dates more than seven calendar days old, but does
not require the latest expected completed session. A source outage can therefore
leave several days of stale prices while producing a green run.

This did not occur in the inspected production refresh: all 77 published prices
are from the latest completed session and the six fresh quote checks matched.

Agreed correction: report fetched versus retained histories separately while
preserving the existing validation rules. Reconsider exchange-session freshness
checks after reviewing several scheduled runs, including holidays and market
hours, so stricter checks do not reintroduce earlier deployment failures.

## Other limits

The coverage report still identifies missing fundamental inputs for AXFO.ST, DT,
INTU, TER, V and YPF. Daily collection retries the applicable current gaps, but
successful execution does not guarantee complete financial coverage. All 77
stocks had a usable revenue momentum window in the inspected coverage report.

SEC Company Facts and the supported fallbacks do not guarantee immediate parsing
of every new earnings release or exhibit. Some values may retain their original
verified observation dates. A snapshot generation timestamp is not the reporting
date of every financial metric.

The scheduled fundamentals run configured for 10:30 UTC started at 14:58 UTC on
16 October. GitHub scheduling should not be treated as a precise publication
time; this audit observed the delay but did not establish its cause.

## Implementation follow-up

Local changes add refresh status counts, SEC verification counts, source notes,
and observation dates to the reports and GitHub validation summary. An unavailable
SEC check retains the saved snapshot without marking filings unchanged or
advancing its SEC state. Supported issuer checks now run independently when due,
with attempt metadata persisted in issuer JSON. Optional issuer-only collection
failures preserve the snapshot and appear in reporting; downloaded issuer facts
newer than that snapshot remain eligible for collection during discovery backoff.

The existing retries, saved-price fallback, seven-day price age limit and adjacent
US/Stockholm session allowance remain in place. Production behavior can be observed
after these changes are deployed; no deployment was performed during this work.
