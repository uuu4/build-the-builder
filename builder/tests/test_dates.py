"""Tests for builder.kit.dates. The generated snippets are executed as shipped.

    python3 -m unittest discover -s tests

Brief A values appear only here. The module under test must hold none of them.
"""
import ast
import copy
import json
import pathlib
import re
import unittest

from builder.kit.dates import assert_code_safe
from builder.kit import dates
from builder.kit.dates import build_check_code, build_facts_code, normalize_params, run_code

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = "2026-10-14T11:00"  # a Wednesday

BRIEF_A = {
    "weekend": [5, 6],
    "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"],
    "bands": [
        {"name": "early", "days_late_min": 1, "days_late_max": 7,
         "deadline": {"kind": "business_days", "n": 12}, "attempts": 1},
        {"name": "late", "days_late_min": 8, "days_late_max": 45,
         "deadline": {"kind": "business_days", "n": 7}, "attempts": 2},
    ],
    "floor_field_by_type": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount",
                            "car_loan": "instalment_amount"},
    "product_label": {"credit_card": "credit card ending <card_last4>"},
    "named_dates": [{"name": "attempt1", "kind": "last_business_day_this_week", "if_today_use_next_week": True}],
    "callback": {"days": ["today", "next_business_day"], "from": "10:00", "to": "19:00", "after_now": True},
}

CARD = {"product_id": "p1", "type": "credit_card", "card_last4": "4821", "past_due": 2125.1,
        "days_late": 12, "minimum_payment": 637.5}
LOAN = {"product_id": "p2", "type": "personal_loan", "past_due": 310.5, "days_late": 4, "instalment_amount": 103.5}


def params(**over):
    p = copy.deepcopy(BRIEF_A)
    p.update(over)
    return p


def facts(products=None, now=NOW, p=None, **extra):
    v = {"now": now, "accounts": copy.deepcopy([CARD, LOAN] if products is None else products)}
    v.update(extra)
    run_code(build_facts_code(p or params()), v)
    return v


def check(products=None, now=NOW, p=None, **extra):
    v = {"now": now, "accounts": copy.deepcopy([CARD, LOAN] if products is None else products)}
    v.update(extra)
    run_code(build_check_code(p or params()), v)
    return v


FACTS_KEYS = ("today", "today_text", "now_time", "product_count", "product_ids", "date_facts",
              "facts_state", "facts_error")
CHECK_KEYS = ("date_check", "date_check_next", "date_check_deadline", "amount_check", "callback_check",
              "check_text", "check_state")


