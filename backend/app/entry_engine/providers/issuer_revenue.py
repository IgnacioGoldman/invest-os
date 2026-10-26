"""Durable, sourced quarterly revenue for issuers with sparse SEC XBRL history."""
from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from app.config import PROJECT_DIR

SUPPORTED_ISSUERS = {"AZN", "B", "NVS", "YPF"}


def revenue_fact(year: int, quarter: int, value_millions: float, filed: str, url: str) -> dict:
    if not math.isfinite(value_millions) or value_millions <= 0:
        raise ValueError("Reported quarterly revenue must be finite and positive")
    month = quarter * 3
    return {"val": value_millions * 1_000_000, "start": date(year, month - 2, 1).isoformat(),
            "end": date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
            "fy": year, "fp": f"Q{quarter}", "form": "ISSUER-QUARTER", "filed": filed, "source_url": url}


def parse_revenue_text(symbol: str, text: str, *, year: int, quarter: int, filed: str, url: str) -> list[dict]:
    text = text.replace("\u00a0", " ")
    if symbol == "NVS":
        header = re.search(rf"Q{quarter}\s+{year}\s+Q{quarter}\s+{year - 1}", text)
        if header is None:
            raise ValueError("Novartis quarterly comparison header was not recognized")
        table = text[header.start():header.start() + 1500]
        if "USD" not in table:
            raise ValueError("Novartis revenue currency was not verified")
        row = re.search(r"^Net sales(?: to third parties)?\s+(\d{1,3}[ ,]\d{3})\s+(\d{1,3}[ ,]\d{3})", table, re.M)
        if row:
            return [revenue_fact(y, quarter, float(re.sub(r"[ ,]", "", value)), filed, url)
                    for y, value in zip((year, year - 1), row.groups())]
    elif symbol == "B":
        if not re.search(r"United States\s+dollars|U\.S\. dollars|US\$", text):
            raise ValueError("Barrick revenue currency was not verified")
        table = re.search(r"Quarterly Information[^\n]*\n([^\n]+)\n([^\n]+)\nRevenues\s+([^\n]+)", text)
        if table:
            years = [int(y) for y in re.findall(r"20\d{2}", table[1])]
            quarters = [int(q) for q in re.findall(r"Q([1-4])", table[2])]
            if len(years) == 2 and len(quarters) == 8:
                years = [years[0]] * 4 + [years[1]] * 4
            values = [float(v.replace(",", "")) for v in table[3].split()]
            if len(years) == len(quarters) == len(values) == 8 and (years[0], quarters[0]) == (year, quarter):
                return [revenue_fact(y, q, value, filed, url) for y, q, value in zip(years, quarters, values)]
    elif symbol == "AZN":
        for page in text.split("\f"):
            if not re.search(rf"Condensed consolidated statement of comprehensive income:\s*Q{quarter}\s+{year}", page, re.I):
                continue
            row = re.search(r"^Total Revenue\s+([\d,]+)\s+([\d,]+)\s*$", page, re.M)
            if row and str(year - 1) in page and "$m" in page:
                return [revenue_fact(y, quarter, float(value.replace(",", "")), filed, url)
                        for y, value in zip((year, year - 1), row.groups())]
    elif symbol == "YPF":
        if "5.2 CONSOLIDATED INCOME STATEMENT" not in text:
            raise ValueError("YPF consolidated income statement was not recognized")
        table = text.split("5.2 CONSOLIDATED INCOME STATEMENT", 1)[-1]
        header = re.search(r"Income Statement([^\n]+)", table)
        row = re.search(r"^Revenues\s+([^\n]+)", table, re.M)
        if header and row and re.search(r"US\$ million", table[:1000]):
            periods = [(2000 + int(y), int(q)) for q, y in re.findall(r"([1-4])Q(\d{2})", header[1])[:3]]
            values = re.findall(r"(?<![\w.])[\d,]+(?![\w.%])", row[1])[:3]
            if len(periods) == len(values) == 3 and periods[0] == (year, quarter):
                return [revenue_fact(y, q, float(v.replace(",", "")), filed, url) for (y, q), v in zip(periods, values)]
    raise ValueError(f"{symbol}: comparable consolidated quarterly revenue table was not recognized")


