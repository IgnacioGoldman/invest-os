from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.entry_engine.fiscal_periods import normalize_companyfacts_periods
from app.entry_engine.open_data_metrics import _quarterly_revenue_rows
from app.entry_engine.open_data_models import OpenDataPeriodMetrics, OpenDataSnapshot
from app.entry_engine.providers.issuer_revenue import issuer_revenue_check_due, load_issuer_revenue, parse_report, parse_revenue_text, refresh_issuer_revenue, revenue_fact
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
from app.services.stock_data_quality import retain_verified_history
from app.services.storage import connect, replace_stock_open_data_snapshot
from open_data_poc import _filter_incremental_sec_work_items
from refresh_static_prices import _merge_stock_rows


def fact(value, start, end, fy, fp, form="10-Q", filed="2026-08-01"):
    return dict(val=value, start=start, end=end, fy=fy, fp=fp, form=form, filed=filed)


def facts(rows):
    return {"facts":{"us-gaap":{"Revenues":{"units":{"USD":rows}}}}}


def nvs_revenue_seed():
    # Scheduled refreshes update the production seed's quarters and check date.
    # Scheduling and persistence tests need a fixed starting point.
    return {
        "verified_on": "2026-10-13",
        "facts": {"issuer": {"Revenues": {"units": {"USD": [
            revenue_fact(2026, 2, 14408, "2026-07-21", "https://issuer.example/q2-2026.pdf"),
        ]}}}},
    }


