"""Local tests of the multi-product back half: the code nodes are run for real, the conversation and api nodes are
played by the test (it sets the variables the platform's extraction or the bank's reply would set)."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.kit import dates  # noqa: E402


def load_workflow():
    out = pathlib.Path(tempfile.mkdtemp())
    subprocess.run([sys.executable, str(ROOT / "examples/multi-brief-b/gen.py"), str(out)], check=True, capture_output=True)
    return json.load(open(out / "workflow.json"))["nodes"]


def holds(cond, vars_):
    op = cond.get("operator")
    if op == "always":
        return True
    if "variable" in cond:
        v = vars_.get(cond["variable"])
        if op == "equals":
            return str(v) == str(cond["operand"])
        if op == "is_not_set":
            return v is None
        if op == "greater_than":
            try:
                return float(v) > float(cond["operand"])
            except (TypeError, ValueError):
                return False
        raise AssertionError("operator " + str(op))
    results = [holds(c, vars_) for c in cond["conditions"]]
    return all(results) if cond.get("logic") == "and" else any(results)


def run(nodes, name, vars_, limit=60):
    """Follow code nodes from `name` until a node that is not code. Returns the name of that node."""
    for _ in range(limit):
        n = nodes[name]
        if n["node_type"] != "code":
            return name
        src = n["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        exec(src, {"vars": vars_})
        for tr in n["transitions"]:
            if holds(tr["condition"], vars_):
                name = tr["target_node"]
                break
    raise AssertionError("loop")


def account(vars_, products):
    for i, p in enumerate(products):
        for k, x in p.items():
            vars_[f"fetch_account_response.data.products.{i}.{k}"] = x


CARD = dict(product_id="p1", type="credit_card", card_last4="6604", past_due=300.0, days_late=4, minimum_payment=90.0)
LOAN = dict(product_id="p2", type="personal_loan", past_due=900.0, days_late=20, instalment_amount=300.0)
CAR = dict(product_id="p3", type="car_loan", past_due=75.0, days_late=3, instalment_amount=25.0)


class MultiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nodes = load_workflow()

    def start(self, products, now="2026-10-14T11:00"):
        v = {"now": now}
        account(v, products)
        self.assertEqual(run(self.nodes, "facts", v), "m_today")
        self.assertEqual(v["facts_state"], "ok")
        return v

    def test_statement_names_every_product(self):
        v = self.start([CARD, LOAN, CAR])
        self.assertEqual(v["debt_statement"].count("past-due amount"), 3)
        self.assertTrue(v["debt_statement"].endswith("Can you pay all of them today?"))
        self.assertTrue(self.start([CARD])["debt_statement"].endswith("Can you make this payment today?"))

    def test_one_date_for_both_is_moved_to_the_loans_own_deadline(self):          # PUB-13
        v = self.start([CARD, LOAN])
        self.assertEqual(run(self.nodes, "enter_1", v), "p1_attempt1_full")
        v.update(agreed_date="2026-10-30", agreed_amount="", **{"p1_attempt1_full_all": "yes"})
        self.assertEqual(run(self.nodes, "save_1_attempt1_full", v), "m_readback")
        self.assertEqual((v["date_1"], v["date_2"], v["adj_1"], v["adj_2"]), ("2026-10-30", "2026-10-23", "", "1"))
        self.assertEqual((v["amt_1"], v["amt_2"]), ("300", "900"))
        self.assertIn("Friday 23 October 2026 (the latest date I can record for it)", v["readback"])
        self.assertNotIn("30 October 2026 (the latest", v["readback"])
        self.assertTrue(v["readback"].endswith("Do you confirm?"))

    def test_date_without_for_all_asks_the_next_product(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="2026-10-15", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        self.assertEqual(run(self.nodes, "save_1_attempt1_full", v), "p2_attempt1_full")
        self.assertEqual(v["date_1"], "2026-10-15")

    def test_yes_to_an_offer_uses_the_offered_amount_and_date(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="", agreed_amount="", **{"p1_attempt1_floor_all": "no"})
        run(self.nodes, "save_1_attempt1_floor", v)
        self.assertEqual((v["amt_1"], v["date_1"]), ("90", "2026-10-16"))

    def test_stale_extraction_does_not_leak_to_the_next_product(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="2026-10-20", agreed_amount="250", **{"p1_attempt1_full_all": "no"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual(v["agreed_date"], "")
        run(self.nodes, "enter_2", v)
        run(self.nodes, "save_2_attempt1_full", v)
        self.assertEqual((v["amt_2"], v["date_2"]), ("900", "2026-10-16"))

    def test_refusals_attempts_follow_the_band(self):                             # PUB-12
        v = self.start([dict(CARD, days_late=16, past_due=510.0, minimum_payment=153.0), dict(LOAN, days_late=16), dict(CAR, days_late=7, past_due=140.0)])
        self.assertEqual(v["s1_attempts"], "2")
        self.assertEqual(v["s3_attempts"], "1")
        step = self.nodes["p3_attempt1_full"]
        refuse = [t for t in step["transitions"] if "refuses" in t["description"]]
        self.assertEqual(len(refuse), 2)
        targets = []
        for t in refuse:
            c = t["condition"]
            targets.append((t["target_node"], json.dumps(c)))
        self.assertTrue(any(t == "p3_attempt2" and "s3_attempts" in c for t, c in targets))
        self.assertTrue(any(t == "refused_3" for t, c in targets))

    def test_record_stage_notes_and_outcome(self):                               # PUB-12 end to end, after the read-back
        v = self.start([dict(CARD, days_late=16, past_due=510.0), dict(LOAN, days_late=16), dict(CAR, days_late=7, past_due=140.0)])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="2026-10-15", agreed_amount="", **{"p1_attempt1_full_all": "no"})
        self.assertEqual(run(self.nodes, "save_1_attempt1_full", v), "p2_attempt1_full")
        self.assertEqual(run(self.nodes, "refused_2", v), "p3_attempt1_full")
        self.assertEqual(run(self.nodes, "refused_3", v), "m_readback")
        self.assertEqual(v["readback"].count("For your"), 1)
        self.assertEqual(run(self.nodes, "rg_1", v), "rec_1")
        v["rec_1_response.data.ok"] = "true"
        self.assertEqual(run(self.nodes, "recok_1", v), "note_2")
        self.assertEqual(v["reason_2"], "refused")
        self.assertEqual(run(self.nodes, "rg_3", v), "note_3")
        self.assertEqual(run(self.nodes, "final", v), "close_promise")
        self.assertEqual(v["final_outcome"], "promise")

    def test_failed_promise_is_noted_and_other_promise_stays(self):
        v = self.start([CARD, LOAN])
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="2026-10-16", **{"p1_attempt1_full_all": "yes"})
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual(run(self.nodes, "rg_1", v), "rec_1")
        v["rec_1_response.data.ok"] = "true"
        run(self.nodes, "recok_1", v)
        self.assertEqual(run(self.nodes, "rg_2", v), "rec_2")
        self.assertEqual(run(self.nodes, "recfail_2", v), "note_2")
        self.assertEqual(v["reason_2"], "service_error")
        self.assertEqual(run(self.nodes, "final", v), "close_promise")

    def test_all_noted_paid_closes_paid_and_first_other_reason_wins(self):
        v = self.start([CARD, LOAN, CAR])
        for k in (1, 2, 3):
            v["st_%d" % k] = "noted"
            v["reason_%d" % k] = "paid"
        self.assertEqual(run(self.nodes, "final", v), "close_paid")
        v["reason_2"] = "dispute"
        v["reason_3"] = "refused"
        self.assertEqual(run(self.nodes, "final", v), "close_other")
        self.assertEqual(v["final_reason"], "dispute")

    def test_hardship_decline_notes_only_products_without_an_answer(self):
        v = self.start([CARD, LOAN, CAR])
        v.update(st_1="agreed", amt_1="300", date_1="2026-10-16", adj_1="", st_2="noted", reason_2="dispute")
        self.assertEqual(run(self.nodes, "hardship_mark", v), "m_readback")
        self.assertEqual((v["reason_2"], v["reason_3"], v["st_1"]), ("dispute", "hardship", "agreed"))

    def test_read_back_change_is_applied_and_clamped(self):
        v = self.start([CARD, LOAN])
        v.update(st_1="agreed", amt_1="300", date_1="2026-10-16", adj_1="", st_2="agreed", amt_2="900", date_2="2026-10-16", adj_2="")
        v.update(fix_kind="change", fix_slot="2", fix_date="2026-10-30", fix_amount="")
        self.assertEqual(run(self.nodes, "apply_fix", v), "m_readback")
        self.assertEqual((v["date_2"], v["adj_2"], v["date_1"]), ("2026-10-23", "1", "2026-10-16"))
        v.update(fix_kind="drop", fix_slot="1")
        run(self.nodes, "apply_fix", v)
        self.assertEqual(v["st_1"], "noted")
        self.assertEqual(v["readback"].count("For your"), 1)

    def test_workflow_stays_under_the_node_limit(self):
        self.assertLess(len(self.nodes), 200)


if __name__ == "__main__":
    unittest.main()
