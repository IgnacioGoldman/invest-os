"""Verify discovery candidates against current listings and SEC filing metadata."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import requests

from screen_revenue_expansion import CACHE, RESEARCH, ROOT, summarize
from app.entry_engine.providers.open_data_provider import RequestPacer


def number(value):
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=RESEARCH / "cached-screen.json")
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    nasdaq = json.loads((RESEARCH / "nasdaq-screener.json").read_text())
    listings = {r["symbol"].replace("/", "-"): r for r in nasdaq["data"]["rows"]}
    user_agent = os.getenv("SEC_USER_AGENT", "Invest OS revenue research contact=local-invest-os@example.com")
    pacer = RequestPacer(0.55)
    verified_dir = RESEARCH / "verification"
    verified_dir.mkdir(parents=True, exist_ok=True)
    # Old cached quarters are a reason to refresh evidence, not reject a company.
    selected = [r for r in report["rows"] if r["passes_screen"] or r["screen_exclusions"] == [
        "latest revenue period older than 140 days or missing"]]
    output = []
    def verify_one(row):
        symbol, cik = row["symbol"], row["cik"]
        target = verified_dir / f"{symbol}.json"
        if target.exists():
            return json.loads(target.read_text())
        row = dict(row)
        session = requests.Session()
        session.headers["User-Agent"] = user_agent
        listing = listings.get(symbol)
        row["verification_exclusions"] = []
        row["verified_at"] = datetime.now(timezone.utc).isoformat()
        if not listing:
            row["verification_exclusions"].append("not in current Nasdaq screener listings")
        else:
            row["listing_metadata"] = listing
            row["sector"] = listing.get("sector")
            row["industry"] = listing.get("industry")
            row["country"] = listing.get("country")
            row["market_cap_usd"] = number(listing.get("marketCap"))
            row["price_usd"] = number(listing.get("lastsale"))
            if row["market_cap_usd"] is None or row["market_cap_usd"] < 500_000_000:
                row["verification_exclusions"].append("market cap below USD500m or unavailable")
            if row["price_usd"] is None or row["price_usd"] < 5:
                row["verification_exclusions"].append("price below USD5 or unavailable")
        if not row["verification_exclusions"]:
            try:
                metadata_url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
                metadata_path = verified_dir / f"CIK{cik:010d}-submissions.json"
                if metadata_path.exists():
                    metadata = json.loads(metadata_path.read_text())
                else:
                    pacer.wait()
                    response = session.get(metadata_url, timeout=25)
                    response.raise_for_status()
                    metadata = response.json()
                    metadata_path.write_text(json.dumps(metadata))
                row["sec_metadata_url"] = metadata_url
                row["sic"] = metadata.get("sic")
                row["sic_description"] = metadata.get("sicDescription")
                row["sec_exchanges"] = metadata.get("exchanges")
                if symbol not in metadata.get("tickers", []):
                    row["verification_exclusions"].append("ticker absent from current SEC issuer metadata")
                recent = metadata.get("filings", {}).get("recent", {})
                filings = [dict(zip(recent, values)) for values in zip(*recent.values())]
                financial = [f for f in filings if f["form"] in {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F"}]
                latest = financial[0] if financial else None
                row["latest_sec_financial_filing"] = latest
                if not latest:
                    row["verification_exclusions"].append("no supported current SEC financial filing")
                elif latest["accessionNumber"] not in row["revenue_accessions"]:
                    facts_path = verified_dir / f"sec_companyfacts_CIK{cik:010d}.json"
                    if not facts_path.exists():
                        pacer.wait()
                        response = session.get(row["source_url"], timeout=40)
                        response.raise_for_status()
                        facts_path.write_text(response.text)
                    updated = summarize(facts_path, {k: row[k] for k in ("symbol", "name", "cik", "exchange")})
                    row.update(updated)
                    row["facts_downloaded_during_verification"] = True
                    if latest["accessionNumber"] not in row["revenue_accessions"]:
                        row["verification_exclusions"].append("latest financial filing has no revenue facts in selected concepts")
                row["newer_earnings_filings"] = [f for f in filings if f["form"] == "8-K"
                    and "2.02" in f.get("items", "") and f["filingDate"] > (row["latest_revenue_filed"] or "")]
                if row["newer_earnings_filings"]:
                    row["verification_exclusions"].append("newer earnings 8-K needs report review before using older quarter")
                if latest:
                    row["filing_url"] = f"https://www.sec.gov/Archives/edgar/data/{cik}/{latest['accessionNumber'].replace('-', '')}/{latest['primaryDocument']}"
                    if latest.get("reportDate", "") > (row["latest_period_end"] or ""):
                        row["verification_exclusions"].append("latest filing report date newer than extracted revenue quarter")
            except Exception as exc:
                row["verification_exclusions"].append(f"SEC verification failed: {exc}")
        row["verified_eligible"] = row["passes_screen"] and not row["verification_exclusions"]
        target.write_text(json.dumps(row, indent=2) + "\n")
        session.close()
        return row
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, row in enumerate(executor.map(verify_one, selected)):
            output.append(row)
            if (i+1) % 10 == 0:
                print(f"Verified {i+1}/{len(selected)}; eligible {sum(r['verified_eligible'] for r in output)}", flush=True)
    output.sort(key=lambda r: (-r["growth_score"], -(r["minimum_growth_6q"] or 0), r["symbol"]))
    result = {"as_of": report["as_of"], "screened_issuers": report["screened_issuers"],
              "screen_eligible": len(selected), "verified_eligible": sum(r["verified_eligible"] for r in output), "rows": output}
    (RESEARCH / "verified-screen.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"}))
    for row in [r for r in output if r["verified_eligible"]][:150]:
        print(row["symbol"], round(row["latest_growth_yoy"], 1), round(row["median_growth_6q"], 1), row.get("sector"), row["flags"])


if __name__ == "__main__":
    main()
