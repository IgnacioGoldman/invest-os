from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from open_data_poc import _build_report, _collect_item_with_retries, _filter_incremental_sec_work_items, _latest_relevant_sec_filing, _record_collected_sec_state, _sec_submissions_verified

from app.entry_engine.open_data_models import OpenDataCompanyContext, OpenDataCompanyFiling, OpenDataPeriodMetrics, OpenDataSnapshot
from app.services.storage import connect, load_stock_sec_refresh_state, replace_stock_open_data_snapshot, replace_stock_sec_refresh_state


class FakeSettings:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir


class FakeProvider:
    def __init__(self, submissions: dict) -> None:
        self.submissions = submissions

    def resolve_cik(self, ticker: str) -> int:
        return 123

    def _fetch_sec_submissions(self, cik: int) -> dict:
        return self.submissions


class IncrementalSecRefreshTests(unittest.TestCase):
    def test_incomplete_metadata_is_not_counted_as_verified(self) -> None:
        for response in (None, {}, {"filings":{"recent":{"form":["10-Q"]}}},
                         {"filings":{"recent":{"form":["10-Q"],"filingDate":[],"accessionNumber":[]}}}):
            with self.subTest(response=response):
                self.assertFalse(_sec_submissions_verified(response))
        self.assertTrue(_sec_submissions_verified({"filings":{"recent":{"form":[],"filingDate":[],"accessionNumber":[]}}}))

    def test_recollection_after_unavailable_metadata_does_not_advance_sec_state(self) -> None:
        with patch("open_data_poc._save_sec_refresh_state") as save_state:
            _record_collected_sec_state({"ticker":"TEST","saved_to":"db","cik":123},
                                       {"sec_check_status":"unavailable"},incremental_sec=True,save=True)
        save_state.assert_not_called()

    def test_sec_outage_retains_snapshot_without_claiming_unchanged_or_overwriting_state(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="TEST", cik=123))
                replace_stock_sec_refresh_state(conn, ticker="TEST", cik=123, accession_number="known", filing_date="2026-09-15", form="10-Q")
                conn.commit()
            with patch("open_data_poc.get_settings", return_value=FakeSettings(data_dir)):
                collect, preserved = _filter_incremental_sec_work_items([(0, {"ticker": "TEST"})], FakeProvider(None), save=True)
            self.assertFalse(collect)
            self.assertEqual(preserved[0]["refresh_status"], "retained_unverified")
            self.assertEqual(preserved[0]["sec_check_status"], "unavailable")
            self.assertNotEqual(preserved[0]["skip_reason"], "sec_filings_unchanged")
            self.assertTrue(preserved[0]["source_notes"])
            with connect(data_dir) as conn:
                self.assertEqual(load_stock_sec_refresh_state(conn,"TEST")["accession_number"], "known")
            report = _build_report(mode="universe_file", requested_count=1, source="test", skip_tickers=set(),
                                   min_coverage=0, include_filing_details=False, results=preserved, skipped_low_fidelity=[], failures=[])
            self.assertEqual(report["retained_unverified_count"], 1)
            self.assertEqual(report["sec_unverified_count"], 1)
            self.assertEqual(report["verified_unchanged_count"], 0)
            self.assertEqual(report["failed_count"], 0)

    def test_supported_issuer_check_bypasses_generic_6k_gate_and_backs_off(self) -> None:
        submissions = {"filings": {"recent": {"form": ["6-K"], "filingDate": ["2026-07-21"],
                       "accessionNumber": ["0001114448-26-000012"], "primaryDocument": ["nvs-20260630.htm"],
                       "primaryDocDescription": ["6-K"]}}}
        self.assertIsNone(_latest_relevant_sec_filing(submissions))
        seed = {"facts": {"issuer": {"Revenues": {"units": {"USD": [{"end": "2026-06-30"}]}}}}}
        for due, expected in [(True, True), (False, False)]:
            with self.subTest(due=due), TemporaryDirectory() as directory:
                data_dir = Path(directory)
                with connect(data_dir) as conn:
                    replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="NVS", cik=123,
                        historical_series={"quarterly_revenue": [OpenDataPeriodMetrics(period="FY2026 Q2",as_of="2026-06-30")]}))
                    conn.commit()
                with (patch("open_data_poc.get_settings",return_value=FakeSettings(data_dir)),
                      patch("open_data_poc.load_issuer_revenue",return_value=seed),
                      patch("open_data_poc.issuer_revenue_check_due",return_value=due)):
                    collect, preserved = _filter_incremental_sec_work_items([(0,{"ticker":"NVS"})],FakeProvider(submissions),save=True)
                self.assertEqual(bool(collect),expected)
                self.assertEqual(bool(preserved),not expected)
                if due:
                    self.assertIn("issuer_report_check_due", collect[0][1]["repair_reasons"])
                    self.assertTrue(collect[0][1]["_issuer_check_only"])

    def test_newer_saved_issuer_report_is_retried_even_during_discovery_backoff(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="NVS",cik=123))
                conn.commit()
            seed = {"facts": {"issuer": {"Revenues": {"units": {"USD": [{"end":"2026-09-30"}]}}}}}
            with (patch("open_data_poc.get_settings",return_value=FakeSettings(data_dir)),
                  patch("open_data_poc.load_issuer_revenue",return_value=seed),
                  patch("open_data_poc.issuer_revenue_check_due",return_value=False)):
                collect, preserved = _filter_incremental_sec_work_items([(0,{"ticker":"NVS"})],FakeProvider({}),save=True)
            self.assertFalse(preserved)
            self.assertIn("issuer_report_data_changed",collect[0][1]["repair_reasons"])

    def test_optional_issuer_collection_outage_preserves_existing_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn,OpenDataSnapshot(ticker="NVS",cik=123))
                conn.commit()
            with (patch("open_data_poc.get_settings",return_value=FakeSettings(data_dir)),
                  patch("open_data_poc.OpenDataProvider") as provider):
                provider.return_value.get_open_data_snapshot.side_effect = RuntimeError("source offline")
                result = _collect_item_with_retries({"ticker":"NVS","_issuer_check_only":True,"sec_check_status":"verified"},
                    save=True,min_coverage=0,include_analysis=False,include_filing_details=False,max_sec_archive_lookups=None,
                    ticker_retries=1,request_timeout=1,request_retries=1,retry_backoff=0)
            self.assertEqual(result["collection_status"],"preserved")
            self.assertEqual(result["refresh_status"],"retained_unverified")
            self.assertTrue(result["source_notes"])

    def test_daily_refresh_does_not_recollect_for_history_only_gaps(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="TEST", cik=123))
                conn.commit()
            with patch("open_data_poc.get_settings", return_value=FakeSettings(data_dir)):
                collect, preserved = _filter_incremental_sec_work_items([(0, {"ticker": "TEST"})], FakeProvider({}), save=True, repair_current_data=True)
            self.assertFalse(collect)
            self.assertEqual(len(preserved), 1)

    def test_unchanged_filing_with_revenue_gap_is_recollected(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="TEST", cik=123))
                conn.commit()
            with patch("open_data_poc.get_settings", return_value=FakeSettings(data_dir)):
                collect, preserved = _filter_incremental_sec_work_items([(0, {"ticker": "TEST"})], FakeProvider({}), save=True, repair_data_gaps=True)
            self.assertFalse(preserved)
            self.assertIn("historical_series.latest_six_revenue_growth_quarters", collect[0][1]["repair_reasons"])

    def test_existing_non_sec_symbol_is_refreshed(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, OpenDataSnapshot(ticker="NIBE-B.ST", cik=None))
                conn.commit()
            provider = FakeProvider({})
            provider.resolve_cik = lambda ticker: (_ for _ in ()).throw(TypeError("No CIK"))
            with patch("open_data_poc.get_settings", return_value=FakeSettings(data_dir)):
                collect, preserved = _filter_incremental_sec_work_items([(0, {"ticker": "NIBE-B.ST"})], provider, save=True)
            self.assertEqual(len(collect), 1)
            self.assertFalse(preserved)
            self.assertEqual(collect[0][1]["sec_check_status"], "not_applicable")

    def test_latest_relevant_sec_filing_ignores_unrelated_newer_filings(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q", "8-K"],
                    "filingDate": ["2026-09-20", "2026-09-15", "2026-09-01"],
                    "accessionNumber": ["unrelated", "quarterly", "earnings"],
                    "items": ["8.01,9.01", "", "2.02,9.01"],
                    "primaryDocument": ["corp-update.htm", "q2-10q.htm", "q2-earnings.htm"],
                    "primaryDocDescription": ["Corporate Update", "10-Q", "Earnings Release"],
                }
            }
        }

        latest = _latest_relevant_sec_filing(submissions)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["accession_number"], "quarterly")

    def test_incremental_preflight_preserves_unchanged_existing_snapshot(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "filingDate": ["2026-09-15"],
                    "accessionNumber": ["quarterly"],
                    "items": [""],
                    "primaryDocument": ["q2-10q.htm"],
                    "primaryDocDescription": ["10-Q"],
                }
            }
        }
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            snapshot = OpenDataSnapshot(
                ticker="TEST",
                cik=123,
                company_context=OpenDataCompanyContext(
                    as_of="2026-09-15",
                    recent_filings=[
                        OpenDataCompanyFiling(
                            accession_number="quarterly",
                            form="10-Q",
                            filing_date="2026-09-15",
                            primary_document="q2-10q.htm",
                            primary_document_description="10-Q",
                        )
                    ],
                ),
            )
            with connect(data_dir) as conn:
                replace_stock_open_data_snapshot(conn, snapshot)
                conn.commit()

            with patch("open_data_poc.get_settings", return_value=FakeSettings(data_dir)):
                collect_items, preserved = _filter_incremental_sec_work_items(
                    [(0, {"ticker": "TEST"})],
                    FakeProvider(submissions),  # type: ignore[arg-type]
                    save=True,
                )

            self.assertEqual(collect_items, [])
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0]["collection_status"], "preserved")
            self.assertEqual(preserved[0]["refresh_status"], "verified_unchanged")
            with connect(data_dir) as conn:
                state = load_stock_sec_refresh_state(conn, "TEST")
            self.assertIsNotNone(state)
            self.assertEqual(state["accession_number"], "quarterly")

if __name__ == "__main__":
    unittest.main()