class Facts(unittest.TestCase):
    def test_values_for_the_practice_day(self):
        v = facts()
        self.assertEqual(v["facts_state"], "ok")
        self.assertEqual(v["facts_error"], "")
        self.assertEqual(v["today"], "2026-10-14")
        self.assertEqual(v["today_text"], "Wednesday 14 October 2026")
        self.assertEqual(v["now_time"], "11:00")
        self.assertEqual((v["band_p1"], v["deadline_p1"]), ("late", "2026-10-23"))
        self.assertEqual(v["deadline_text_p1"], "Friday 23 October 2026")
        self.assertEqual((v["band_p2"], v["deadline_p2"]), ("early", "2026-11-02"))
        self.assertEqual(v["deadline_text_p2"], "Monday 2 November 2026")
        self.assertEqual((v["floor_p1"], v["attempts_p1"]), ("637.50", "2"))
        self.assertEqual((v["floor_p2"], v["attempts_p2"]), ("103.50", "1"))
        self.assertEqual(v["attempt1"], "2026-10-16")
        self.assertEqual(v["attempt1_text"], "Friday 16 October 2026")
        self.assertEqual(v["product_count"], "2")
        self.assertEqual(v["product_ids"], "p1,p2")
        for k in FACTS_KEYS:
            self.assertIsInstance(v[k], str, k)

    def test_all_written_values_are_strings(self):
        before = {"now": NOW, "accounts": [CARD]}
        v = facts([CARD])
        for k in v:
            if k not in before:
                self.assertIsInstance(v[k], str, k)

    def test_text_block_content(self):
        t = facts()["date_facts"]
        self.assertIn("Today is Wednesday 14 October 2026 (2026-10-14)", t)
        self.assertIn("The time now is 11:00", t)
        self.assertIn("Monday 26 October 2026 (2026-10-26)", t)  # holiday listed
        self.assertIn("credit card ending 4821", t)
        self.assertIn("Past due 2125.10", t)
        self.assertIn("Days late: 12", t)
        self.assertIn("Band: late", t)
        self.assertIn("Friday 23 October 2026 (2026-10-23)", t)
        self.assertIn("Floor: 637.50 (field minimum_payment)", t)
        self.assertIn("Attempts: 2", t)
        self.assertIn("personal loan", t)  # default label from the type
        self.assertIn("attempt1: Friday 16 October 2026 (2026-10-16)", t)
        self.assertIn("Thursday 15 October 2026 (2026-10-15), next business day: from 10:00 to 19:00", t)
        self.assertIn("Wednesday 14 October 2026 (2026-10-14), today: from 11:01 to 19:00", t)

    def test_calendar(self):
        lines = facts()["date_facts"].split("\n")
        cal = [ln for ln in lines if re.match(r"^\d{4}-\d{2}-\d{2} ", ln)]
        self.assertEqual(len(cal), 22)  # today and 21 days after it
        self.assertEqual(cal[0], "2026-10-14 Wednesday: business day, this week, today")
        self.assertIn("2026-10-17 Saturday: weekend, this week", cal)
        self.assertIn("2026-10-23 Friday: business day, next week", cal)
        self.assertIn("2026-10-26 Monday: bank holiday, later", cal)
        self.assertIn("2026-11-04 Wednesday: business day, later", cal)
        short = facts(p=params(calendar_days=3))["date_facts"].split("\n")
        self.assertEqual(len([ln for ln in short if re.match(r"^\d{4}-\d{2}-\d{2} ", ln)]), 4)

    def test_first_attempt_on_a_friday_moves_to_next_week(self):
        v = facts(now="2026-10-16T09:00")
        self.assertEqual(v["attempt1"], "2026-10-23")

    def test_first_attempt_on_a_weekend_moves_to_next_week(self):
        self.assertEqual(facts(now="2026-10-17T09:00")["attempt1"], "2026-10-23")

    def test_first_attempt_without_the_flag_stays_on_today(self):
        nd = [{"name": "a", "kind": "last_business_day_this_week", "if_today_use_next_week": False}]
        self.assertEqual(facts(now="2026-10-16T09:00", p=params(named_dates=nd))["a"], "2026-10-16")

    def test_other_named_date_kinds(self):
        nd = [{"name": "t", "kind": "today"}, {"name": "nb", "kind": "next_business_day"},
              {"name": "nw", "kind": "last_business_day_next_week"},
              {"name": "n5", "kind": "nth_business_day", "n": 5}]
        v = facts(p=params(named_dates=nd))
        self.assertEqual((v["t"], v["nb"], v["nw"], v["n5"]), ("2026-10-14", "2026-10-15", "2026-10-23", "2026-10-21"))
        v = facts(now="2026-10-16T09:00", p=params(named_dates=nd))
        self.assertEqual((v["nb"], v["nw"]), ("2026-10-19", "2026-10-23"))

    def test_holiday_is_skipped_when_counting(self):
        # 12 business days after Wednesday 14 October, with Monday 26 October a holiday
        self.assertEqual(facts([LOAN])["deadline_p2"], "2026-11-02")
        no_holiday = facts([LOAN], p=params(holidays=[]))
        self.assertEqual(no_holiday["deadline_p2"], "2026-10-30")

    def test_deadline_kinds(self):
        def dl(kind, **kw):
            band = {"name": "b", "days_late_min": None, "days_late_max": None,
                    "deadline": dict(kind=kind, **kw), "attempts": None}
            return facts([LOAN], p=params(bands=[band]))
        self.assertEqual(dl("end_of_month")["deadline_p2"], "2026-10-30")  # 31st is a Saturday
        self.assertEqual(dl("calendar_days", n=14, roll="none")["deadline_p2"], "2026-10-28")
        self.assertEqual(dl("calendar_days", n=11, roll="none")["deadline_p2"], "2026-10-25")
        self.assertEqual(dl("calendar_days", n=11, roll="back")["deadline_p2"], "2026-10-23")
        self.assertEqual(dl("calendar_days", n=11, roll="forward")["deadline_p2"], "2026-10-27")
        self.assertEqual(dl("calendar_days", n=11)["deadline_p2"], "2026-10-23")  # roll defaults to back
        self.assertEqual(dl("business_days", n=0)["deadline_p2"], "2026-10-14")
        self.assertEqual(dl("business_days", n=2)["attempts_p2"], "")  # attempts null
        self.assertEqual(facts([LOAN], now="2026-10-31T10:00",
                               p=params(bands=[{"name": "b", "deadline": {"kind": "end_of_month"}}]))["deadline_p2"],
                         "2026-11-02")  # never before today

    def test_other_weekend_and_day_names(self):
        v = facts([LOAN], p=params(weekend=[4, 5], holidays=[]))  # Friday and Saturday off
        self.assertIn("2026-10-16 Friday: weekend", v["date_facts"])
        self.assertIn("Business days are Monday, Tuesday, Wednesday, Thursday, Sunday.", v["date_facts"])

    def test_band_edges_and_open_ends(self):
        bands = [{"name": "a", "days_late_min": None, "days_late_max": 3,
                  "deadline": {"kind": "business_days", "n": 1}, "attempts": 1},
                 {"name": "b", "days_late_min": 4, "days_late_max": None,
                  "deadline": {"kind": "business_days", "n": 2}, "attempts": 2}]
        mk = lambda n: dict(LOAN, days_late=n)
        self.assertEqual(facts([mk(3)], p=params(bands=bands))["band_p2"], "a")
        self.assertEqual(facts([mk(4)], p=params(bands=bands))["band_p2"], "b")
        self.assertEqual(facts([mk(400)], p=params(bands=bands))["band_p2"], "b")
        self.assertEqual(facts([mk(0)], p=params(bands=bands))["band_p2"], "a")

    def test_days_late_that_fit_no_band(self):
        v = facts([dict(LOAN, days_late=60)])
        self.assertEqual(v["facts_state"], "ok")
        self.assertEqual((v["band_p2"], v["deadline_p2"], v["deadline_text_p2"], v["attempts_p2"]), ("", "", "", ""))
        self.assertIn("No band fits this product.", v["date_facts"])
        self.assertIn("Deadline: not known.", v["date_facts"])
        c = check([dict(LOAN, days_late=60)], proposed_date="2026-10-30")
        self.assertEqual((c["date_check"], c["date_check_deadline"]), ("ok", ""))

    def test_numbers_may_arrive_as_strings(self):
        v = facts([dict(CARD, past_due="2125.10", days_late="12", minimum_payment="637.5")])
        self.assertEqual((v["band_p1"], v["floor_p1"]), ("late", "637.50"))
        self.assertIn("Past due 2125.10", v["date_facts"])

    def test_missing_floor_field_and_missing_ids(self):
        v = facts([{"type": "mystery", "past_due": 10, "days_late": 2}])
        self.assertEqual(v["facts_state"], "ok")
        self.assertEqual(v["product_ids"], "p1")
        self.assertEqual(v["floor_p1"], "")
        self.assertIn("Floor: not known.", v["date_facts"])
        self.assertIn("mystery", v["date_facts"])

    def test_duplicate_product_ids_stay_apart(self):
        v = facts([dict(CARD), dict(LOAN, product_id="p1")])
        self.assertEqual(v["product_count"], "2")
        self.assertEqual(v["band_p1"], "late")
        self.assertEqual(v["band_p1_2"], "early")

    def test_param_names_for_the_variables_and_fields(self):
        p = params(now_var="clock", products_var="rows",
                   fields={"id": "pid", "type": "kind", "past_due": "owed", "days_late": "days_late"})
        row = {"pid": "x9", "kind": "credit_card", "owed": "50", "days_late": 9, "minimum_payment": 5, "card_last4": "1111"}
        v = {"clock": "2026-10-14T11:00", "rows": [row]}
        run_code(build_facts_code(p), v)
        self.assertEqual(v["facts_state"], "ok")
        self.assertEqual((v["band_x9"], v["floor_x9"]), ("late", "5.00"))
        self.assertIn("Past due 50.00", v["date_facts"])

    def test_now_with_seconds_zone_and_space(self):
        for now in ("2026-10-14T11:00:45Z", "2026-10-14 11:00:45", "2026-10-14T11:00:00+02:00"):
            v = facts(now=now)
            self.assertEqual((v["today"], v["now_time"]), ("2026-10-14", "11:00"), now)

    def test_now_without_a_time(self):
        v = facts(now="2026-10-14")
        self.assertEqual((v["facts_state"], v["now_time"]), ("ok", ""))
        self.assertIn("Wednesday 14 October 2026 (2026-10-14), today: from 10:00 to 19:00", v["date_facts"])

    def test_no_callback_section_when_null(self):
        t = facts(p=params(callback=None))["date_facts"]
        self.assertNotIn("Callback", t)

    def test_running_twice_gives_the_same_facts(self):
        a, b = facts(), facts()
        self.assertEqual(a, b)


