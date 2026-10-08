from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from open_data_poc import _filter_incremental_sec_work_items, _latest_relevant_sec_filing

from app.entry_engine.open_data_models import OpenDataCompanyContext, OpenDataCompanyFiling, OpenDataSnapshot
from app.services.storage import connect, load_stock_sec_refresh_state, replace_stock_open_data_snapshot


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
            with connect(data_dir) as conn:
                state = load_stock_sec_refresh_state(conn, "TEST")
            self.assertIsNotNone(state)
            self.assertEqual(state["accession_number"], "quarterly")

if __name__ == "__main__":
    unittest.main()
