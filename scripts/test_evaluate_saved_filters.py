from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from evaluate_saved_filters import evaluate, expression_matches, signal_for


class FakeSupabase:
    def __init__(self) -> None:
        self.profiles = [{"user_id": "user-1"}]
        self.saved_filters: list[dict] = []
        self.watchlist = [{"user_id": "user-1", "ticker": "TEST"}]
        self.evaluations: list[dict] = []
        self.states: list[dict] = []
        self.events: list[dict] = []

    def request(self, method, table, params=None, payload=None, prefer=None):
        if method == "GET":
            return {
                "user_profiles": self.profiles,
                "watchlist_items": self.watchlist,
                "saved_filters": self.saved_filters,
                "filter_evaluations": self.evaluations,
                "filter_match_state": self.states,
            }[table]
        if method == "PATCH":
            for row in self.states:
                if all(str(row[key]) == value.removeprefix("eq.") for key, value in (params or {}).items()):
                    row.update(payload)
            return None
        rows = payload if isinstance(payload, list) else [payload]
        target = {
            "filter_evaluations": self.evaluations,
            "filter_match_state": self.states,
            "filter_match_events": self.events,
        }[table]
        key_fields = {
            "filter_evaluations": ("user_id", "filter_key"),
            "filter_match_state": ("user_id", "filter_key", "ticker"),
            "filter_match_events": ("user_id", "filter_key", "ticker", "matched_on"),
        }[table]
        for row in rows:
            existing = next((item for item in target if all(item.get(key) == row.get(key) for key in key_fields)), None)
            if existing:
                existing.update(row)
            else:
                target.append(dict(row))
        return None


from test_screening_metrics import ordinary
from app.services.screening_metrics import build_screening_metrics
from test_screening_metrics import TODAY
from unittest.mock import patch


def snapshot(ticker="TEST", revenue=12, short=1, long=30):
    row=ordinary(revenue); row["ticker"]=ticker
    def support(value):
        midpoint=100/(1+value/100) if value is not None else 100
        return {"value":value,"source":"yfinance_history","tier":"computed_from_public_facts","as_of":TODAY.isoformat(),
                "notes":f"Support zone: ${midpoint*.975:.8f}-${midpoint*1.025:.8f}; midpoint ${midpoint}"}
    row["price_opportunity"].update(support_1m_distance=support(short),support_5y_distance=support(long))
    row["screening"]=build_screening_metrics(row,TODAY)
    return row


RESEARCH_FILTER={"operator":"and","groups":[
    {"operator":"or","conditions":[{"field":"revenue","value":"Growing"},{"field":"revenue","value":"Growing"}]},
    {"operator":"or","conditions":[{"field":"support_1m","value":"Inside Support Zone"},{"field":"support_5y","value":"Near Support"}]},
]}


class FrozenDatetime(datetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2026,10,24,12,tzinfo=timezone.utc)


class SavedFilterEvaluatorTests(unittest.TestCase):
    def setUp(self):
        clock=patch('evaluate_saved_filters.datetime',FrozenDatetime)
        clock.start();self.addCleanup(clock.stop)

    def test_retired_rules_fail_closed_even_inside_or(self):
        for field in ("eps","valuation","industry_strength","fcf_margin","forward_pe","balance_sheet"):
            row=snapshot()
            self.assertEqual(signal_for(row,field),"Needs Review")
            expression={"operator":"or","groups":[{"operator":"or","conditions":[
                {"field":field,"value":"Cheap"},{"field":"revenue","value":"Growing"}]}]}
            self.assertFalse(expression_matches(row,expression))

    def test_grouped_expression_requires_each_metric_and_accepts_any_status(self):
        self.assertTrue(expression_matches(snapshot(short=1),RESEARCH_FILTER))
        self.assertTrue(expression_matches(snapshot(revenue=25,short=15,long=4),RESEARCH_FILTER))
        self.assertFalse(expression_matches(snapshot(revenue=-5),RESEARCH_FILTER))
        self.assertFalse(expression_matches(snapshot(short=15,long=30),RESEARCH_FILTER))

    def test_missing_metrics_remain_unknown_and_do_not_create_positive_signals(self):
        row={"ticker":"MISSING"}
        for field in ("revenue","momentum","operating_margin","operating_margin_trend","upcoming_earnings","support_1m"):
            self.assertEqual(signal_for(row,field),"Unknown")
        self.assertFalse(expression_matches(row,RESEARCH_FILTER))

    def test_old_revenue_band_rules_require_explicit_editing(self):
        row=snapshot(revenue=25)
        for label in ('Strong','Solid','High Growth','Moderate Growth'):
            expression={"operator":"or","groups":[{"operator":"or","conditions":[{"field":"revenue","value":label},{"field":"revenue","value":"Growing"}]}]}
            self.assertFalse(expression_matches(row,expression))

    def test_support_boundaries_and_missing_data_are_neutral_context(self):
        for value,label in ((2.5,"Inside Support Zone"),(2.51,"Near Support"),(6,"Near Support"),(6.01,"Above Support"),(100,"Above Support"),(None,"Unknown"),(-1,"Inside Support Zone"),(-3,"Unknown")):
            self.assertEqual(signal_for(snapshot(short=value),"support_1m"),label)

    def test_bare_forward_multiple_never_generates_a_valuation_rating(self):
        for value in (5,18,25,50,None,-1,float("nan")):
            row=snapshot();row["valuation"]["forward_pe"]={"value":value}
            self.assertEqual(signal_for(row,"forward_pe"),"Needs Review")

    def test_first_run_is_quiet_then_new_match_creates_daily_badge(self):
        client=FakeSupabase();client.saved_filters=[{"id":"research","user_id":"user-1","expression":RESEARCH_FILTER}]
        self.assertEqual(evaluate([snapshot(short=15)],client),(1,0))
        self.assertEqual(evaluate([snapshot(short=1)],client),(1,1))
        self.assertEqual(client.events[0]["filter_key"],"saved:research")
        self.assertEqual(evaluate([snapshot(short=1)],client),(1,0))

    def test_badges_are_scoped_to_filter_owner(self):
        client=FakeSupabase();client.profiles.append({"user_id":"user-2"});client.watchlist.append({"user_id":"user-2","ticker":"TEST"})
        client.saved_filters=[{"id":"research","user_id":"user-1","expression":RESEARCH_FILTER}]
        self.assertEqual(evaluate([snapshot(short=15)],client),(1,0))
        self.assertEqual(evaluate([snapshot(short=1)],client),(1,1))
        self.assertTrue(all(row["user_id"]=="user-1" for row in client.events+client.evaluations))

    def test_retired_filter_deactivates_matches_without_new_events(self):
        client=FakeSupabase();client.saved_filters=[{"id":"old","user_id":"user-1","expression":{"groups":[{"conditions":[{"field":"eps","value":"Strong"}]}]}}]
        client.states=[{"user_id":"user-1","filter_key":"saved:old","ticker":"TEST","active":True}]
        self.assertEqual(evaluate([snapshot()],client),(1,0))
        self.assertFalse(client.states[0]["active"])

    def test_empty_filters_preserve_all_stocks(self):
        self.assertTrue(expression_matches(snapshot(),{"groups":[]}))
        self.assertEqual(evaluate([snapshot()],FakeSupabase()),(0,0))

if __name__=="__main__":unittest.main()