class ProductForms(unittest.TestCase):
    """The exact shape of the account variable is not confirmed on the platform."""

    def expect_ok(self, v):
        self.assertEqual(v["facts_state"], "ok", v.get("facts_error"))
        self.assertEqual(v["product_ids"], "p1,p2")
        self.assertEqual((v["deadline_p1"], v["deadline_p2"]), ("2026-10-23", "2026-11-02"))
        self.assertEqual((v["floor_p1"], v["floor_p2"]), ("637.50", "103.50"))

    def run_with(self, **vars_):
        v = {"now": NOW}
        v.update(vars_)
        run_code(build_facts_code(params()), v)
        return v

    def test_list_in_the_products_variable(self):
        self.expect_ok(self.run_with(accounts=[CARD, LOAN]))

    def test_json_string_in_the_products_variable(self):
        self.expect_ok(self.run_with(accounts=json.dumps([CARD, LOAN])))

    def test_python_repr_string(self):
        self.expect_ok(self.run_with(accounts=str([CARD, LOAN])))

    def test_json_object_with_products(self):
        self.expect_ok(self.run_with(accounts=json.dumps({"ok": True, "products": [CARD, LOAN]})))

    def test_list_in_the_response_variable(self):
        self.expect_ok(self.run_with(**{"get_account_response.data.products": [CARD, LOAN]}))

    def test_json_string_in_the_response_variable(self):
        self.expect_ok(self.run_with(**{"get_account_response.data.products": json.dumps([CARD, LOAN])}))

    def test_flattened_keys(self):
        flat = {}
        for i, prod in enumerate([CARD, LOAN]):
            for k, val in prod.items():
                flat["get_account_response.data.products.%d.%s" % (i, k)] = str(val)  # all strings
        flat["get_account_response.data.ok"] = "true"
        flat["get_account_response.status"] = "success"
        self.expect_ok(self.run_with(**flat))

    def test_flattened_keys_are_ordered_by_index_not_by_text(self):
        flat = {}
        rows = [dict(LOAN, product_id="p%d" % (i + 1)) for i in range(11)]
        for i, prod in enumerate(rows):
            for k, val in prod.items():
                flat["get_account_response.data.products.%d.%s" % (i, k)] = val
        v = self.run_with(**flat)
        self.assertEqual(v["product_ids"], ",".join("p%d" % (i + 1) for i in range(11)))

    def test_flattened_keys_under_the_products_variable_name(self):
        flat = {"accounts.0.product_id": "p1", "accounts.0.type": "credit_card", "accounts.0.past_due": "5",
                "accounts.0.days_late": "3", "accounts.0.minimum_payment": "2"}
        v = self.run_with(**flat)
        self.assertEqual((v["facts_state"], v["floor_p1"]), ("ok", "2.00"))

    def test_first_usable_form_wins_over_later_ones(self):
        v = self.run_with(accounts=[dict(LOAN, product_id="only")],
                          **{"get_account_response.data.products": [CARD, LOAN]})
        self.assertEqual(v["product_ids"], "only")

    def test_unusable_first_form_falls_through(self):
        v = self.run_with(accounts="[not json", **{"get_account_response.data.products": [CARD, LOAN]})
        self.expect_ok(v)

    def test_check_reads_the_same_forms(self):
        flat = {"get_account_response.data.products.0.product_id": "p1",
                "get_account_response.data.products.0.type": "credit_card",
                "get_account_response.data.products.0.past_due": "2125.1",
                "get_account_response.data.products.0.days_late": "12",
                "get_account_response.data.products.0.minimum_payment": "637.5"}
        v = {"now": NOW, "proposed_date": "2026-11-06", "proposed_amount": "600"}
        v.update(flat)
        run_code(build_check_code(params()), v)
        self.assertEqual((v["check_state"], v["date_check"], v["amount_check"]), ("ok", "after_deadline", "below_floor"))


