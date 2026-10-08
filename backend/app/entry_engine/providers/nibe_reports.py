"""Normalize NIBE's consolidated report tables; reject ambiguous column layouts."""
from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import date
from io import BytesIO
import re
from typing import Any

from pypdf import PdfReader


def _numbers(text: str) -> list[float]:
    text = re.sub(r"([-–−+])\s+(?=\d)", r"\1", text).replace("–", "-").replace("−", "-")
    tokens = text.split()
    if any(not re.fullmatch(r"[+-]?\d[\d,]*(?:\.\d+)?", token) for token in tokens):
        raise ValueError(f"Ambiguous NIBE numeric row: {text}")
    return [float(token.replace(",", "")) for token in tokens]


def _row(text: str, label: str) -> list[float] | None:
    match = re.search(rf"^{label}\s+([^\n]+)$", text, re.I | re.M)
    return _numbers(match[1]) if match else None


def parse_nibe_report(payload: bytes, *, year: int, quarter: int, filed: str, url: str) -> dict[str, Any]:
    # Plain text preserves digits in the redesigned 2026 PDFs. Layout mode is
    # needed only for the older income table's grouped year/quarter headers.
    reader = PdfReader(BytesIO(payload))
    pages = [page.extract_text() or "" for page in reader.pages]
    facts: dict[str, Any] = {}

    def add(concept: str, value: float, fy: int, q: int | None, *, instant: bool = False, eps: bool = False, ytd: bool = False) -> None:
        month = q * 3 if q else 12
        end = date(fy, month, calendar.monthrange(fy, month)[1])
        row = {
            "val": value if eps else value * 1_000_000,
            "end": end.isoformat(), "filed": filed, "source_url": url,
            "form": "ISSUER-QUARTER" if q else "ISSUER-ANNUAL",
            "fy": fy, "fp": f"Q{q}" if q else "FY",
        }
        if not instant:
            row["start"] = date(fy, (q - 1) * 3 + 1 if q and not ytd else 1, 1).isoformat()
        unit = "SEK/shares" if eps else "SEK"
        facts.setdefault(concept, {"units": {}})["units"].setdefault(unit, []).append(row)

    revenue_concept = "RevenueFromContractWithCustomerExcludingAssessedTax"
    quarterly_found = False
    for page_index, text in enumerate(pages):
        if "Quarterly data" in text:
            layout = reader.pages[page_index].extract_text(extraction_mode="layout") or ""
            layout = "\n".join(re.sub(r"\s+", " ", line).strip() for line in layout.splitlines())
            header = re.search(r"Consolidated income statement (.+)\n\(SEK million\) (.+)", layout)
            if not header:
                raise ValueError("NIBE quarterly table header was not recognized")
            years = [int(x) for x in re.findall(r"20\d{2}", header[1])]
            quarters = [int(x) for x in re.findall(r"Q([1-4])", header[2])]
            periods = []
            group = 0
            for index, q in enumerate(quarters):
                if index and q <= quarters[index - 1]:
                    group += 1
                if group >= len(years):
                    raise ValueError("NIBE quarter/year headers do not align")
                periods.append((years[group], q))
            if len(periods) != 9:
                raise ValueError("Expected nine NIBE quarterly columns")
            for label, concept in (("Net sales", revenue_concept), ("Operating profit", "OperatingIncomeLoss"), ("Net profit", "NetIncomeLoss")):
                values = _row(layout, label)
                if values is None or len(values) != len(periods):
                    raise ValueError(f"NIBE {label} columns do not align")
                for (fy, q), value in zip(periods, values):
                    add(concept, value, fy, q)
            quarterly_found = True
        elif "LAST NINE QUARTERS" in text and "NET SALES" in text:
            header = text.split("LAST NINE QUARTERS", 1)[1].split("NET SALES", 1)[0]
            periods = [(int(fy), int(q)) for q, fy in re.findall(r"Q([1-4])\s+(20\d{2})", header)]
            totals = re.findall(r"^GROUP TOTAL SEK m\s+([^\n]+)", text, re.M)
            if len(periods) != 9 or len(totals) < 2:
                raise ValueError("NIBE redesigned quarterly table was not recognized")
            # First two totals are reported revenue and operating profit. Later
            # totals contain adjusted results and must never replace GAAP facts.
            for concept, raw in zip((revenue_concept, "OperatingIncomeLoss"), totals[:2]):
                values = _numbers(raw)
                if len(values) != len(periods):
                    raise ValueError("NIBE quarterly totals do not align")
                for (fy, q), value in zip(periods, values):
                    add(concept, value, fy, q)
            quarterly_found = True

        if "Condensed income statement" in text:
            layout = reader.pages[page_index].extract_text(extraction_mode="layout") or ""
            layout = "\n".join(re.sub(r"\s+", " ", line).strip() for line in layout.splitlines())
            mappings = {
                "Net sales": revenue_concept, "Cost of goods sold": "CostOfRevenue",
                "Gross profit": "GrossProfit", "Operating profit": "OperatingIncomeLoss", "Net profit": "NetIncomeLoss",
                "Includes amortization/depreciation": "DepreciationAndAmortisationExpense",
                "Earnings per share before and after": "EarningsPerShareDiluted",
            }
            for label, concept in mappings.items():
                values = _row(layout, label)
                if values is None or len(values) != 6:
                    raise ValueError(f"NIBE condensed {label} layout was not recognized")
                for index, fy, q in ((0, year, quarter), (1, year - 1, quarter)):
                    add(concept, abs(values[index]) if concept == "CostOfRevenue" else values[index], fy, q, eps=concept == "EarningsPerShareDiluted")
                if quarter == 4:
                    for index, fy in ((2, year), (3, year - 1)):
                        add(concept, abs(values[index]) if concept == "CostOfRevenue" else values[index], fy, None, eps=concept == "EarningsPerShareDiluted")

        # The 2026 redesign separates consolidated and parent statements into
        # different pages. Parse only the first consolidated income page.
        elif "INCOME STATEMENT, SEK million" in text and not any("INCOME STATEMENT, SEK million" in p for p in pages[:page_index]):
            income = text.split("STATEMENT OF COMPREHENSIVE INCOME", 1)[0]
            mappings = {
                "Net sales": revenue_concept, "Cost of goods sold": "CostOfRevenue",
                "GROSS PROFIT": "GrossProfit", "OPERATING PROFIT": "OperatingIncomeLoss",
                "NET PROFIT": "NetIncomeLoss", "Includes depreciation/amortization as follows:": "DepreciationAndAmortisationExpense",
                "Earnings per share before and after dilution, SEK": "EarningsPerShareDiluted",
            }
            expected = 4 if quarter == 1 else 6
            for label, concept in mappings.items():
                values = _row(income, re.escape(label))
                if values is None or len(values) != expected:
                    raise ValueError(f"NIBE consolidated {label} columns do not align")
                for index, fy, q in ((0, year, quarter), (1, year - 1, quarter), (expected - 1, year - 1, None)):
                    add(concept, abs(values[index]) if concept == "CostOfRevenue" else values[index], fy, q, eps=concept == "EarningsPerShareDiluted")
                if quarter > 1:
                    for index, fy in ((2, year), (3, year - 1)):
                        add(concept, abs(values[index]) if concept == "CostOfRevenue" else values[index], fy, quarter, eps=concept == "EarningsPerShareDiluted", ytd=True)

        if "CASH FLOW STATEMENT, SEK million" in text and not any("CASH FLOW STATEMENT, SEK million" in p for p in pages[:page_index]):
            cashflow = text.split("CASH FLOW STATEMENT, SEK million", 1)[1]
            expected = 3 if quarter == 1 else 5
            for label, concept in (("CASH FLOW FROM OPERATING ACTIVITIES", "NetCashProvidedByUsedInOperatingActivities"), ("Investments in existing operations", "CapitalExpenditures")):
                values = _row(cashflow, label)
                if values is None or len(values) != expected:
                    raise ValueError(f"NIBE cash flow {label} columns do not align")
                for index, fy, q in ((0, year, quarter), (1, year - 1, quarter), (expected - 1, year - 1, None)):
                    add(concept, abs(values[index]) if concept == "CapitalExpenditures" else values[index], fy, q)
                if quarter > 1:
                    for index, fy in ((2, year), (3, year - 1)):
                        add(concept, abs(values[index]) if concept == "CapitalExpenditures" else values[index], fy, quarter, ytd=True)
            balance = text.split("CASH FLOW STATEMENT, SEK million", 1)[0]
            if "BALANCE SHEET, SEK million" in balance:
                for label, concept in (("Cash and cash equivalents", "CashAndCashEquivalentsAtCarryingValue"), ("Equity", "StockholdersEquity")):
                    values = _row(balance, label)
                    # Some Q1 PDF equity digits are separated by kerning. Keep
                    # the vendor fact rather than guessing how to join digits.
                    if values is not None and len(values) == 3:
                        for index, fy, q in ((0, year, quarter), (1, year - 1, quarter), (2, year - 1, None)):
                            add(concept, values[index], fy, q, instant=True)
                debt_rows = re.findall(r"^[–-] interest-bearing\s+([^\n]+)", balance, re.M)
                if len(debt_rows) == 2:
                    noncurrent, current = [_numbers(raw) for raw in debt_rows]
                    if len(noncurrent) == len(current) == 3:
                        for index, fy, q in ((0, year, quarter), (1, year - 1, quarter), (2, year - 1, None)):
                            add("DebtCurrent", noncurrent[index] + current[index], fy, q, instant=True)
    if not quarterly_found:
        raise ValueError("No consolidated NIBE quarterly history found")
    return {"entityName": "NIBE Industrier AB (publ)", "source": "issuer_financial_reports:NIBE", "facts": {"issuer": facts}}


