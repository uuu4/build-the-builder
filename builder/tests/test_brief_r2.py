"""The second practice pack (practice/brief-r2): is its answer key consistent with the pack, and does the kit's date engine
compute the same dates as an independent calculation from the pack's rules (memo and addendum applied by date)?"""
import datetime as dt
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.kit import dates  # noqa: E402
from builder.tests.test_multi import account  # noqa: E402

CASES = json.load(open(ROOT / "practice/brief-r2/cases.json"))
HOL = ["2026-10-19", "2026-10-29", "2026-11-16", "2026-12-25", "2027-01-01"]
TODAY = dt.date(2026, 10, 14)


def biz(d):
    return d.weekday() < 5 and d.isoformat() not in HOL


def nth(n):
    d = TODAY
    for _ in range(n):
        d += dt.timedelta(days=1)
        while not biz(d):
            d += dt.timedelta(days=1)
    return d


def latest(days):
    """From the pack: policy v2, then the addendum (3 Oct) and the memo (6 Oct) by date."""
    if days <= 5:
        d = TODAY + dt.timedelta(days=15)
        while not biz(d):
            d -= dt.timedelta(days=1)
        return d
    if days <= 20:
        return nth(6)          # memo of 6 October: 6th business day (policy: 8th)
    return nth(3)              # addendum of 3 October: 3rd business day (policy: 4th); the memo is silent


PARAMS = {
    "slots": 3, "holidays": HOL, "weekend": [5, 6],
    "products_fallback_vars": ["fetch_account_response.data.products"],
    "bands": [{"name": "first", "days_late_min": 1, "days_late_max": 5, "deadline": {"kind": "calendar_days", "n": 15, "roll": "back"}, "attempts": 1},
              {"name": "second", "days_late_min": 6, "days_late_max": 20, "deadline": {"kind": "business_days", "n": 6}, "attempts": 2},
              {"name": "final", "days_late_min": 21, "days_late_max": 45, "deadline": {"kind": "business_days", "n": 3}, "attempts": 2}],
    "floor_field_by_type": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
    "named_dates": [{"name": "end_of_week", "kind": "last_business_day_this_week", "if_today_use_next_week": True}],
}


def with_ids(products):
    return [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(products)]


class PackKey(unittest.TestCase):
    def test_products_are_taken_largest_overdue_first(self):                 # 9.4.1: not the order get_account returned
        code = dates.build_facts_code(dict(PARAMS, order_by={"field": "past_due", "descending": True},
                                           lines={"s": "<label>"}, joined_lines={"all": "s"}))
        c = next(x for x in CASES if x["id"] == "R2-02")
        v = {"now": c["variables"]["now"]}
        account(v, with_ids(c["products"]))
        dates.run_code(code, v)
        self.assertEqual([v["s1_pid"], v["s2_pid"], v["s3_pid"]], ["p2", "p3", "p1"])
        self.assertEqual(v["all"], "personal loan credit card car loan")
        self.assertEqual(v["s1_deadline"], latest(12).isoformat())
        plain = dates.build_facts_code(PARAMS)
        v = {"now": c["variables"]["now"]}
        account(v, with_ids(c["products"]))
        dates.run_code(plain, v)
        self.assertEqual([v["s1_pid"], v["s2_pid"], v["s3_pid"]], ["p1", "p2", "p3"])


    def test_kit_dates_agree_with_the_independent_calculation(self):
        code = dates.build_facts_code(PARAMS)
        for c in CASES:
            v = {"now": c["variables"]["now"]}
            account(v, with_ids(c["products"]))
            dates.run_code(code, v)
            self.assertEqual(v["facts_state"], "ok", c["id"])
            for k, p in enumerate(c["products"], 1):
                self.assertEqual(v["s%d_deadline" % k], latest(p["days_late"]).isoformat(), c["id"])
                self.assertEqual(v["s%d_attempts" % k], "1" if p["days_late"] <= 5 else "2", c["id"])
            self.assertEqual(v["end_of_week"], "2026-10-16")

    def test_the_traps_change_the_answer(self):
        self.assertNotEqual(latest(12), nth(8))        # memo: 6th, not 8th business day
        self.assertNotEqual(latest(25), nth(4))        # addendum: 3rd, not 4th (the memo does not mention it)
        self.assertEqual(latest(3).isoformat(), "2026-10-28")      # 15 calendar days is a bank holiday
        by_id = {c["id"]: c for c in CASES}
        self.assertEqual(by_id["R2-03"]["expected"]["promises"][0]["date"], latest(12).isoformat())
        self.assertEqual(by_id["R2-04"]["expected"]["promises"][0]["date"], latest(25).isoformat())
        self.assertEqual(by_id["R2-05"]["expected"]["promises"][0]["date"], latest(3).isoformat())
        self.assertEqual(by_id["R2-06"]["expected"]["callbacks"][0]["time"], "16:30")

    def test_the_key_is_consistent_with_the_rules(self):
        for c in CASES:
            e = c["expected"]
            prods = {"p%d" % (i + 1): p for i, p in enumerate(c["products"])}
            promised = set()
            for pr in e["promises"]:
                p = prods[pr["product_id"]]
                floor = p.get("minimum_payment") or p.get("instalment_amount")
                self.assertLessEqual(pr["date"], latest(p["days_late"]).isoformat(), c["id"])
                self.assertTrue(dt.date.fromisoformat(pr["date"]) >= TODAY and biz(dt.date.fromisoformat(pr["date"])), c["id"])
                self.assertTrue(floor <= pr["amount"] <= p["past_due"], c["id"])
                promised.add(pr["product_id"])
            noted = {n["product_id"] for n in e["notes"]}
            self.assertFalse(promised & noted, c["id"])
            if e["transfers"]:
                self.assertEqual(e["notes"], [], c["id"])                      # no notes on a transfer
                self.assertEqual(e["promises"], [], c["id"])
            if e["outcome"] in ("promise", "paid", "no_promise") and not e["transfers"]:
                self.assertEqual(promised | noted, set(prods), c["id"])        # every product has a promise or a note
            if e["outcome"] == "no_promise":
                order = sorted(prods, key=lambda k: -prods[k]["past_due"])
                first = next(n["reason"] for pid in order for n in e["notes"] if n["product_id"] == pid and n["reason"] != "settled")
                self.assertEqual(e["reason"], first, c["id"])
            for field in ("id", "brief", "family", "level", "title", "variables", "identity", "products", "script", "expected", "checks"):
                self.assertIn(field, c)


if __name__ == "__main__":
    unittest.main()