class CheckDate(unittest.TestCase):
    def date(self, d, products=None, **kw):
        return check(products, proposed_date=d, current_product="p1", **kw)

    def test_weekend_and_holiday_move_to_the_next_business_day(self):
        v = check([LOAN], proposed_date="2026-10-26", current_product="p2")
        self.assertEqual((v["date_check"], v["date_check_next"], v["date_check_deadline"]),
                         ("not_business_day", "2026-10-27", "2026-11-02"))
        self.assertEqual(v["check_text"],
                         "Monday 26 October 2026 is a bank holiday, not a business day. "
                         "The next business day is Tuesday 27 October 2026, "
                         "which is inside the deadline (Monday 2 November 2026).")
        v = check([LOAN], proposed_date="2026-10-17", current_product="p2")
        self.assertEqual((v["date_check"], v["date_check_next"]), ("not_business_day", "2026-10-19"))
        self.assertIn("Saturday 17 October 2026 is a weekend day", v["check_text"])
        self.assertIn("Monday 19 October 2026", v["check_text"])

    def test_inside_the_deadline_is_ok(self):
        v = check([dict(CARD, days_late=4)], proposed_date="2026-10-30")
        self.assertEqual((v["date_check"], v["date_check_next"]), ("ok", "2026-10-30"))
        self.assertEqual(v["check_state"], "ok")
        self.assertIn("Friday 30 October 2026 is a business day", v["check_text"])

    def test_after_the_deadline(self):
        v = check([dict(CARD, days_late=14)], proposed_date="2026-11-06")
        self.assertEqual((v["date_check"], v["date_check_deadline"], v["date_check_next"]),
                         ("after_deadline", "2026-10-23", ""))
        self.assertEqual(v["check_text"], "Friday 6 November 2026 is after the deadline. "
                                          "The latest date you can record is Friday 23 October 2026.")
        v = self.date("2026-11-18")
        self.assertEqual(v["check_text"], "Wednesday 18 November 2026 is after the deadline. "
                                          "The latest date you can record is Friday 23 October 2026.")

    def test_a_weekend_after_the_deadline_is_after_the_deadline(self):
        self.assertEqual(self.date("2026-10-24")["date_check"], "after_deadline")  # a Saturday, deadline is Friday 23

    def test_the_deadline_day_itself_is_ok(self):
        self.assertEqual(self.date("2026-10-23")["date_check"], "ok")
        self.assertEqual(self.date("2026-10-26")["date_check"], "after_deadline")

    def test_past_and_today(self):
        v = self.date("2026-10-13")
        self.assertEqual((v["date_check"], v["date_check_next"]), ("past", ""))
        self.assertIn("Tuesday 13 October 2026 is in the past", v["check_text"])
        self.assertIn("The earliest date you can record is Wednesday 14 October 2026", v["check_text"])
        self.assertEqual(self.date("2026-10-14")["date_check"], "ok")

    def test_today_on_a_weekend_is_not_a_business_day(self):
        v = check([LOAN], now="2026-10-17T09:00", proposed_date="2026-10-17", current_product="p2")
        self.assertEqual((v["date_check"], v["date_check_next"]), ("not_business_day", "2026-10-19"))

    def test_none_and_invalid(self):
        for blank in (None, "", "  ", "None", "null"):
            self.assertEqual(self.date(blank)["date_check"], "none", repr(blank))
        v = check(current_product="p1")  # variable never set
        self.assertEqual(v["date_check"], "none")
        for bad in ("tomorrow", "2026-02-30", "26/10/2026", "2026-13-01", 12345, ["2026-10-30"]):
            v = self.date(bad)
            self.assertEqual((v["date_check"], v["date_check_next"], v["check_state"]), ("invalid", "", "ok"), repr(bad))

    def test_a_date_with_a_time_is_read_by_its_date(self):
        self.assertEqual(self.date("2026-10-16T00:00:00Z")["date_check"], "ok")

    def test_unresolved_placeholder_counts_as_nothing(self):
        self.assertEqual(self.date("{" + "{proposed_date}" + "}")["date_check"], "none")

    def test_current_product_selection(self):
        v = check(proposed_date="2026-10-30", current_product="p2")
        self.assertEqual((v["date_check"], v["date_check_deadline"], v["check_product"]), ("ok", "2026-11-02", "p2"))
        v = check(proposed_date="2026-10-30", current_product="p1")
        self.assertEqual((v["date_check"], v["date_check_deadline"], v["check_product"]), ("after_deadline", "2026-10-23", "p1"))
        for odd in (None, "", "p9", "P2 "):
            v = check(proposed_date="2026-10-30", current_product=odd)
            want = "p2" if odd == "P2 " else "p1"
            self.assertEqual(v["check_product"], want, repr(odd))
        v = check(proposed_date="2026-10-30")  # no current_product at all
        self.assertEqual(v["check_product"], "p1")

    def test_check_and_facts_agree_on_the_deadline(self):
        f = facts()
        for pid in ("p1", "p2"):
            c = check(proposed_date="2026-10-16", current_product=pid)
            self.assertEqual(c["date_check_deadline"], f["deadline_" + pid])

    def test_another_day(self):
        # Friday 16 October: the 7th business day after is Wednesday 28 October (Monday 26 is a holiday)
        v = check([dict(CARD, days_late=20)], now="2026-10-16T09:00", proposed_date="2026-10-28")
        self.assertEqual((v["date_check_deadline"], v["date_check"]), ("2026-10-28", "ok"))
        v = check([dict(CARD, days_late=20)], now="2026-10-16T09:00", proposed_date="2026-10-29")
        self.assertEqual(v["date_check"], "after_deadline")


