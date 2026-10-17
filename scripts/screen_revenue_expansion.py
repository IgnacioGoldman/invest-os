"""Research-only revenue screen. Never writes the universe, snapshots, or database."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.entry_engine.open_data_metrics import REVENUE_CONCEPTS, _quarterly_revenue_rows, _source_statement_currencies
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum

AS_OF = date(2026, 10, 17)
CACHE = ROOT / ".cache/open_data"
RESEARCH = ROOT / ".cache/revenue-expansion-2026-10-17"


def summarize(path: Path, listing: dict) -> dict:
    payload = json.loads(path.read_text())
    payload["cik"] = int(payload["cik"])
    # Keep the fiscal-calendar anchors used by the production normalizer.
    keep = set(REVENUE_CONCEPTS) | {"NetIncomeLoss", "ProfitLoss"}
    facts = {namespace: {key: value for key, value in concepts.items() if key in keep}
             for namespace, concepts in payload.get("facts", {}).items()}
    small = {"cik": payload["cik"], "entityName": payload.get("entityName"), "facts": facts}
    quarters = [row.model_dump(mode="json") for row in _quarterly_revenue_rows(small, AS_OF.isoformat())]
    quarters = [row for row in quarters if row["as_of"] <= AS_OF.isoformat()]
    momentum = calculate_revenue_growth_momentum({"historical_series": {"quarterly_revenue": quarters}})
    last = quarters[-1] if quarters else None
    points = momentum["points"]
    growth = [p["value"] for p in points]
    latest = last["metrics"]["revenue_growth_yoy"]["value"] if last else None
    revenue_points = [r for ns in facts.values() for concept, data in ns.items() if concept in REVENUE_CONCEPTS
                      for unit_rows in data.get("units", {}).values() for r in unit_rows]
    filings = sorted({r.get("accn") for r in revenue_points if r.get("accn")})
    row = {
        **listing, "name": payload.get("entityName") or listing["name"],
        "facts_cache_file": str(path.relative_to(ROOT)),
        "facts_cache_modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "latest_revenue_filed": max((r.get("filed", "") for r in revenue_points), default=None),
        "revenue_accessions": filings,
        "latest_period": last["period"] if last else None,
        "latest_period_end": last["as_of"] if last else None,
        "latest_growth_yoy": latest,
        "latest_quarter_revenue": last["metrics"]["revenue"]["value"] if last else None,
        "median_growth_6q": median(growth) if growth else None,
        "recent_median_growth_3q": momentum["recentMedian"],
        "prior_median_growth_3q": momentum["priorMedian"],
        "momentum": momentum["label"], "momentum_pp": momentum["change"],
        "solid_quarters_6q": sum(g >= 8 for g in growth),
        "positive_quarters_6q": sum(g > 0 for g in growth),
        "minimum_growth_6q": min(growth) if growth else None,
        "quarters": quarters[-10:], "momentum_reason": momentum["reason"],
        "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{payload['cik']:010d}.json",
    }
    currencies = set().union(*(_source_statement_currencies(r["metrics"]["revenue"]["source"]) for r in quarters[-10:]))
    row["reporting_currency"] = next(iter(currencies)) if len(currencies) == 1 else None
    reasons = []
    if len(currencies) != 1:
        reasons.append("revenue reporting currency missing or inconsistent")
    if not last or (AS_OF - date.fromisoformat(last["as_of"])).days > 140:
        reasons.append("latest revenue period older than 140 days or missing")
    if len(growth) != 6:
        reasons.append("six consecutive comparable YoY quarters unavailable")
    if latest is None or latest < 8:
        reasons.append("latest quarter below 8%")
    if growth and (any(g < 8 for g in growth[-3:]) or median(growth) < 8 or sum(g > 0 for g in growth) < 5):
        reasons.append("growth persistence below screen")
    if row["latest_quarter_revenue"] is None or (currencies == {"USD"} and row["latest_quarter_revenue"] < 25_000_000):
        reasons.append("quarterly revenue missing or below USD25m")
    flags = []
    if growth and max(growth) >= 100:
        flags.append("100%+ quarter: review acquisitions, base effects and revenue definition")
    if growth and max(growth) - min(growth) >= 50:
        flags.append("six-quarter growth range exceeds 50pp")
    if momentum["label"] == "Decelerating":
        flags.append("growth decelerating versus prior three-quarter median")
    if last:
        sources = last["metrics"]["revenue"]["source"]
        row["revenue_source"] = sources
        if "derived" in last["metrics"]["revenue"]["notes"].lower():
            flags.append("latest quarter derived from annual/YTD revenue")
    row["flags"] = flags
    row["screen_exclusions"] = reasons
    row["passes_screen"] = not reasons
    # Rank sustainable growth; cap rates to prevent tiny-base outliers dominating.
    row["growth_score"] = round(
        0.6 * min(max(row["median_growth_6q"] or 0, 0), 50) / 50 * 100
        + 0.3 * min(max(min(growth[-3:]) if growth else 0, 0), 50) / 50 * 100
        + 10 * row["solid_quarters_6q"] / 6, 4)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESEARCH / "cached-screen.json")
    parser.add_argument("--base-universe", type=Path, default=ROOT / "docs/research/revenue-expansion-2026-10-17/base-universe.json")
    args = parser.parse_args()
    base = args.base_universe if args.base_universe.exists() else ROOT / "data/stocks/stocks.json"
    existing = json.loads(base.read_text())["rows"]
    existing_symbols = {r["symbol"] for r in existing}
    existing_ciks = {r.get("cik") for r in existing if r.get("cik")}
    mapping = json.loads((CACHE / "sec_company_tickers_exchange.json").read_text())
    listings = {}
    for values in mapping["data"]:
        r = dict(zip(mapping["fields"], values))
        cik, symbol = r["cik"], r["ticker"]
        if cik in existing_ciks or symbol in existing_symbols or r["exchange"] not in {"NYSE", "Nasdaq"}:
            continue
        if "-" in symbol or "." in symbol or len(symbol) > 5 or (len(symbol) == 5 and symbol.endswith(("W", "R", "U"))):
            continue
        if cik not in listings or len(symbol) < len(listings[cik]["symbol"]):
            listings[cik] = {"cik": cik, "symbol": symbol, "name": r["name"], "exchange": r["exchange"]}
    output, failures = [], []
    files = sorted(CACHE.glob("sec_companyfacts_CIK*.json"))
    for i, path in enumerate(files):
        cik = int(path.stem.split("CIK")[1])
        if cik not in listings:
            continue
        try:
            output.append(summarize(path, listings[cik]))
        except Exception as exc:
            failures.append({"cik": cik, "error": str(exc)})
        if (i + 1) % 100 == 0:
            print(f"Scanned {i+1}/{len(files)} files; eligible {sum(r['passes_screen'] for r in output)}", flush=True)
    output.sort(key=lambda r: (-r["growth_score"], r["symbol"]))
    report = {"as_of": AS_OF.isoformat(), "existing_symbol_count": len(existing_symbols),
              "cached_facts_count": len(files), "screened_issuers": len(output),
              "eligible_count": sum(r["passes_screen"] for r in output),
              "exclusion_counts": dict(Counter(reason for r in output for reason in r["screen_exclusions"])),
              "failures": failures, "rows": output}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    for r in [r for r in output if r["passes_screen"]][:150]:
        print(f"{r['symbol']:6} {r['latest_growth_yoy']:7.1f}% median6 {r['median_growth_6q']:6.1f}% {r['solid_quarters_6q']}/6 {r['latest_period_end']} {r['name']}")


if __name__ == "__main__":
    main()
