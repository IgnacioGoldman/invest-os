"""Apply reviewed house peer groups for the revenue-led 123-stock expansion."""
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    ("Technology", "Semiconductors"): "CRDO ALAB SITM MTSI MPWR AMBA",
    ("Technology", "Software"): "RBRK SNPS NET ZETA SHOP SNOW IOT KVYO BRZE FROG ZS MDB AVPT TOST GTLB TEAM CRWD PDFS NOW S",
    ("Technology", "Cloud Infrastructure"): "CRWV",
    ("Technology", "Industrial Lasers"): "LASR",
    ("Technology", "Geospatial Data"): "PL",
    ("Technology", "Communications Equipment"): "LITE AAOI VIAV UI",
    ("Technology", "Electronic Components"): "APH",
    ("Technology", "Electronics Manufacturing"): "CLS FN",
    ("Technology", "IT Services"): "FA",
    ("Healthcare", "Biopharmaceuticals"): "TGTX TARS ARQT INSM TVTX AXSM RYTM MIRM HALO ANIP LGND NBIX KRYS AUPH",
    ("Healthcare", "Medical Devices"): "GKOS ESTA TMDX PODD PRCT IRTC AXGN",
    ("Healthcare", "Diagnostics & Genomics"): "TEM GH NTRA ADPT WGS",
    ("Healthcare", "Managed Healthcare"): "ALHC OSCR",
    ("Healthcare", "Healthcare Services"): "ASTH",
    ("Materials", "Precious Metals Mining"): "CDE SSRM",
    ("Materials", "Precious Metals Royalties"): "RGLD",
    ("Materials", "Specialty Chemicals"): "PRM",
    ("Communication Services", "Internet Platforms"): "RDDT LIF GRND",
    ("Communication Services", "Interactive Entertainment"): "RBLX",
    ("Communication Services", "Broadcasting"): "EVC",
    ("Consumer Cyclical", "Auto Retail"): "CVNA",
    ("Consumer Cyclical", "Local Delivery Platforms"): "DASH",
    ("Consumer Cyclical", "Digital Education"): "DUOL",
    ("Consumer Cyclical", "Restaurants"): "BROS CAVA",
    ("Consumer Cyclical", "General Merchandise Retail"): "FIVE",
    ("Consumer Cyclical", "Online Gaming"): "RSI",
    ("Consumer Defensive", "Tobacco"): "TPB",
    ("Financials", "Property & Casualty Insurance"): "PLMR LMND",
    ("Financials", "Insurance Brokers"): "BRO AJG",
    ("Financials", "Consumer Lending"): "DAVE",
    ("Financials", "Brokerage & Market Making"): "LPLA HOOD VIRT",
    ("Financials", "Investment Managers"): "ARES",
    ("Financials", "Investment Banking"): "EVR",
    ("Financials", "Payment Processing"): "FOUR PAY FLYW RELY",
    ("Real Estate", "Healthcare REITs"): "CTRE VTR",
    ("Real Estate", "Net Lease REITs"): "EPRT NTST",
    ("Real Estate", "Real Estate Brokerage"): "COMP",
    ("Industrials", "Engineering & Construction"): "ROAD FIX ECG DY",
    ("Industrials", "Aerospace & Defense"): "FTAI RKLB VSEC LOAR KTOS",
    ("Industrials", "Public Safety Equipment"): "AXON",
    ("Industrials", "Electrical Equipment"): "NVT AMSC AEIS",
    ("Industrials", "Power Equipment & Services"): "SEI",
    ("Industrials", "Industrial Sensors"): "OUST",
    ("Industrials", "Warehouse Automation"): "SYM",
    ("Industrials", "Manufacturing Marketplaces"): "XMTR",
    ("Energy", "Oil & Gas Exploration & Production"): "BKV",
    ("Energy", "Oil & Gas Midstream"): "OKE DTM",
    ("Utilities", "Residential Solar Services"): "RUN",
}


def main():
    manifest = json.loads((ROOT / "docs/research/revenue-expansion-2026-10-17/candidates.json").read_text())
    expected = set(manifest["tickers"])
    assignments = {}
    for (sector, industry), symbols in GROUPS.items():
        for symbol in symbols.split():
            assert symbol not in assignments, symbol
            assignments[symbol] = (sector, industry)
    assert set(assignments) == expected, (set(assignments) - expected, expected - set(assignments))
    with sqlite3.connect(f"file:{ROOT / 'data/invest_os.sqlite'}?mode=ro", uri=True) as conn:
        snapshots = {ticker: json.loads(payload) for ticker, payload in conn.execute("SELECT ticker,payload FROM stock_open_data_snapshots")}
    path = ROOT / "data/stocks/industry-classifications.json"
    data = json.loads(path.read_text())
    source_rows = {r["symbol"]: r for r in manifest["rows"]}
    for symbol, (sector, industry) in assignments.items():
        snapshot = snapshots[symbol]
        data["stocks"][symbol] = {
            "sector": sector, "industry": industry,
            "original_sector": snapshot["sector"], "original_industry": snapshot["industry"],
            "original_classification_source": "Nasdaq screener directory, checked 2026-10-17",
            "market": "US", "currency": "USD",
            "reviewed_at": "2026-10-17",
            "sources": [source_rows[symbol]["research"]["filing_url"]],
        }
    data["reviewed_at"] = "2026-10-17"
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Reviewed {len(assignments)} new classifications; {len(data['stocks'])} total stocks. Existing groups preserved.")


if __name__ == "__main__":
    main()