class CheckAmount(unittest.TestCase):
    def amount(self, a, **kw):
        return check([CARD], proposed_amount=a, current_product="p1", **kw)

    def test_floor_and_full_are_included(self):
        for a in (637.5, "637.50", 2125.1, "2125.10", 1000, "1000", "$637.50", "$1,250", "1,250", "1250.00 USD",
                  " 700 "):
            self.assertEqual(self.amount(a)["amount_check"], "ok", repr(a))

    def test_below_the_floor(self):
        v = self.amount(600)
        self.assertEqual(v["amount_check"], "below_floor")
        self.assertIn("The amount 600.00 is below the floor of 637.50 (minimum payment)", v["check_text"])
        self.assertEqual(self.amount("637.49")["amount_check"], "below_floor")

    def test_above_the_full_amount(self):
        v = self.amount(3000)
        self.assertEqual(v["amount_check"], "above_full")
        self.assertIn("The most you can record is 2125.10", v["check_text"])
        self.assertEqual(self.amount("2,125.11")["amount_check"], "above_full")

    def test_none_and_invalid(self):
        for blank in (None, "", "none"):
            self.assertEqual(self.amount(blank)["amount_check"], "none", repr(blank))
        for bad in ("abc", "$", 0, "0", -5, "-10", True, [100], "1.2.3", float("nan"), float("inf")):
            v = self.amount(bad)
            self.assertEqual((v["amount_check"], v["check_state"]), ("invalid", "ok"), repr(bad))

    def test_decimal_comma(self):
        self.assertEqual(self.amount("637,50")["amount_check"], "ok")
        self.assertEqual(self.amount("600,5")["amount_check"], "below_floor")

    def test_each_product_has_its_own_floor(self):
        c = check(proposed_amount="100", current_product="p2")
        self.assertEqual(c["amount_check"], "below_floor")  # floor of the loan is 103.50
        c = check(proposed_amount="104", current_product="p2")
        self.assertEqual(c["amount_check"], "ok")

    def test_no_floor_known_only_checks_the_full_amount(self):
        prod = [{"product_id": "p1", "type": "mystery", "past_due": 100, "days_late": 3}]
        self.assertEqual(check(prod, proposed_amount="1")["amount_check"], "ok")
        self.assertEqual(check(prod, proposed_amount="101")["amount_check"], "above_full")


class CheckCallback(unittest.TestCase):
    def cb(self, date, time, now=NOW):
        return check(now=now, callback_date=date, callback_time=time, current_product="p1")

    def test_inside_the_window(self):
        for d, t in (("2026-10-15", "11:00"), ("2026-10-15", "10:00"), ("2026-10-15", "19:00"),
                     ("2026-10-14", "11:01"), ("2026-10-14", "19:00"), ("2026-10-14", "14:30"),
                     ("2026-10-15", "7:00 PM"), ("2026-10-15", "11:00:30")):
            v = self.cb(d, t)
            self.assertEqual((v["callback_check"], v["check_state"]), ("ok", "ok"), (d, t))

    def test_outside_the_window(self):
        for d, t in (("2026-10-15", "09:00"), ("2026-10-15", "09:59"), ("2026-10-15", "19:01"),
                     ("2026-10-14", "10:30"), ("2026-10-14", "11:00"), ("2026-10-14", "19:01"),
                     ("2026-10-13", "12:00"), ("2026-10-16", "12:00"), ("2026-10-15", "00:00")):
            self.assertEqual(self.cb(d, t)["callback_check"], "outside_window", (d, t))

    def test_text_of_an_outside_window(self):
        t = self.cb("2026-10-15", "09:00")["check_text"]
        self.assertIn("A callback on Thursday 15 October 2026 at 09:00 is outside the allowed window.", t)
        self.assertIn("Wednesday 14 October 2026 from 11:01 to 19:00", t)
        self.assertIn("Thursday 15 October 2026 from 10:00 to 19:00", t)

    def test_next_business_day_over_a_weekend_and_a_holiday(self):
        now = "2026-10-16T09:00"  # Friday
        self.assertEqual(self.cb("2026-10-19", "10:00", now)["callback_check"], "ok")
        self.assertEqual(self.cb("2026-10-17", "12:00", now)["callback_check"], "outside_window")
        now = "2026-10-23T09:00"  # Friday, Monday 26 is a holiday
        self.assertEqual(self.cb("2026-10-27", "12:00", now)["callback_check"], "ok")
        self.assertEqual(self.cb("2026-10-26", "12:00", now)["callback_check"], "outside_window")

    def test_late_in_the_day_nothing_is_left_for_today(self):
        now = "2026-10-14T19:30"
        v = self.cb("2026-10-14", "19:45", now)
        self.assertEqual(v["callback_check"], "outside_window")
        self.assertNotIn("Wednesday 14 October 2026 from", v["check_text"])
        self.assertEqual(self.cb("2026-10-15", "10:00", now)["callback_check"], "ok")

    def test_without_after_now_today_starts_at_the_opening_time(self):
        cb = dict(BRIEF_A["callback"], after_now=False)
        v = check(p=params(callback=cb), callback_date="2026-10-14", callback_time="10:30", current_product="p1")
        self.assertEqual(v["callback_check"], "ok")

    def test_none_and_invalid(self):
        self.assertEqual(self.cb(None, None)["callback_check"], "none")
        self.assertEqual(self.cb("", "")["callback_check"], "none")
        for d, t in (("2026-10-15", None), (None, "11:00"), ("soon", "11:00"), ("2026-10-15", "noon"),
                     ("2026-10-15", "25:00"), ("2026-10-15", "11:75")):
            self.assertEqual(self.cb(d, t)["callback_check"], "invalid", (d, t))

    def test_a_date_time_in_one_variable(self):
        v = check(callback_date="2026-10-15T11:00", current_product="p1")
        self.assertEqual(v["callback_check"], "ok")

    def test_no_window_configured(self):
        v = check(p=params(callback=None), callback_date="2026-10-15", callback_time="03:00", current_product="p1")
        self.assertEqual(v["callback_check"], "none")

    def test_variable_names_are_params(self):
        p = params(callback_date_var="cb_day", callback_time_var="cb_time", date_var="d", amount_var="a",
                   product_var="which")
        v = {"now": NOW, "accounts": [CARD, LOAN], "cb_day": "2026-10-15", "cb_time": "09:00", "d": "2026-10-30",
             "a": "200", "which": "p2"}
        run_code(build_check_code(p), v)
        self.assertEqual((v["callback_check"], v["date_check"], v["amount_check"], v["check_product"]),
                         ("outside_window", "ok", "ok", "p2"))


