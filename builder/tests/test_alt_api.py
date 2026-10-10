"""What does the kit assume about the bank's tool API? Build the examples against an API with every name changed."""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.tests import alt_api  # noqa: E402
from builder.tests.test_multi import account, holds, run  # noqa: E402

# names that belong to the original bank only
OLD_TOKENS = ["verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call",
              "customer_id", "product_id", "date_of_birth", "phone_last4", "wrong_answers_left", "all_verified", "data.ok",
              "no_promise", "not_verified", "not_reached", "transferred", "minimum_payment", "instalment_amount", "card_last4"]


def build(example):
    tmp = pathlib.Path(tempfile.mkdtemp())
    front, multi, dates = alt_api.alt_specs(example)
    (tmp / "front.json").write_text(json.dumps(front))
    (tmp / "multi.json").write_text(json.dumps(multi))
    (tmp / "dates.json").write_text(json.dumps(dates))
    (tmp / "openapi.json").write_text(json.dumps(alt_api.alt_openapi()))
    env = dict(os.environ, SPEC_DIR=str(tmp), TOOL_API=str(tmp / "openapi.json"))
    r = subprocess.run([sys.executable, str(ROOT / "examples" / example / "gen.py"), str(tmp / "out")], capture_output=True, text=True, env=env)
    return r, tmp


class AltApi(unittest.TestCase):
    def check(self, example):
        r, tmp = build(example)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("lint: clean", r.stdout)
        text = open(tmp / "out" / "workflow.json").read()
        leaks = [t for t in OLD_TOKENS if re.search(r"(?<![A-Za-z0-9_])" + re.escape(t) + r"(?![A-Za-z0-9_])", text)]
        self.assertEqual(leaks, [], "the generated workflow still contains names of the original bank")
        return json.load(open(tmp / "out" / "workflow.json"))["nodes"]

    def test_brief_b_shaped_example(self):
        nodes = self.check("multi-brief-b")
        v = {"now": "2026-10-14T11:00"}
        account(v, alt_api.alt_products([
            dict(product_id="p1", type="credit_card", card_last4="6604", past_due=300.0, days_late=4, minimum_payment=90.0),
            dict(product_id="p2", type="personal_loan", past_due=900.0, days_late=20, instalment_amount=300.0)]))
        self.assertEqual(run(nodes, "facts", v), "m_today")
        self.assertEqual((v["s1_deadline"], v["s2_deadline"], v["s2_floor"]), ("2026-11-02", "2026-10-23", "300.00"))

    def test_brief_a_shaped_example(self):
        self.check("multi-brief-a")


class FrontSpec(unittest.TestCase):
    def test_a_missing_part_is_named(self):
        from builder.kit import front
        from builder.kit.openapi import Api
        spec = json.load(open(ROOT / "examples/multi-brief-b/front.json"))
        spec["third_party"].pop("callback")
        spec.pop("human")
        with self.assertRaises(ValueError) as cm:
            front.build(Api(str(ROOT / "tools/openapi.json")), spec, "next")
        self.assertIn("third_party.callback", str(cm.exception))
        self.assertIn("human.queue", str(cm.exception))

    def test_calendar_is_optional(self):
        from builder.kit import front
        from builder.kit.openapi import Api
        spec = json.load(open(ROOT / "examples/multi-brief-b/front.json"))
        spec.pop("calendar")
        self.assertIn("setup", front.build(Api(str(ROOT / "tools/openapi.json")), spec, "next"))


if __name__ == "__main__":
    unittest.main()
