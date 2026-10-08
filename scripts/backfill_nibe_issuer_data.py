"""Extend durable NIBE issuer facts, then collect the symbol into SQLite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.entry_engine.providers.nibe_reports import merge_nibe_facts, parse_nibe_report
from app.entry_engine.providers.open_data_provider import OpenDataProvider
from app.services.open_data_stock_store import save_stock_snapshot_to_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Import a downloaded report instead of fetching new reports.")
    parser.add_argument("--year", type=int)
    parser.add_argument("--quarter", type=int, choices=range(1, 5))
    parser.add_argument("--filed", help="Issuer publication date (YYYY-MM-DD).")
    parser.add_argument("--url", help="Original issuer report URL for provenance.")
    parser.add_argument("--facts-only", action="store_true", help="Update issuer facts without collecting the SQLite snapshot.")
    args = parser.parse_args()
    if args.pdf and not all((args.year, args.quarter, args.filed, args.url)):
        parser.error("--pdf requires --year, --quarter, --filed and --url")
    path = ROOT / "data" / "stocks" / "issuer_facts" / "NIBE-B.ST.json"
    facts = json.loads(path.read_text())
    provider = OpenDataProvider()
    if args.pdf:
        reports = [{"year": args.year, "quarter": args.quarter, "filed": args.filed, "url": args.url}]
    else:
        html = provider._get("https://www.nibegroup.com/report-archive", timeout=30).text
        reports = []
        for row in re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.S):
            link = re.search(r'<a href="([^"]+)" title="Report Q([1-4]) (\d{4})"', row)
            filed = re.search(r'mfn-archive-event-date[^>]*>([\d-]+)', row)
            if link and filed:
                reports.append({"url": link[1], "quarter": int(link[2]), "year": int(link[3]), "filed": filed[1]})
        if not reports:
            raise RuntimeError("NIBE report archive did not contain recognizable quarterly reports")
        latest_year = max(r["year"] for r in reports)
        reports = [r for r in reports if r["year"] >= 2024 and (r["quarter"] == 4 or r["year"] == latest_year)]
        known = {(r["year"], r["quarter"]) for r in facts["reports"]}
        reports = [r for r in reports if (r["year"], r["quarter"]) not in known]
    for report in sorted(reports, key=lambda r: r["filed"]):
        content = args.pdf.read_bytes() if args.pdf else provider._get(report["url"], timeout=30).content
        parsed = parse_nibe_report(content, **{k: report[k] for k in ("year", "quarter", "filed")}, url=report["url"])
        merge_nibe_facts(facts, parsed)
        facts["reports"] = [r for r in facts["reports"] if (r["year"], r["quarter"]) != (report["year"], report["quarter"])] + [report]
        print(f"Imported FY{report['year']} Q{report['quarter']} ({report['filed']})")
    facts["reports"].sort(key=lambda r: r["filed"])
    path.write_text(json.dumps(facts, indent=2) + "\n")
    if not args.facts_only:
        snapshot = provider.get_open_data_snapshot("NIBE-B.ST")
        save_stock_snapshot_to_db(get_settings(), snapshot)
        print("Saved NIBE-B.ST to data/invest_os.sqlite")


if __name__ == "__main__":
    main()