class _StatementText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.row_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row_depth += 1
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(re.sub(r"\s+", " ", data))

    def handle_endtag(self, tag):
        if tag == "tr":
            self.row_depth = max(0, self.row_depth - 1)
        self.parts.append("\n" if tag == "tr" or (tag in {"p", "div"} and not self.row_depth) else " " if tag in {"p", "div", "td", "th"} else "")


def report_text(content: bytes) -> str:
    if content.startswith(b"%PDF"):
        text = "\f".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    else:
        parser = _StatementText()
        parser.feed(content.decode("utf-8", errors="replace"))
        text = "".join(parser.parts)
        # SEC tables split cells into paragraphs. Keep each table row together.
        text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_report(symbol: str, content: bytes, **metadata) -> list[dict]:
    return parse_revenue_text(symbol, report_text(content), **metadata)


def parse_operating_income_text(symbol: str, text: str, **metadata) -> list[dict]:
    """Read reported USD operating income from YPF's consolidated table only."""
    if symbol != 'YPF':
        raise ValueError('Operating-income report parsing is supported only for YPF')
    text = text.replace('\u00a0', ' ')
    revenues = parse_revenue_text(symbol, text, **metadata)
    table = text.split('5.2 CONSOLIDATED INCOME STATEMENT', 1)[-1].split('5.3 ', 1)[0]
    match = re.search(r'^Operating (?:income|profit)(?: / \(loss\))?\s+([^\n]+)', table, re.M)
    tokens = match[1].split()[:3] if match else []
    if len(tokens) != len(revenues) or any(not re.fullmatch(r'\(?-?[\d,]+(?:\.\d+)?\)?|-', token) for token in tokens):
        raise ValueError('YPF: reported consolidated operating-income row was not recognized')
    result = []
    for revenue, token in zip(revenues, tokens):
        value = 0.0 if token == '-' else float(token.strip('()').replace(',', '')) * (-1 if token.startswith('(') else 1)
        if not math.isfinite(value):
            raise ValueError('YPF: non-finite operating income')
        result.append({**revenue, 'val': value * 1_000_000})
    return result


def supplement_issuer_revenue(primary: dict, seed: dict) -> dict:
    result = deepcopy(primary)
    result.setdefault("facts", {}).setdefault("issuer", {}).update(deepcopy(seed["facts"]["issuer"]))
    return result


def load_issuer_revenue(symbol: str, *, root: Path = PROJECT_DIR) -> dict | None:
    if symbol not in SUPPORTED_ISSUERS:
        return None
    path = root / "data/stocks/issuer_facts" / f"{symbol}.json"
    seed = json.loads(path.read_text())
    for row in seed["facts"]["issuer"]["Revenues"]["units"]["USD"]:
        expected = revenue_fact(row["fy"], int(row["fp"][1:]), row["val"] / 1_000_000, row["filed"], row["source_url"])
        if row != expected or not row["source_url"].startswith("https://"):
            raise ValueError(f"{symbol}: invalid durable issuer revenue fact")
    for row in seed['facts']['issuer'].get('OperatingIncomeLoss', {}).get('units', {}).get('USD', []):
        expected = {**revenue_fact(row['fy'], int(row['fp'][1:]), 1, row['filed'], row['source_url']), 'val': row['val']}
        if row != expected or not math.isfinite(row['val']) or not row['source_url'].startswith('https://'):
            raise ValueError(f'{symbol}: invalid durable issuer operating-income fact')
    return seed


def issuer_revenue_check_due(symbol: str, seed: dict, *, as_of: date | None = None) -> bool:
    """Use persisted attempt dates so scheduled runners share the weekly backoff."""
    today = as_of or date.today()
    if symbol not in SUPPORTED_ISSUERS:
        return False
    checked_at = seed.get("last_report_check", {}).get("checked_on")
    try:
        if checked_at and today - date.fromisoformat(checked_at) < timedelta(days=7):
            return False
    except (TypeError, ValueError):
        pass
    rows = seed["facts"]["issuer"]["Revenues"]["units"]["USD"]
    latest = max(rows, key=lambda r: r["end"])
    year, quarter = latest["fy"] + (latest["fp"] == "Q4"), int(latest["fp"][1:]) % 4 + 1
    month = quarter * 3
    return today >= date(year, month, calendar.monthrange(year, month)[1]) + timedelta(days=20)