class CheckText(unittest.TestCase):
    def test_all_three_in_one_text(self):
        v = check(proposed_date="2026-11-18", proposed_amount="3000", callback_date="2026-10-15",
                  callback_time="11:00", current_product="p1")
        t = v["check_text"]
        self.assertIn("after the deadline", t)
        self.assertIn("more than the full past-due amount", t)
        self.assertIn("inside the allowed window", t)

    def test_nothing_proposed(self):
        v = check(current_product="p1")
        self.assertEqual((v["date_check"], v["amount_check"], v["callback_check"], v["check_state"]),
                         ("none", "none", "none", "ok"))
        self.assertIn("nothing to check", v["check_text"])

    def test_ok_text_keeps_the_amount_sentence(self):
        v = check(proposed_amount="637.5", current_product="p1")
        self.assertEqual(v["check_text"], "The amount 637.50 can be recorded.")


class OddInput(unittest.TestCase):
    ODD_VARS = [
        {},
        {"accounts": [CARD]},  # no now
        {"now": None, "accounts": [CARD]},
        {"now": "", "accounts": [CARD]},
        {"now": "yesterday", "accounts": [CARD]},
        {"now": 12345, "accounts": [CARD]},
        {"now": NOW},
        {"now": NOW, "accounts": None},
        {"now": NOW, "accounts": []},
        {"now": NOW, "accounts": "[]"},
        {"now": NOW, "accounts": "garbage"},
        {"now": NOW, "accounts": 42},
        {"now": NOW, "accounts": [1, 2, 3]},
        {"now": NOW, "accounts": [None]},
        {"now": NOW, "accounts": {"x": 1}},
        {"now": NOW, "accounts": [{"product_id": None, "type": None, "past_due": None, "days_late": None}]},
        {"now": NOW, "accounts": [{"product_id": "p1", "type": {"a": 1}, "past_due": [1], "days_late": "x"}]},
        {"now": NOW, "accounts": [{"product_id": ["p1"], "days_late": float("nan")}]},
        {"now": NOW, "accounts": [{"type": "credit_card", "minimum_payment": "abc", "days_late": "1e999"}]},
        {"now": NOW, "accounts": "{'broken': "},
        {"now": NOW, "get_account_response.data.products.x.y": "1", "get_account_response.data.products.0.": "1"},
        {"now": NOW, "accounts": [CARD], "proposed_date": {"d": 1}, "proposed_amount": object(),
         "callback_date": [1], "callback_time": {"t": 1}, "current_product": {"p": 1}},
    ]

    def test_facts_never_raises_and_always_writes_the_fixed_variables(self):
        for odd in self.ODD_VARS:
            v = dict(odd)
            run_code(build_facts_code(params()), v)
            for k in FACTS_KEYS + ("attempt1", "attempt1_text"):
                self.assertIn(k, v, (odd, k))
                self.assertIsInstance(v[k], str, (odd, k))
            self.assertIn(v["facts_state"], ("ok", "error"))

    def test_check_never_raises_and_always_writes_the_fixed_variables(self):
        for odd in self.ODD_VARS:
            v = dict(odd)
            run_code(build_check_code(params()), v)
            for k in CHECK_KEYS + ("check_error", "check_product"):
                self.assertIn(k, v, (odd, k))
                self.assertIsInstance(v[k], str, (odd, k))
            self.assertIn(v["check_state"], ("ok", "error"))

    def test_facts_error_values(self):
        for odd in ({}, {"accounts": [CARD]}, {"now": "yesterday", "accounts": [CARD]}):
            v = dict(odd)
            run_code(build_facts_code(params()), v)
            self.assertEqual(v["facts_state"], "error", odd)
            self.assertTrue(v["facts_error"], odd)
            self.assertEqual((v["product_count"], v["product_ids"], v["attempt1"], v["attempt1_text"]), ("0", "", "", ""))
            self.assertIn("could not be computed", v["date_facts"])
            self.assertIn("Do not state any date", v["date_facts"])

    def test_check_error_values(self):
        for odd in ({}, {"accounts": [CARD]}, {"now": NOW}, {"now": NOW, "accounts": "garbage"}):
            v = dict(odd, proposed_date="2026-10-30", proposed_amount="500", callback_date="2026-10-15",
                     callback_time="11:00")
            run_code(build_check_code(params()), v)
            self.assertEqual(v["check_state"], "error", odd)
            self.assertTrue(v["check_error"], odd)
            self.assertEqual((v["date_check"], v["amount_check"], v["callback_check"]), ("none", "none", "none"))
            self.assertEqual((v["date_check_next"], v["date_check_deadline"]), ("", ""))
            self.assertIn("Do not tell the customer", v["check_text"])

    def test_a_partly_failed_run_keeps_the_day(self):
        v = {"now": NOW, "accounts": "garbage"}
        run_code(build_facts_code(params()), v)
        self.assertEqual((v["today"], v["today_text"], v["now_time"]), ("2026-10-14", "Wednesday 14 October 2026", "11:00"))

    def test_no_products_still_gives_calendar_and_callback_window(self):
        # the someone-else path runs the facts before any account is loaded
        for odd in ({"now": NOW}, {"now": NOW, "accounts": "garbage"}, {"now": NOW, "accounts": []}):
            v = dict(odd)
            run_code(build_facts_code(params()), v)
            self.assertEqual(v["facts_state"], "ok", odd)
            self.assertEqual((v["product_count"], v["product_ids"]), ("0", ""))
            self.assertIn("no account has been loaded", v["date_facts"])
            self.assertIn("Callback windows", v["date_facts"])
            self.assertIn("Calendar", v["date_facts"])

    def test_error_after_a_good_run_overwrites_stale_values(self):
        v = {"now": NOW, "accounts": [CARD]}
        run_code(build_facts_code(params()), v)
        self.assertEqual(v["facts_state"], "ok")
        v["now"] = "garbage"
        run_code(build_facts_code(params()), v)
        self.assertEqual((v["facts_state"], v["deadline_p1"], v["product_ids"]), ("error", "", ""))

    def test_read_only_style_vars_are_not_needed(self):
        # a mapping that only offers get, keys and item assignment
        class Mini(object):
            def __init__(self, d):
                self.d = d

            def get(self, k, default=None):
                return self.d.get(k, default)

            def keys(self):
                return self.d.keys()

            def __setitem__(self, k, val):
                self.d[k] = val

        m = Mini({"now": NOW, "get_account_response.data.products.0.product_id": "p1",
                  "get_account_response.data.products.0.days_late": "3"})
        run_code(build_facts_code(params()), m)
        self.assertEqual(m.d["facts_state"], "ok")