def merge_nibe_facts(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Keep the newest report's value for each exact concept/unit/period."""
    issuer = target.setdefault("facts", {}).setdefault("issuer", {})
    for concept, data in incoming.get("facts", {}).get("issuer", {}).items():
        for unit, rows in data["units"].items():
            existing = issuer.setdefault(concept, {"units": {}})["units"].setdefault(unit, [])
            by_period = {(r.get("start"), r["end"]): r for r in existing}
            for row in rows:
                key = (row.get("start"), row["end"])
                if key not in by_period or row.get("filed", "") >= by_period[key].get("filed", ""):
                    by_period[key] = row
            issuer[concept]["units"][unit] = sorted(by_period.values(), key=lambda r: (r["end"], r.get("start", "")))


def discover_nibe_reports(html: str) -> list[dict[str, Any]]:
    reports = []
    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.S):
        link = re.search(r'<a href="([^"]+)" title="Report Q([1-4]) (\d{4})"', row)
        filed = re.search(r'mfn-archive-event-date[^>]*>([\d-]+)', row)
        if link and filed:
            reports.append({"url": link[1], "quarter": int(link[2]), "year": int(link[3]), "filed": filed[1]})
    if not reports:
        raise ValueError("NIBE report archive did not contain recognizable quarterly reports")
    latest_year = max(r["year"] for r in reports)
    return [r for r in reports if r["year"] >= 2024 and (r["quarter"] == 4 or r["year"] == latest_year)]


