"""Regression: the multi-product kit with one slot (examples/multi-brief-a) against the public Brief A customers and
against the single-product agent we measured on Brief A (submission/ours-brief-a.workflow.json).

Offline: the code nodes run for real, the conversation and the bank are played by the test."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.tests.test_multi import account, run  # noqa: E402

CASES = [c for c in json.load(open(ROOT / "public-test-set.json")) if c["brief"] == "A"]
OLD = json.load(open(ROOT / "submission/ours-brief-a.workflow.json"))
OLD = OLD.get("workflow", OLD)["nodes"]


def code_of(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def products_of(case):
    out = []
    for i, p in enumerate(case["products"]):
        out.append(dict(p, product_id="p%d" % (i + 1)))
    return out


class MultiOnBriefA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = pathlib.Path(tempfile.mkdtemp())
        subprocess.run([sys.executable, str(ROOT / "examples/multi-brief-a/gen.py"), str(out)], check=True, capture_output=True)
        with open(out / "workflow.json") as f:
            cls.nodes = json.load(f)["nodes"]

    def start(self, case):
        v = {"now": case["variables"]["now"]}
        account(v, products_of(case))
        self.assertEqual(run(self.nodes, "facts", v), "m_today")
        return v

    def test_facts_agree_with_the_measured_single_product_agent(self):
        for case in CASES:
            if not case["products"]:
                continue
            old = {"now": case["variables"]["now"], "products": products_of(case)}
            exec(code_of(OLD["facts"]), {"vars": old})
            new = self.start(case)
            self.assertEqual(old["facts_state"], "ok", case["id"])
            self.assertEqual(new["s1_band"], old["band"], case["id"])
            self.assertEqual(new["s1_deadline"], old["deadline_iso"], case["id"])
            self.assertEqual(new["end_of_week"], old["attempt1_iso"], case["id"])
            self.assertAlmostEqual(float(new["s1_floor"]), float(old["floor_say"]), msg=case["id"])
            self.assertAlmostEqual(float(new["s1_due"]), float(old["past_due_say"]), msg=case["id"])
            self.assertEqual(new["s1_attempts"], "2" if old["band"] == "late" else "1", case["id"])

    def test_every_expected_promise_survives_the_clamp_and_is_read_back(self):
        for case in CASES:
            for exp in case["expected"]["promises"]:
                v = self.start(case)
                run(self.nodes, "enter_1", v)
                v.update(agreed_date=exp["date"], agreed_amount=str(exp["amount"]), p1_attempt1_full_all="no")
                self.assertEqual(run(self.nodes, "save_1_attempt1_full", v), "m_readback", case["id"])
                self.assertEqual(v["date_1"], exp["date"], case["id"])
                self.assertEqual(v["adj_1"], "", case["id"])
                self.assertAlmostEqual(float(v["amt_1"]), exp["amount"], places=2, msg=case["id"])

    def test_accepting_the_floor_offer_records_the_floor_on_the_attempt_date(self):          # PUB-06
        case = next(c for c in CASES if c["id"] == "PUB-06")
        exp = case["expected"]["promises"][0]
        v = self.start(case)
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="", agreed_amount="", p1_attempt1_floor_all="no")
        run(self.nodes, "save_1_attempt1_floor", v)
        self.assertEqual((float(v["amt_1"]), v["date_1"]), (exp["amount"], exp["date"]))

    def test_a_date_after_the_deadline_is_moved_to_the_deadline(self):                       # PUB-04: asks for later than 23 Oct
        case = next(c for c in CASES if c["id"] == "PUB-04")
        v = self.start(case)
        run(self.nodes, "enter_1", v)
        v.update(agreed_date="2026-11-03", agreed_amount="", p1_attempt1_full_all="no")
        run(self.nodes, "save_1_attempt1_full", v)
        self.assertEqual((v["date_1"], v["adj_1"]), ("2026-10-23", "1"))

    def test_one_product_has_no_notes_and_closes_on_the_right_codes(self):
        for case in CASES:
            exp = case["expected"]
            if case["id"] in ("PUB-02", "PUB-03", "PUB-09") or exp["promises"]:
                continue
            v = self.start(case)
            path = []
            if exp["outcome"] == "paid":
                end = run(self.nodes, "paid_1", v, path=path)
            elif exp["reason"] == "hardship":
                run(self.nodes, "enter_1", v)
                end = run(self.nodes, "hardship_mark", v, path=path)
            else:
                continue
            self.assertNotIn("note_1", path, case["id"])
            self.assertEqual(end, "close_paid" if exp["outcome"] == "paid" else "close_other", case["id"])
            self.assertEqual(v["final_outcome"], exp["outcome"], case["id"])
            self.assertEqual(v.get("final_reason") or None, exp["reason"], case["id"])
        v = self.start(CASES[0])
        v.update(st_1="noted", reason_1="dispute")
        path = []
        self.assertEqual(run(self.nodes, "rg_1", v, path=path), "close_other")
        self.assertNotIn("note_1", path)
        self.assertEqual((v["final_outcome"], v["final_reason"]), ("no_promise", "dispute"))

    def test_restructuring_request_transfers_with_the_right_queue(self):                      # PUB-09
        def body(name):
            return self.nodes[name]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(body("transfer_new_plan")["queue"]["default"], "restructuring")
        close = body("close_new_plan")
        self.assertEqual((close["outcome"]["default"], close["reason"]["default"]), ("transferred", "restructuring"))
        step = self.nodes["p1_attempt1_full"]
        self.assertTrue(any(t["target_node"] == "transfer_new_plan" for t in step["transitions"]))

    def test_tool_failure_gets_a_second_explicit_call_then_closes_service_error(self):       # PUB-10
        v = self.start(next(c for c in CASES if c["id"] == "PUB-10"))
        v.update(st_1="agreed", amt_1="365", date_1="2026-10-16", adj_1="")
        self.assertEqual(run(self.nodes, "rg_1", v), "rec_1")
        first = self.nodes["rec_1"]
        self.assertEqual(first["passthrough_default_transition"], "rec2_1")
        self.assertEqual(self.nodes["rec2_1"]["passthrough_default_transition"], "recfail_1")
        self.assertEqual(run(self.nodes, "recfail_1", v), "close_other")
        self.assertEqual((v["final_outcome"], v["final_reason"]), ("no_promise", "service_error"))
        v2 = self.start(next(c for c in CASES if c["id"] == "PUB-10"))
        v2.update(st_1="agreed", amt_1="365", date_1="2026-10-16", adj_1="")
        run(self.nodes, "rg_1", v2)
        v2["rec2_1_response.data.ok"] = "true"
        self.assertEqual(run(self.nodes, "recok_1", v2), "close_promise")
        self.assertEqual(v2["final_outcome"], "promise")

    def test_statement_for_one_product(self):
        v = self.start(CASES[0])
        self.assertEqual(v["debt_statement"], "Your credit card ending %s has a past-due amount of 420.00 and is 6 days late. Can you make this payment today?"
                         % CASES[0]["products"][0]["card_last4"])


if __name__ == "__main__":
    unittest.main()