class Safety(unittest.TestCase):
    def codes(self):
        return [build_facts_code(params()), build_check_code(params()),
                build_facts_code({"bands": BRIEF_A["bands"]}), build_check_code({"bands": BRIEF_A["bands"]})]

    def test_code_passes_the_safety_check_and_has_no_double_braces(self):
        for code in self.codes():
            assert_code_safe(code)
            self.assertNotIn("{{", code)
            self.assertNotIn("}}", code)

    def test_code_parses_as_python_3_9(self):
        for code in self.codes():
            ast.parse(code, feature_version=(3, 9))

    def test_imports_are_only_json_re_datetime(self):
        for code in self.codes():
            mods = set()
            for node in ast.walk(ast.parse(code)):
                if isinstance(node, ast.Import):
                    mods.update(a.name for a in node.names)
                if isinstance(node, ast.ImportFrom):
                    mods.add(node.module)
            self.assertEqual(mods, {"json", "re", "datetime"})

    def test_works_when_globals_and_locals_are_separate(self):
        code = build_facts_code(params())
        v = {"now": NOW, "accounts": [CARD]}
        exec(code, {}, {"vars": v})
        self.assertEqual(v["facts_state"], "ok")
        code = build_check_code(params())
        v.update(proposed_date="2026-10-30", current_product="p1")
        exec(code, {}, {"vars": v})
        self.assertEqual(v["check_state"], "ok")

    def test_no_double_braces_in_the_text_written_either(self):
        left, right = "{" + "{", "}" + "}"
        p = params(product_label={"credit_card": "card " + left + "x" + right + " <card_last4>"},
                   bands=[dict(BRIEF_A["bands"][0], name="a" + left + "b", days_late_min=None, days_late_max=None)])
        p["floor_field_by_type"] = {"credit_card": "f" + right, "personal_loan": "z"}
        prod = [dict(CARD, type="credit_card", card_last4="9" + left, minimum_payment=5)]
        prod[0]["product_id"] = "p" + right
        v = facts(prod, p=p)
        for k, val in v.items():
            if isinstance(val, str):
                self.assertNotIn(left, val, k)
                self.assertNotIn(right, val, k)
        c = check(prod, p=p, proposed_date=left + "z" + right, proposed_amount="x" + right, current_product=right)
        for k, val in c.items():
            if isinstance(val, str) and k not in ("proposed_date", "proposed_amount", "current_product"):
                self.assertNotIn(left, val, k)
                self.assertNotIn(right, val, k)

    def test_text_never_holds_double_braces(self):
        for v in (facts(), facts(now="garbage"), check(proposed_date="2026-11-18", proposed_amount="1"),
                  check(now="")):
            for k, val in v.items():
                if isinstance(val, str):
                    self.assertNotIn("{{", val, k)
                    self.assertNotIn("}}", val, k)

    def test_the_snippet_does_not_change_the_input_params(self):
        p = params()
        before = json.dumps(p, sort_keys=True)
        build_facts_code(p)
        build_check_code(p)
        self.assertEqual(json.dumps(p, sort_keys=True), before)