def refresh_nibe_reports(provider: Any, seed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Retain verified history if archive discovery or an individual PDF fails."""
    facts = deepcopy(seed)
    failures = []
    try:
        html = provider._get("https://www.nibegroup.com/report-archive", timeout=provider.request_timeout).text
        reports = discover_nibe_reports(html)
    except Exception as exc:
        return facts, [f"NIBE issuer archive refresh failed; retained verified history: {exc}"]
    known = {(r["year"], r["quarter"]) for r in facts.get("reports", [])}
    # Daily collection only checks the newest release. Filling older absent
    # reports belongs to the explicit local backfill command.
    reports = [max(reports, key=lambda r: (r["year"], r["quarter"]))]
    for report in sorted(reports, key=lambda r: r["filed"]):
        if (report["year"], report["quarter"]) in known:
            continue
        try:
            content = provider._get(report["url"], timeout=provider.request_timeout).content
            parsed = parse_nibe_report(content, **report)
        except Exception as exc:
            failures.append(f"NIBE FY{report['year']} Q{report['quarter']} could not be imported; retained verified history: {exc}")
            continue
        merge_nibe_facts(facts, parsed)
        facts.setdefault("reports", []).append(report)
    facts["reports"].sort(key=lambda r: r["filed"])
    return facts, failures
