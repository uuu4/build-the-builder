"""The customer's dates in the multi-product back half: said in words, resolved in code against the call's `now`.

The live run of 10 October showed the platform's `date` extraction resolving "today" and "tomorrow" against the real
clock (PUB-01 recorded 2026-10-10 instead of 2026-10-14; PUB-12 read back Sunday 11 October for "tomorrow" seven times),
and the "can you pay all of it today?" step agreeing every product when the customer spoke of one (PUB-12, PUB-13)."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.kit import multi  # noqa: E402
from builder.kit.pycode import run_locally, with_params  # noqa: E402
from builder.tests.test_multi import CARD, LOAN, CAR, account, holds, load_workflow, run  # noqa: E402

NOW = "2026-10-14T11:00"          # a Wednesday; Brief B holidays include 2026-10-26


def resolve(text, now=NOW, next_weekday="following_week", holidays="2026-10-26"):
    v = run_locally(with_params(multi._WHEN + "\nd = resolve_when(vars.get('q'))\nvars['out'] = '' if d is None else d.isoformat()\n",
                                {"next_weekday": next_weekday}),
                    {"q": text, "today": now[:10], "now": now, "holiday_list": holidays, "weekend_list": "5,6"})
    return v["out"]


def route(node, vars_):
    for tr in node["transitions"]:
        if holds(tr["condition"], vars_):
            return tr["target_node"]
    return None


class Resolve(unittest.TestCase):
    def test_relative_days_follow_the_calls_now_not_the_clock(self):
        self.assertEqual(resolve("today"), "2026-10-14")
        self.assertEqual(resolve("I can pay it tomorrow"), "2026-10-15")
        self.assertEqual(resolve("the day after tomorrow"), "2026-10-16")
        self.assertEqual(resolve("in 3 days"), "2026-10-17")
        self.assertEqual(resolve("tomorrow", now="2026-11-02T09:00"), "2026-11-03")

    def test_weekdays(self):
        self.assertEqual(resolve("Friday"), "2026-10-16")
        self.assertEqual(resolve("this Friday"), "2026-10-16")
        self.assertEqual(resolve("next Friday"), "2026-10-23")                  # the Friday of the following week
        self.assertEqual(resolve("next Friday", next_weekday="nearest"), "2026-10-16")
        self.assertEqual(resolve("next Friday", now="2026-10-16T10:00"), "2026-10-23")
        self.assertEqual(resolve("this Monday"), "")                            # already past this week

    def test_named_days(self):
        for said in ("30 October", "the 30th of October", "October 30th", "on the thirtieth of October", "30/10",
                     "Friday 30 October 2026", "2026-10-30", "the 30th", "thirty October"):
            self.assertEqual(resolve(said), "2026-10-30", said)
        self.assertEqual(resolve("Thursday 15 October 2026"), "2026-10-15")
        self.assertEqual(resolve("twenty-third of October"), "2026-10-23")
        self.assertEqual(resolve("the 5th"), "2026-11-05")                      # passed this month: next month
        self.assertEqual(resolve("5 January"), "2027-01-05")

    def test_vague_or_empty_is_no_date(self):
        for said in ("", "next week", "when I get paid", "end of the month", "soon", "yes"):
            self.assertEqual(resolve(said), "", said)


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_workflow()

    def start(self, products):
        v = {"now": NOW}
        account(v, products)
        self.assertEqual(run(self.nodes, "facts", v), "m_today")
        return v

    def test_yes_to_today_is_the_calls_today(self):                              # PUB-01
        v = self.start([CARD])
        v.update(m_today_turn="accepts", agreed_date="")
        self.assertEqual(route(self.nodes["m_today"], v), "all_yes")              # one product: no scope needed
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback")
        self.assertEqual((v["date_1"], v["amt_1"]), ("2026-10-14", "300"))
        v.update(m_today_turn="accepts", agreed_date="today")
        run(self.nodes, "all_yes", v)
        self.assertEqual(v["date_1"], "2026-10-14")

    def test_one_product_named_goes_to_the_ladders(self):                         # PUB-12
        prods = [dict(CARD, days_late=16, past_due=510.0, minimum_payment=153.0), dict(LOAN, days_late=16, past_due=1320.0), dict(CAR, days_late=7, past_due=140.0)]
        v = self.start(prods)
        v.update(m_today_turn="proposes", m_today_scope="some", agreed_date="tomorrow")
        self.assertEqual(route(self.nodes["m_today"], v), "enter_1")
        v.update(m_today_turn="accepts", m_today_scope="some")
        self.assertEqual(route(self.nodes["m_today"], v), "enter_1")
        v.update(m_today_turn="accepts", m_today_scope="all")
        self.assertEqual(route(self.nodes["m_today"], v), "all_yes")
        self.assertEqual(run(self.nodes, "enter_1", v), "p1_attempt1_full")
        v.update(agreed_date="tomorrow", agreed_amount="510", **{"p1_attempt1_full_all": "no"})
        self.assertEqual(run(self.nodes, "save_1_attempt1_full", v), "p2_attempt1_full")
        self.assertEqual((v["date_1"], v["amt_1"]), ("2026-10-15", "510"))
        run(self.nodes, "refused_2", v)
        self.assertEqual(run(self.nodes, "refused_3", v), "m_readback")
        self.assertIn("Thursday 15 October 2026", v["readback"])

    def test_one_date_for_everything_said_at_the_start(self):                    # PUB-13
        v = self.start([CARD, LOAN])
        v.update(m_today_turn="proposes", m_today_scope="all", agreed_date="both on 30 October")
        self.assertEqual(route(self.nodes["m_today"], v), "all_yes")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback")
        self.assertEqual((v["date_1"], v["adj_1"], v["date_2"], v["adj_2"]), ("2026-10-30", "", "2026-10-23", "1"))

    def test_a_vague_time_for_everything_asks_per_product(self):
        v = self.start([CARD, LOAN])
        v.update(m_today_turn="proposes", m_today_scope="all", agreed_date="next week")
        self.assertEqual(run(self.nodes, "all_yes", v), "p1_attempt1_full")
        self.assertEqual(v.get("st_1", ""), "")

    def test_weekend_day_moves_to_the_next_business_day_and_says_so(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="Saturday", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual((v["date_1"], v["mov_1"], v["adj_1"]), ("2026-10-19", "1", ""))
        v.update(st_2="noted", reason_2="refused")
        run(self.nodes, "finish", v)
        self.assertIn("Monday 19 October 2026 (the next business day)", v["readback"])

    def test_holiday_moves_too(self):
        v = self.start([CARD])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="26 October", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual((v["date_1"], v["mov_1"]), ("2026-10-27", "1"))

    def test_unreadable_date_falls_back_to_the_offer(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="yes that works", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual(v["date_1"], "2026-10-16")                               # the step's offer: end of this week

    def test_fix_in_words_and_a_loop_ends(self):
        v = self.start([CARD, LOAN])
        v.update(st_1="agreed", amt_1="300", date_1="2026-10-16", adj_1="", st_2="noted", reason_2="refused")
        v.update(fix_kind="change", fix_slot="1", fix_date="tomorrow", fix_amount="")
        self.assertEqual(run(self.nodes, "apply_fix", v), "m_readback")
        self.assertEqual(v["date_1"], "2026-10-15")
        for _ in range(2):
            v.update(fix_kind="change", fix_slot="1", fix_date="tomorrow", fix_amount="")
            self.assertEqual(run(self.nodes, "apply_fix", v), "m_readback")
        v.update(fix_kind="change", fix_slot="1", fix_date="tomorrow", fix_amount="")
        self.assertEqual(run(self.nodes, "apply_fix", v), "note_1")              # the fourth change: no promise, notes, close
        self.assertEqual(v["reason_1"], "refused")

    def test_read_back_is_spoken_on_every_entry(self):
        self.assertFalse(self.nodes["m_readback"]["on_enter_first_entry_only"])
        self.assertFalse(self.nodes["m_fix"]["on_enter_first_entry_only"])

    def test_no_date_extraction_is_left(self):
        for name, n in self.nodes.items():
            for f in n.get("extraction_schema") or []:
                self.assertNotEqual(f.get("type"), "date", f"{name}.{f['name']}")


if __name__ == "__main__":
    unittest.main()
