"""Publish a reviewable shortlist without activating stocks or collecting app data."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import hashlib
import json
from pathlib import Path

from screen_revenue_expansion import AS_OF, RESEARCH, ROOT
from build_stock_universe import SECTOR_ALIASES
from app.services.revenue_growth_momentum import _quarter_index

OUTPUT = ROOT / "docs/research/revenue-expansion-2026-10-17"
SPOT_CHECKS = {
    "CRDO": ("https://investors.credosemi.com/news-events/news/news-details/2026/Credo-Technology-Group-Holding-Ltd-Reports-First-Quarter-of-Fiscal-Year-2027-Financial-Results/default.aspx", "Issuer reports approximately 115% revenue growth for the quarter ended 1 August 2026."),
    "CRWV": ("https://investors.coreweave.com/news/news-details/2026/CoreWeave-Reports-Strong-Second-Quarter-2026-Results/default.aspx", "Issuer Q2 2026 release corroborates the revenue comparison."),
    "ALAB": ("https://ir.asteralabs.com/news-releases/news-release-details/astera-labs-reports-second-quarter-2026-financial-results", "Issuer reports USD392.4m revenue and approximately 104% YoY growth for Q2 2026."),
    "RDDT": ("https://investor.redditinc.com/news-events/news-releases/news-details/2026/Reddit-Reports-Second-Quarter-2026-Results/", "Issuer reports USD805m revenue and approximately 61% YoY growth for Q2 2026."),
    "CVNA": ("https://investors.carvana.com/news-releases/2026/07-29-2026-210525685", "Issuer reports USD7.376bn revenue and approximately 52% YoY growth for Q2 2026."),
    "APH": ("https://investor.amphenol.com/news-and-events/news-details/2026/Amphenol-Reports-Record-Second-Quarter-2026-Results/default.aspx", "Issuer reports 55% reported sales growth, including 24 percentage points from acquisitions and approximately 1 point from FX; organic growth is 30%."),
    "PLMR": ("https://ir.palomarspecialty.com/news-releases/news-release-details/palomar-holdings-inc-reports-second-quarter-2026-results", "Total GAAP revenue is USD314.423m versus USD203.311m; premium-growth headlines use different revenue definitions."),
}


def main():
    screened = json.loads((RESEARCH / "cached-screen.json").read_text())
    verified = json.loads((RESEARCH / "verified-screen.json").read_text())
    universe_path = OUTPUT / "base-universe.json"
    if not universe_path.exists():
        universe_path = ROOT / "data/stocks/stocks.json"
    existing = json.loads(universe_path.read_text())["rows"]
    existing_symbols = {r["symbol"] for r in existing}
    existing_ciks = {r["cik"] for r in existing if r.get("cik")}
    eligible = [r for r in verified["rows"] if r["verified_eligible"]]
    # Require an established revenue base throughout all ten quarters needed
    # to calculate the latest six comparable year-over-year observations.
    consistent = [r for r in eligible if r["solid_quarters_6q"] == 6
                  and r["reporting_currency"] == "USD"
                  and len(r["quarters"]) == 10
                  and min(q["metrics"]["revenue"]["value"] for q in r["quarters"]) >= 25_000_000]
    consistent.sort(key=lambda r: (-r["growth_score"], -r["minimum_growth_6q"], r["symbol"]))
    selected = consistent[:123]
    if len(selected) != 123:
        raise ValueError(f"Need 123 qualifying stocks; found {len(selected)}")
    assert len({r["symbol"] for r in selected}) == 123
    assert len({r["cik"] for r in selected}) == 123
    assert not existing_symbols.intersection(r["symbol"] for r in selected)
    assert not existing_ciks.intersection(r["cik"] for r in selected)
    for r in selected:
        assert r["minimum_growth_6q"] >= 8
        assert r["latest_sec_financial_filing"]["accessionNumber"] in r["revenue_accessions"]
        assert r["latest_sec_financial_filing"]["reportDate"] <= r["latest_period_end"]
        assert not r["newer_earnings_filings"]
        assert r["market_cap_usd"] >= 500_000_000 and r["price_usd"] >= 5
        assert r["latest_quarter_revenue"] >= 25_000_000
        assert min(q["metrics"]["revenue"]["value"] for q in r["quarters"]) >= 25_000_000
        assert (AS_OF - date.fromisoformat(r["latest_period_end"])).days <= 140
        for i, quarter in enumerate(r["quarters"]):
            if i:
                assert _quarter_index(quarter["period"]) == _quarter_index(r["quarters"][i-1]["period"]) + 1
            if i >= 4:
                prior = r["quarters"][i-4]
                computed = (quarter["metrics"]["revenue"]["value"] / prior["metrics"]["revenue"]["value"] - 1) * 100
                assert abs(computed - quarter["metrics"]["revenue_growth_yoy"]["value"]) < 1e-8, r["symbol"]
        assert r["latest_sec_financial_filing"]["filingDate"] <= AS_OF.isoformat()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sectors = Counter(SECTOR_ALIASES.get(r["sector"], r["sector"]) for r in selected)
    statuses = Counter("Strong" if r["latest_growth_yoy"] >= 20 else "Solid" for r in selected)
    stats = {
        "as_of": AS_OF.isoformat(), "existing_stocks": len(existing), "additions": len(selected),
        "target_stocks": len(existing) + len(selected), "cached_sec_issuers": screened["cached_facts_count"],
        "screened_new_listed_issuers": screened["screened_issuers"],
        "candidates_sent_to_current_verification": len(verified["rows"]),
        "verified_eligible": len(eligible), "consistent_eligible": len(consistent),
        "latest_growth_status_counts": dict(statuses), "sector_counts": dict(sectors),
        "minimum_selected_latest_yoy_pct": min(r["latest_growth_yoy"] for r in selected),
        "minimum_selected_six_quarter_yoy_pct": min(r["minimum_growth_6q"] for r in selected),
        "base_universe_sha256": hashlib.sha256(universe_path.read_bytes()).hexdigest(),
    }
    manifest_rows = []
    csv_rows = []
    for rank, r in enumerate(selected, 1):
        history = r["quarters"][-6:]
        research = {key: r[key] for key in (
            "latest_period", "latest_period_end", "latest_growth_yoy", "median_growth_6q",
            "recent_median_growth_3q", "prior_median_growth_3q", "minimum_growth_6q",
            "momentum", "momentum_pp", "growth_score", "flags", "reporting_currency",
            "latest_quarter_revenue", "market_cap_usd", "price_usd", "verified_at",
            "latest_revenue_filed", "latest_sec_financial_filing", "source_url", "filing_url", "sec_metadata_url")}
        research["quarters"] = r["quarters"]
        research["latest_status"] = "Strong" if r["latest_growth_yoy"] >= 20 else "Solid"
        research["rank"] = rank
        research["source_sector"] = r["sector"]
        if r["symbol"] in SPOT_CHECKS:
            research["issuer_release_url"], research["issuer_release_note"] = SPOT_CHECKS[r["symbol"]]
        manifest_rows.append({
            "symbol": r["symbol"], "name": r["name"], "cik": r["cik"], "exchange": r["exchange"],
            "country": r["country"], "region": "US" if r["country"] == "United States" else "ADR",
            "quote_type": "ADR" if "depositary" in r["listing_metadata"]["name"].lower() else "EQUITY",
            "sector": SECTOR_ALIASES.get(r["sector"], r["sector"]), "industry": r["industry"], "research": research,
        })
        item = {"rank": rank, "symbol": r["symbol"], "name": r["name"], "sector": SECTOR_ALIASES.get(r["sector"], r["sector"]),
                "industry": r["industry"], "country": r["country"], "latest_period": r["latest_period"],
                "latest_period_end": r["latest_period_end"], "latest_status": research["latest_status"],
                "latest_yoy_pct": round(r["latest_growth_yoy"], 4),
                "median_6q_yoy_pct": round(r["median_growth_6q"], 4),
                "minimum_6q_yoy_pct": round(r["minimum_growth_6q"], 4),
                "momentum": r["momentum"], "momentum_pp": round(r["momentum_pp"], 4),
                "market_cap_usd": r["market_cap_usd"], "quarter_revenue_usd": r["latest_quarter_revenue"],
                "notes": "; ".join(r["flags"]), "filing_url": r["filing_url"], "sec_facts_url": r["source_url"]}
        for i, q in enumerate(history):
            item[f"q_minus_{5-i}_period"] = q["period"]
            item[f"q_minus_{5-i}_yoy_pct"] = round(q["metrics"]["revenue_growth_yoy"]["value"], 4)
        csv_rows.append(item)
    manifest = {"discovery_only": True, "statistics": stats,
                "selection_rule": "Six consecutive quarterly revenue YoY rates >=8%; USD reporting; latest period <=140 days old; every one of ten comparison quarters has revenue >=USD25m; current market cap >=USD500m and price >=USD5; current SEC financial filing represented; no newer pending earnings 8-K.",
                "tickers": [r["symbol"] for r in selected], "rows": manifest_rows}
    (OUTPUT / "candidates.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (OUTPUT / "candidates.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    lines = [
        "# Revenue-led expansion: 77 to 200 stocks", "", "Research date: 17 October 2026.", "",
        f"**123 proposed additions**, selected from {screened['screened_issuers']:,} new listed issuers with cached SEC facts. "
        f"{len(verified['rows'])} promising or previously growing candidates received current listing/filing checks; "
        f"{len(consistent)} met the conservative final screen. The original 77 stocks were excluded by ticker and SEC issuer identity.", "",
        "This is a research shortlist. The active universe, SQLite database, and website exports have not been changed by this discovery work. "
        "The existing 77 stocks were retained as the starting universe and were not required to pass this new screen.", "",
        "## Selection", "",
        "- All six consecutive quarterly revenue YoY growth observations are **at least 8%**. The latest quarter is Strong at >=20%, otherwise Solid.",
        "- Every quarter in the ten-quarter revenue comparison window has at least USD25m of revenue. This avoids selecting extreme percentage growth from a very small historical revenue base.",
        "- Latest quarterly reporting period is no more than 140 days old, with consistent USD reporting across the comparison window. Rates of 100%+ are flagged, not automatically rejected.",
        "- Current Nasdaq directory listing, market cap >=USD500m, price >=USD5, and matching SEC ticker. No sector quotas were imposed.",
        "- The latest supported SEC financial filing accession must appear in revenue facts; its reporting date cannot exceed the extracted latest revenue quarter. A newer earnings 8-K with Item 2.02 sends a company to further review.",
        "- Quarterly calculations and fiscal-calendar normalization reuse the application's existing revenue and momentum functions. Q4 may be annual revenue less nine-month revenue.", "",
        "Rank is a screening order: 60% six-quarter median growth, 30% minimum growth in the latest three quarters, and 10% the fraction of six quarters above 8%; growth inputs are capped at 50% before scoring. "
        "Ties use the six-quarter minimum, then ticker. All selected companies have six qualifying quarters, so their consistency component is equal.", "",
        "This evaluates reported revenue growth. It does not establish organic growth, profitability, financial strength, valuation, or expected stock returns. "
        "Acquisitions and currency translation can contribute to reported USD growth. Sector revenue definitions differ, especially for financial companies. "
        "Decelerating companies remain eligible when all six quarters meet the growth threshold.", "",
        "## Coverage", "", f"Latest-quarter classifications: **{statuses['Strong']} Strong**, **{statuses['Solid']} Solid**.", "",
        "| Sector (normalized Nasdaq labels) | Additions |", "| --- | ---: |",
    ]
    lines += [f"| {sector} | {count} |" for sector, count in sectors.most_common()]
    lines += ["", "## Proposed 123 additions", "",
              "All growth values below are percentages. The six-quarter sequence runs oldest to newest; fiscal-quarter labels and underlying revenues are included in the JSON and CSV.", "",
              "| Rank | Stock | Company | Latest period end | Latest YoY | 6Q median | Six quarterly YoY rates | Momentum |", "| ---: | --- | --- | --- | ---: | ---: | --- | --- |"]
    for rank, r in enumerate(selected, 1):
        growths = ", ".join(f"{q['metrics']['revenue_growth_yoy']['value']:.1f}" for q in r["quarters"][-6:])
        name = r["name"].replace("|", "/")
        lines.append(f"| {rank} | [{r['symbol']}]({r['filing_url']}) | {name} | {r['latest_period_end']} | {r['latest_growth_yoy']:.1f}% | {r['median_growth_6q']:.1f}% | {growths} | {r['momentum']} |")
    alternates = [r for r in eligible if r not in consistent]
    lines += ["", "## Higher-growth and less-consistent alternatives", "",
              "These passed the broader screen (latest three quarters >=8%, six-quarter median >=8%, at least five positive quarters) but not the conservative final screen. They are excluded from the proposed 123.", "",
              "| Stock | Latest YoY | 6Q median | Quarters >=8% | Reason for separate review |", "| --- | ---: | ---: | ---: | --- |"]
    for r in alternates[:40]:
        reasons = []
        if r["solid_quarters_6q"] < 6:
            reasons.append("fewer than six quarters >=8%")
        if len(r["quarters"]) < 10 or any(q["metrics"]["revenue"]["value"] < 25_000_000 for q in r["quarters"]):
            reasons.append("historical quarter revenue below USD25m or incomplete window")
        reason = "; ".join(reasons)
        if r["reporting_currency"] != "USD":
            reason += "; non-USD reporting"
        lines.append(f"| [{r['symbol']}]({r['filing_url']}) | {r['latest_growth_yoy']:.1f}% | {r['median_growth_6q']:.1f}% | {r['solid_quarters_6q']}/6 | {reason} |")
    rejected = [r for r in verified["rows"] if not r["verified_eligible"]]
    lines += ["", "## Filing and data exceptions", "", "These companies need additional source or comparability work, or no longer meet the screen:", "",
              "| Stock | Reason |", "| --- | --- |"]
    for r in rejected:
        reasons = r["verification_exclusions"] + r["screen_exclusions"]
        lines.append(f"| {r['symbol']} | {'; '.join(reasons).replace('|', '/')} |")
    lines += ["", "## Issuer-release spot checks", "",
              "These are sample checks of the SEC-derived latest-quarter figures against issuer releases, not a manual review of every company:", ""]
    lines += [f"- [{symbol}]({url}): {note}" for symbol, (url, note) in SPOT_CHECKS.items() if symbol in {r["symbol"] for r in selected}]
    lines += ["", "## Sources and limits", "",
              "The starting pool is the approximately 2,000 issuers already represented in the project's SEC cache, not an exhaustive screen of every listed stock. "
              "Cached growth that already failed persistence criteria was not universally refreshed. Consequently these are 123 qualifying additions from this pool, not a claim about the 123 best revenue growers in the entire market.", "",
              "The current Nasdaq directory and SEC submissions metadata were fetched on 17 October. Cached revenue facts were retained when the current financial accession was already represented; "
              "otherwise fresh Company Facts were downloaded into the isolated research cache. Fresh facts can still omit custom tags or the newest earnings-release figures. "
              "Conservative exceptions are listed above. The screen does not parse every exhibit or independently review organic growth for every company.", "",
              "- [SEC Company Facts and submissions API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)",
              "- [Nasdaq screener directory](https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true&limit=25000&offset=0)",
              "- Each selected ticker links to its current supported financial filing. The JSON includes Company Facts and submissions URLs plus verification timestamps.",
              "- [Full evidence and proposed metadata](candidates.json) · [Spreadsheet with all six growth observations](candidates.csv)", "",
              "Reproduce the research with `scripts/screen_revenue_expansion.py`, `scripts/verify_revenue_expansion.py`, and `scripts/report_revenue_expansion.py`. "
              "Raw source responses remain under `.cache/revenue-expansion-2026-10-17/`; none of these scripts activates stocks or writes the application database.", ""]
    (OUTPUT / "shortlist.md").write_text("\n".join(lines))
    print(json.dumps(stats, indent=2))
    print("Selected:", ", ".join(r["symbol"] for r in selected))


if __name__ == "__main__":
    main()