class Params(unittest.TestCase):
    def bad(self, **over):
        p = params()
        p.update(over)
        with self.assertRaises(ValueError):
            build_facts_code(p)
        with self.assertRaises(ValueError):
            build_check_code(p)

    def test_bands_are_required(self):
        with self.assertRaises(ValueError):
            build_facts_code({})
        self.bad(bands=[])
        self.bad(bands=[{"name": "x"}])
        self.bad(bands=[{"name": "x", "deadline": {"kind": "whenever"}}])
        self.bad(bands=[{"name": "x", "deadline": {"kind": "business_days", "n": "3"}}])
        self.bad(bands=[{"name": "x", "deadline": {"kind": "calendar_days", "n": 3, "roll": "sideways"}}])
        self.bad(bands=[{"name": "x", "days_late_min": "1", "deadline": {"kind": "end_of_month"}}])

    def test_other_params_are_checked(self):
        self.bad(holidays=["2026-02-30"])
        self.bad(holidays=["26/10/2026"])
        self.bad(weekend=[7])
        self.bad(weekend=[0, 1, 2, 3, 4, 5, 6])
        self.bad(named_dates=[{"name": "x", "kind": "someday"}])
        self.bad(named_dates=[{"name": "bad name", "kind": "today"}])
        self.bad(named_dates=[{"name": "today", "kind": "today"}])
        self.bad(named_dates=[{"name": "a", "kind": "today"}, {"name": "a", "kind": "today"}])
        self.bad(named_dates=[{"name": "a", "kind": "nth_business_day"}])
        self.bad(callback={"days": ["tomorrow"], "from": "10:00", "to": "19:00"})
        self.bad(callback={"days": ["today"], "from": "25:00", "to": "19:00"})
        self.bad(callback={"days": ["today"], "from": "10:00"})
        self.bad(calendar_days=0)
        self.bad(now_var="")
        self.bad(fields={"id": ""})

    def test_defaults_are_filled(self):
        p = normalize_params({"bands": BRIEF_A["bands"]})
        self.assertEqual((p["now_var"], p["products_var"], p["weekend"], p["calendar_days"], p["callback"]),
                         ("now", "accounts", [5, 6], 21, None))
        self.assertEqual(p["fields"], dates.DEFAULT_FIELDS)

    def test_minimal_params_work_end_to_end(self):
        code = build_facts_code({"bands": BRIEF_A["bands"]})
        v = {"now": NOW, "accounts": [LOAN]}
        run_code(code, v)
        self.assertEqual((v["facts_state"], v["deadline_p2"], v["floor_p2"]), ("ok", "2026-10-30", ""))


class PublicCases(unittest.TestCase):
    """Every promise the practice set expects must pass the shipped check."""

    @classmethod
    def setUpClass(cls):
        path = ROOT / "public-test-set.json"
        cls.cases = json.loads(path.read_text()) if path.exists() else []

    def test_expected_promises_pass_the_checks(self):
        if not self.cases:
            self.skipTest("public-test-set.json not found")
        checked = 0
        for case in self.cases:
            products = []
            for i, prod in enumerate(case["products"]):
                products.append(dict(prod, product_id="p%d" % (i + 1)))
            now = case["variables"]["now"]
            f = facts(products, now=now)
            self.assertEqual(f["facts_state"], "ok", case["id"])
            for promise in case["expected"]["promises"]:
                c = check(products, now=now, proposed_date=promise["date"], proposed_amount=str(promise["amount"]),
                          current_product=promise["product_id"])
                self.assertEqual((c["date_check"], c["amount_check"]), ("ok", "ok"), (case["id"], promise))
                self.assertLessEqual(promise["date"], c["date_check_deadline"], case["id"])
                checked += 1
        self.assertGreater(checked, 10)

    def test_pub_13_two_deadlines_for_one_customer(self):
        case = [c for c in self.cases if c["id"] == "PUB-13"]
        if not case:
            self.skipTest("PUB-13 not found")
        products = [dict(p, product_id="p%d" % (i + 1)) for i, p in enumerate(case[0]["products"])]
        f = facts(products)
        self.assertEqual((f["deadline_p1"], f["deadline_p2"]), ("2026-11-02", "2026-10-23"))
        c = check(products, proposed_date="2026-10-30", current_product="p2")
        self.assertEqual(c["date_check"], "after_deadline")
        self.assertEqual(c["date_check_deadline"], "2026-10-23")


class NothingFromABriefIsHardCoded(unittest.TestCase):
    def test_source_of_the_module(self):
        src = pathlib.Path(dates.__file__).read_text(encoding="utf-8")
        for needle in ("2026-", "2027-", "minimum_payment", "instalment", "installment", "credit_card",
                       "personal_loan", "car_loan", "card_last4", "attempt1", "10:00", "19:00",
                       "persuasion", "customer_id"):
            self.assertNotIn(needle, src, needle)
        # band names: the words early and late alone. days_late is the generic field name.
        for word in re.findall(r"\b(?:early|late)\b", src, flags=re.IGNORECASE):
            self.fail("brief band name in the source: " + word)
        self.assertIn("days_late", src)

    def test_generated_code_without_params_holds_no_brief_value(self):
        bands = [{"name": "only", "deadline": {"kind": "business_days", "n": 3}}]
        for code in (build_facts_code({"bands": bands}), build_check_code({"bands": bands})):
            for needle in ("2026", "minimum_payment", "instalment", "credit_card", "early", "attempt1"):
                self.assertNotIn(needle, code, needle)


if __name__ == "__main__":
    unittest.main()
