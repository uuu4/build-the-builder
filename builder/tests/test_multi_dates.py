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
        self.assertEqual(resolve("Monday the 26th"), "2026-10-26")               # live run: was read as next Monday
        self.assertEqual(resolve("Monday the twenty sixth"), "2026-10-26")
        self.assertEqual(resolve("on the 30th, a Friday"), "2026-10-30")
        self.assertEqual(resolve("the 5th"), "2026-11-05")                      # passed this month: next month
        self.assertEqual(resolve("5 January"), "2027-01-05")

    def test_a_corrected_date_wins(self):                                       # style "corrects", PUB-06
        self.assertEqual(resolve("the 15th, sorry, I mean the 16th"), "2026-10-16")
        self.assertEqual(resolve("Thursday, actually Friday"), "2026-10-16")
        self.assertEqual(resolve("the 30th, sorry"), "2026-10-30")                # nothing after the correction: the date before it

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

    def test_a_vague_time_is_asked_once_then_the_deadline_is_proposed(self):     # PUB-07
        v = self.start([dict(LOAN, days_late=5, past_due=540.0, instalment_amount=180.0)])
        v.update(m_today_turn="proposes", agreed_date="the week after next")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_today")                 # the model asks for the exact day
        self.assertEqual(v.get("st_1", ""), "")
        v.update(m_today_turn="proposes", agreed_date="26 October")              # a holiday in Brief B's calendar
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback")
        self.assertEqual((v["date_1"], v["mov_1"]), ("2026-10-27", "1"))
        v = self.start([CARD, LOAN])
        for _ in range(2):
            v.update(m_today_turn="proposes", m_today_scope="all", agreed_date="")
            r = run(self.nodes, "all_yes", v)
        self.assertEqual(r, "m_readback")                                         # second vague answer: the latest dates
        self.assertEqual((v["date_1"], v["adj_1"], v["date_2"], v["adj_2"]), (v["s1_deadline"], "1", v["s2_deadline"], "1"))

    def test_no_to_today_goes_to_the_ladders(self):
        v = self.start([CARD, LOAN])
        v.update(m_today_turn="accepts", m_today_scope="all", agreed_date="")
        v["m_today_turn"] = "refuses"
        self.assertEqual(route(self.nodes["m_today"], v), "enter_1")

    def test_a_date_named_for_one_product_at_the_start_is_kept(self):            # PUB-12, second live run
        prods = [dict(CARD, days_late=16, past_due=510.0, minimum_payment=153.0), dict(LOAN, days_late=16, past_due=1320.0), dict(CAR, days_late=7, past_due=140.0)]
        v = self.start(prods)
        v.update(m_today_turn="proposes", m_today_scope="some", m_today_when_1="tomorrow")
        self.assertEqual(route(self.nodes["m_today"], v), "enter_1")
        self.assertEqual(run(self.nodes, "enter_1", v), "p2_attempt1_full")       # card agreed on its own date, loan asked
        self.assertEqual((v["st_1"], v["date_1"], v["amt_1"]), ("agreed", "2026-10-15", "510"))
        self.assertEqual(v["m_today_when_1"], "")
        v.update(m_today_when_2="tomorrow", m_today_amount_2="100")              # below the loan's floor: asked, not agreed
        self.assertEqual(run(self.nodes, "enter_2", v), "p2_attempt1_full")
        self.assertEqual(v.get("st_2", ""), "")

    def test_read_back_and_fix_carry_the_rules_of_the_call(self):
        self.assertIn("robot", self.nodes["m_readback"]["task_message"])
        self.assertIn("RULES OF THE CALL", self.nodes["m_fix"]["task_message"])

    def test_weekend_day_moves_to_the_next_business_day_and_says_so(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="Saturday", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual((v["date_1"], v["mov_1"], v["adj_1"]), ("2026-10-19", "1", ""))
        v.update(st_2="noted", reason_2="refused")
        run(self.nodes, "finish", v)
        self.assertIn("Monday 19 October 2026 (the day you named is not a business day", v["readback"])

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

    def test_read_back_is_a_fixed_line_unless_a_question_came_with_the_agreement(self):   # PUB-12 style run, PUB-04
        self.assertFalse(self.nodes["m_readback"]["on_enter_first_entry_only"])
        self.assertEqual(self.nodes["m_readback"]["on_enter"], {"type": "tts", "text": "{{readback}}"})
        self.assertIn("{{readback}}", self.nodes["m_readback_q"]["on_enter"]["prompt"])
        self.assertFalse(self.nodes["m_fix"]["on_enter_first_entry_only"])
        self.assertIn("asked_q", [f["name"] for f in self.nodes["m_today"]["extraction_schema"]])
        self.assertIn("asked_q", [f["name"] for f in self.nodes["p1_attempt1_full"]["extraction_schema"]])
        for n in ("m_readback", "m_readback_q", "m_fix"):
            self.assertIn("asked_q", [f["name"] for f in self.nodes[n]["extraction_schema"]], n)
        v = self.start([CARD])
        v.update(m_today_turn="accepts", agreed_date="", asked_q="yes")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback_q")
        self.assertEqual(v["asked_q"], "")
        v.update(fix_kind="change", fix_slot="1", fix_date="tomorrow", fix_amount="")
        self.assertEqual(run(self.nodes, "apply_fix", v), "m_readback")

    def test_a_change_named_with_the_no_is_applied_at_once(self):                # PUB-07 pieces run
        v = self.start([dict(LOAN, days_late=5, past_due=540.0, instalment_amount=180.0)])
        v.update(st_1="agreed", amt_1="540", date_1="2026-10-19", adj_1="", mov_1="")
        v.update(rb_turn="changes", fix_kind="change", fix_slot="unknown", fix_date="Monday the twenty sixth", fix_amount="")
        nxt = route(self.nodes["m_readback"], v)
        self.assertEqual(nxt, "apply_fix")
        self.assertEqual(run(self.nodes, nxt, v), "m_readback")                     # one product: no slot needed
        self.assertEqual((v["date_1"], v["mov_1"]), ("2026-10-27", "1"))            # 26 October is a holiday in this calendar
        v.update(rb_turn="changes", fix_kind="unknown")
        self.assertEqual(route(self.nodes["m_readback"], v), "m_fix")

    def test_the_week_named_first_and_the_weekday_after(self):                   # PUB-07: "the week after next" ... "Monday"
        self.assertEqual(resolve("Monday, the week after next"), "2026-10-26")
        self.assertEqual(resolve("Wednesday next week"), "2026-10-21")
        v = self.start([dict(LOAN, days_late=5, past_due=540.0, instalment_amount=180.0)])
        v.update(m_today_turn="proposes", agreed_date="the week after next")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_today")
        v.update(m_today_turn="proposes", agreed_date="Monday")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback")
        self.assertEqual(v["date_1"], "2026-10-27")                                 # Monday 26th, a holiday here: Tuesday

    def test_an_amount_below_the_floor_is_not_recorded(self):                    # PUB-06 "six hundred and thirty seven"; PUB-11 "3"
        v = self.start([dict(CARD, past_due=2125.10, minimum_payment=637.5, days_late=12)])
        v["floor_first"] = "1"
        self.assertEqual(run(self.nodes, "enter_1", v), "p1_attempt1_floor")
        v.update(agreed_date="", agreed_amount="637", **{"p1_attempt1_floor_all": "no"})
        run(self.nodes, "save_1_attempt1_floor", v)
        self.assertEqual(v["amt_1"], "637.50")
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="", agreed_amount="3", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual(v["amt_1"], "300")                                         # the step's offer: the full amount

    def test_a_date_only_in_the_per_product_field_counts_for_all(self):          # PUB-13 pieces: "the thirtieth"
        v = self.start([CARD, LOAN])
        v.update(m_today_turn="proposes", m_today_scope="all", agreed_date="", m_today_when_1="the thirtieth")
        self.assertEqual(run(self.nodes, "all_yes", v), "m_readback")
        self.assertEqual((v["date_1"], v["date_2"], v["adj_2"]), ("2026-10-30", "2026-10-23", "1"))

    def test_endless_read_backs_end_without_a_promise(self):
        v = self.start([CARD])
        v.update(st_1="agreed", amt_1="300", date_1="2026-10-16", adj_1="", mov_1="")
        for _ in range(5):
            self.assertEqual(run(self.nodes, "finish", v), "m_readback")
        self.assertEqual(run(self.nodes, "finish", v), "note_1")                  # through rg_1: a note, no promise
        self.assertEqual((v["st_1"], v["reason_1"]), ("noted", "refused"))

    def test_no_date_extraction_is_left(self):
        for name, n in self.nodes.items():
            for f in n.get("extraction_schema") or []:
                self.assertNotEqual(f.get("type"), "date", f"{name}.{f['name']}")


if __name__ == "__main__":
    unittest.main()