def refresh_issuer_revenue(provider: Any, symbol: str, seed: dict, *, as_of: date | None = None) -> tuple[dict, list[str]]:
    """Try one newer report weekly; retain verified facts on source outages."""
    today = as_of or date.today()
    cache_name = f"issuer_revenue_check_{symbol}.json"
    if not issuer_revenue_check_due(symbol, seed, as_of=today) or provider.cache.get(cache_name, timedelta(days=7)) is not None:
        return seed, seed.get("last_report_check", {}).get("notes", [])
    rows = seed["facts"]["issuer"]["Revenues"]["units"]["USD"]
    latest = max(rows, key=lambda r: r["end"])
    year, quarter = latest["fy"] + (latest["fp"] == "Q4"), int(latest["fp"][1:]) % 4 + 1
    provider.cache.set(cache_name, {"checked_at": datetime.now(timezone.utc).isoformat()})
    try:
        if symbol == "B":
            url = f"https://s25.q4cdn.com/322814910/files/doc_financial/quarterly_results/{year}/q{quarter}/Barrick_Q{quarter}_{year}_MD-A.pdf"
        elif symbol == "NVS":
            url = f"https://www.novartis.com/sites/novartis_com/files/q{quarter}-{year}-media-release-en.pdf"
        elif symbol == "AZN":
            archive = provider._get("https://www.astrazeneca.com/investor-relations/results-and-presentations.html", timeout=15).text
            urls = re.findall(r'href=["\']([^"\']+\.pdf)["\']', archive, re.I)
            url = next(u for u in urls if f"Q{quarter}-{year}-results-announcement".lower() in u.lower())
            if url.startswith("/"):
                url = "https://www.astrazeneca.com" + url
        else:
            # The earnings releases are public 6-K primary documents even when
            # their tables are not exposed in the Company Facts XBRL API.
            filings = provider._fetch_sec_submissions(904851)["filings"]["recent"]
            candidates = [i for i, form in enumerate(filings["form"]) if form == "6-K"
                          and filings["filingDate"][i] > latest["filed"]][:2]
            for i in candidates:
                accession = filings["accessionNumber"][i].replace("-", "")
                url = f"https://www.sec.gov/Archives/edgar/data/904851/{accession}/{filings['primaryDocument'][i]}"
                content = provider._get(url, timeout=15).content
                try:
                    imported = parse_report(symbol, content, year=year, quarter=quarter,
                                            filed=filings["filingDate"][i], url=url)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("No newer recognizable YPF earnings release found")
        if symbol != "YPF":
            content = provider._get(url, timeout=15).content
            imported = parse_report(symbol, content, year=year, quarter=quarter, filed=today.isoformat(), url=url)
        updated = deepcopy(seed)
        by_period = {(r["start"], r["end"]): r for r in rows}
        by_period.update({(r["start"], r["end"]): r for r in imported})
        updated["facts"]["issuer"]["Revenues"]["units"]["USD"] = sorted(by_period.values(), key=lambda r: r["end"])
        notes = []
        if symbol == 'YPF':
            try:
                operating = parse_operating_income_text(symbol, report_text(content), year=year, quarter=quarter,
                                                      filed=filings['filingDate'][i], url=url)
                stored = updated['facts']['issuer'].setdefault('OperatingIncomeLoss', {'units': {'USD': []}})['units']['USD']
                by_period = {(r['start'], r['end']): r for r in stored}
                by_period.update({(r['start'], r['end']): r for r in operating})
                updated['facts']['issuer']['OperatingIncomeLoss']['units']['USD'] = sorted(by_period.values(), key=lambda r: r['end'])
            except ValueError as exc:
                notes.append(f'YPF: retained operating-income history; newer consolidated row unavailable: {exc}')
        updated["verified_on"] = today.isoformat()
        updated["last_report_check"] = {"checked_on": today.isoformat(), "status": "updated"}
    except Exception as exc:
        updated = deepcopy(seed)
        notes = [f"{symbol}: newer issuer revenue report unavailable; retained verified quarterly history: {exc}"]
        updated["last_report_check"] = {"checked_on": today.isoformat(), "status": "retained_unverified", "notes": notes}
    path = PROJECT_DIR / "data/stocks/issuer_facts" / f"{symbol}.json"
    path.write_text(json.dumps(updated, indent=2) + "\n")
    return updated, notes