class RevenueHistoryRepairTests(unittest.TestCase):
    def test_comparative_filing_year_does_not_erase_prior_quarter(self):
        data = facts([
            fact(400,"2024-01-01","2024-12-31",2025,"FY","10-K"),
            fact(500,"2025-01-01","2025-12-31",2025,"FY","10-K"),
            fact(100,"2024-04-01","2024-06-30",2025,"Q2"),
            fact(120,"2025-04-01","2025-06-30",2025,"Q2"),
        ])
        original = deepcopy(data)
        rows = _quarterly_revenue_rows(data, "2026-10-13")
        self.assertEqual([r.period for r in rows],["FY2024 Q2","FY2025 Q2"])
        self.assertEqual(rows[-1].metrics["revenue_growth_yoy"].value,20)
        self.assertEqual(data,original)

    def test_noncalendar_q4_uses_annual_and_ytd_from_same_actual_year(self):
        rows = _quarterly_revenue_rows(facts([
            fact(400,"2024-02-01","2025-01-31",2025,"FY","10-K","2025-03-05"),
            fact(500,"2025-02-01","2026-01-31",2025,"FY","10-K","2026-03-02"),
            fact(270,"2024-02-01","2024-10-31",2025,"Q3"),
            fact(330,"2025-02-01","2025-10-31",2026,"Q3"),
        ]),"2026-10-13")
        self.assertEqual([(r.period,r.metrics["revenue"].value) for r in rows],[("FY2025 Q4",130),("FY2026 Q4",170)])

    def test_53_week_calendar_ignores_inconsistent_year_labels(self):
        data = facts([
            fact(6433,"2023-07-01","2024-06-28",2024,"FY","10-K","2024-08-01"),
            fact(9097,"2024-06-29","2025-06-27",2027,"FY","10-K","2025-08-01"),
            fact(12195,"2025-06-28","2026-07-03",2026,"FY","10-K","2026-08-04"),
            fact(6653,"2024-06-29","2025-03-28",2025,"Q3"),
            fact(8566,"2025-06-28","2026-04-03",2026,"Q3"),
        ])
        rows=_quarterly_revenue_rows(data,"2026-10-13")
        self.assertEqual([(r.period,r.metrics["revenue"].value) for r in rows],[("FY2025 Q4",2444),("FY2026 Q4",3629)])

    def test_annual_balance_facts_remain_annual(self):
        data=facts([fact(400,"2025-01-01","2025-12-31",2025,"FY","10-K")])
        data["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]={"units":{"USD":[fact(10,None,"2025-12-31",2026,"FY","10-K")]}}
        row=normalize_companyfacts_periods(data)["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"][0]
        self.assertEqual((row["fy"],row["fp"]),(2025,"FY"))

    def test_two_year_gap_never_becomes_yoy(self):
        rows=_quarterly_revenue_rows(facts([
            fact(100,"2024-06-01","2024-08-31",2025,"Q1"),
            fact(150,"2026-06-01","2026-08-31",2026,"Q1"),
        ]),"2026-10-13")
        self.assertIsNone(rows[-1].metrics["revenue_growth_yoy"].value)

    def test_wrong_label_is_not_restored_by_history_retention(self):
        current=OpenDataSnapshot(ticker="TEST",historical_series={"quarterly_revenue":[OpenDataPeriodMetrics(period="FY2027 Q1",as_of="2026-08-31")]})
        old=OpenDataSnapshot(ticker="TEST",historical_series={"quarterly_revenue":[OpenDataPeriodMetrics(period="FY2026 Q1",as_of="2026-08-31")]})
        self.assertEqual([r.period for r in retain_verified_history(current,old).historical_series["quarterly_revenue"]],["FY2027 Q1"])

    def test_all_four_verified_issuer_histories_have_six_growth_rates(self):
        expected={"AZN":"Decelerating","NVS":"Decelerating","B":"Accelerating","YPF":"Accelerating"}
        for ticker,label in expected.items():
            with self.subTest(ticker=ticker):
                rows=_quarterly_revenue_rows(load_issuer_revenue(ticker),"2026-10-13")
                result=calculate_revenue_growth_momentum({"historical_series":{"quarterly_revenue":[r.model_dump(mode="json") for r in rows]}})
                self.assertEqual(len(rows),10)
                self.assertEqual(rows[-1].as_of,"2026-06-30")
                self.assertEqual(result["label"],label)
                self.assertEqual(len(result["points"]),6)
                self.assertTrue(all("https://" in r.metrics["revenue"].source for r in rows))

    def test_report_parsers_keep_reported_quarters_and_ignore_ytd(self):
        reports={
            "AZN":"Condensed consolidated statement of comprehensive income: Q2 2026\n2026 $m 2025 $m\nTotal Revenue 15,384 14,457\n",
            "NVS":"Q2 2026 Q2 2025 % change H1 2026 H1 2025\nUSD m USD m\nNet sales 14 408 14 054 3 1 27 521 27 287 1 -2\n",
            "B":"All amounts in United States dollars\nQuarterly Informationa\n($ millions) 2026 2026 2025 2025 2025 2025 2024 2024\nQ2 Q1 Q4 Q3 Q2 Q1 Q4 Q3\nRevenues 5,292 5,218 5,997 4,148 3,681 3,130 3,645 3,368\n",
        }
        for ticker,text in reports.items():
            rows=parse_revenue_text(ticker,text,year=2026,quarter=2,filed="2026-08-10",url="https://issuer.example/report.pdf")
            self.assertEqual(rows[0]["end"],"2026-06-30")
            self.assertEqual(rows[0]["val"],{"AZN":15384,"NVS":14408,"B":5292}[ticker]*1_000_000)
        html=b'<h2>5.2 CONSOLIDATED INCOME STATEMENT</h2><table><tr><td><p>Income Statement</p></td><td>2Q26</td><td>1Q26</td><td>2Q25</td></tr><tr><td>Unaudited Figures, in US$ million</td></tr><tr><td><p>Revenues</p></td><td><p>6,574</p></td><td>4,946</td><td>4,641</td><td>32.9%</td><td>41.7%</td><td>11,520</td></tr></table>'
        rows=parse_report("YPF",html,year=2026,quarter=2,filed="2026-08-10",url="https://www.sec.gov/report.htm")
        self.assertEqual([r["val"] for r in rows],[6574e6,4946e6,4641e6])

    def test_source_outage_keeps_verified_seed_and_records_weekly_check(self):
        seed=nvs_revenue_seed()
        cache=SimpleNamespace(get=Mock(return_value=None),set=Mock())
        provider=SimpleNamespace(cache=cache,_get=Mock(side_effect=ValueError("source unavailable")))
        with TemporaryDirectory() as directory, patch("app.entry_engine.providers.issuer_revenue.PROJECT_DIR", Path(directory)):
            path = Path(directory) / "data/stocks/issuer_facts/NVS.json"
            path.parent.mkdir(parents=True)
            result,notes=refresh_issuer_revenue(provider,"NVS",seed,as_of=date(2026,11,1))
            self.assertEqual(result["facts"],seed["facts"])
            self.assertEqual(result["verified_on"],seed["verified_on"])
            self.assertTrue(notes)
            cache.set.assert_called_once()
            # A new runner has no raw cache; persisted attempt metadata still backs off.
            persisted = load_issuer_revenue("NVS", root=Path(directory))
            refresh_issuer_revenue(provider,"NVS",persisted,as_of=date(2026,11,2))
            self.assertFalse(issuer_revenue_check_due("NVS",persisted,as_of=date(2026,11,7)))
            self.assertTrue(issuer_revenue_check_due("NVS",persisted,as_of=date(2026,11,8)))
        provider._get.assert_called_once()

    def test_issuer_discovery_waits_until_next_quarter_can_be_reported(self):
        seed = nvs_revenue_seed()
        self.assertFalse(issuer_revenue_check_due("NVS", seed, as_of=date(2026,10,19)))
        self.assertTrue(issuer_revenue_check_due("NVS", seed, as_of=date(2026,10,20)))

    def test_issuer_discovery_waits_seven_days_after_persisted_check(self):
        seed = nvs_revenue_seed()
        seed["last_report_check"] = {"checked_on": "2026-10-20", "status": "retained_unverified"}
        for day, expected in ((20, False), (21, False), (26, False), (27, True)):
            with self.subTest(day=day):
                self.assertEqual(issuer_revenue_check_due("NVS", seed, as_of=date(2026,10,day)), expected)

    def test_successful_issuer_discovery_persists_new_quarter_and_check_date(self):
        seed = nvs_revenue_seed()
        provider = SimpleNamespace(cache=SimpleNamespace(get=Mock(return_value=None),set=Mock()),
            _get=Mock(return_value=SimpleNamespace(content=b"<p>Q3 2026 Q3 2025</p><p>USD m USD m</p><p>Net sales 15 000 14 000</p>")))
        with TemporaryDirectory() as directory, patch("app.entry_engine.providers.issuer_revenue.PROJECT_DIR", Path(directory)):
            (Path(directory) / "data/stocks/issuer_facts").mkdir(parents=True)
            result, notes = refresh_issuer_revenue(provider,"NVS",seed,as_of=date(2026,11,1))
            self.assertFalse(notes)
            self.assertEqual(result["last_report_check"]["status"], "updated")
            self.assertEqual(result["verified_on"], "2026-11-01")
            rows = result["facts"]["issuer"]["Revenues"]["units"]["USD"]
            self.assertEqual(rows[-1]["end"], "2026-09-30")
            self.assertEqual(rows[-1]["val"], 15_000e6)
            self.assertEqual(load_issuer_revenue("NVS",root=Path(directory)), result)

    def test_price_refresh_cannot_restore_older_deployed_revenue_history(self):
        deployed={"ticker":"AZN","revenue_history_version":0}
        repaired={"ticker":"AZN","revenue_history_version":1,"revenue_history_checked_at":"2026-10-13T12:00:00Z"}
        self.assertEqual(_merge_stock_rows([deployed],[repaired],["AZN"]),[repaired])
        newer={**repaired,"revenue_history_checked_at":"2026-10-14T12:00:00Z"}
        self.assertEqual(_merge_stock_rows([newer],[repaired],["AZN"]),[newer])

    def test_history_repairs_upgrade_once_and_back_off_for_seven_days(self):
        for version,age,expected in [(0,0,True),(1,0,False),(1,8,True)]:
            with self.subTest(version=version,age=age),TemporaryDirectory() as directory:
                data_dir=Path(directory)
                snapshot=OpenDataSnapshot(ticker="TEST",cik=123,revenue_history_version=version,
                    revenue_history_checked_at=datetime.now(timezone.utc)-timedelta(days=age))
                with connect(data_dir) as conn:
                    replace_stock_open_data_snapshot(conn,snapshot)
                    conn.commit()
                provider=SimpleNamespace(resolve_cik=lambda ticker:123,_fetch_sec_submissions=lambda cik:{})
                with patch("open_data_poc.get_settings",return_value=SimpleNamespace(data_dir=data_dir)):
                    collect,preserved=_filter_incremental_sec_work_items([(0,{"ticker":"TEST"})],provider,save=True,repair_revenue_history=True)
                self.assertEqual(bool(collect),expected)
                self.assertEqual(bool(preserved),not expected)


if __name__ == "__main__":
    unittest.main()
