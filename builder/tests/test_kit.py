"""Local tests of the kit. No network.  python3 -m unittest builder.tests.test_kit"""
import json, pathlib, re, unittest

from builder.kit import front, graph as g, pycode
from builder.kit.lint import lint
from builder.kit.openapi import Api

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = Api(ROOT / "tools/openapi.json")
SPEC = json.load(open(ROOT / "builder/tests/fixtures/front-brief-a.json"))


def front_wf():
    nodes = front.build(API, SPEC, after_verify="next")
    nodes["next"] = g.close(API, "next", "no_promise", "refused", "Bye.")
    return {"initial_node": "setup", "nodes": nodes, "global_nodes": {}}


class OpenApiTest(unittest.TestCase):
    def test_ops(self):
        self.assertEqual(len(API.ops), 7)
        self.assertTrue(API.base_url.startswith("https://"))
        self.assertIn("promise", API.enum("close_call", "outcome"))

    def test_tool_bakes_customer_id_and_keeps_enum(self):
        t = API.tool("transfer_to_agent", "d")
        body = t["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(body["customer_id"]["default"], "{{customer_id}}")
        self.assertEqual(body["queue"]["default"], "{{queue}}")
        self.assertTrue(body["queue"]["enum"])

    def test_pre_action_is_literal(self):
        a = API.pre_action("close_call", {"outcome": "x"})
        body = a["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(set(body), {"customer_id", "outcome"})
        self.assertNotIn("description", a["function"])


class CodeTest(unittest.TestCase):
    def test_no_braces(self):
        src = pycode.with_params("x = 1\n", {"a": {"b": [1, {"c": 2}]}})
        self.assertNotIn("{", src)
        self.assertEqual(pycode.run_locally(src + "vars['p'] = P\n", {})["p"], {"a": {"b": [1, {"c": 2}]}})

    def test_callback_window(self):
        src = front_wf()["nodes"]["setup"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        v = pycode.run_locally(src, {"now": "2026-10-23T12:00"})   # Friday before a Monday holiday
        self.assertEqual(v["callback_dates"], "2026-10-23,2026-10-27")
        v = pycode.run_locally(src, {"now": "2026-10-14T19:30"})   # after the window: only the next business day
        self.assertEqual(v["callback_dates"], "2026-10-15")
        v = pycode.run_locally(src, {"now": "garbage"})
        self.assertTrue(v["setup_state"].startswith("error"))


class FrontTest(unittest.TestCase):
    def test_lint_clean(self):
        self.assertEqual(lint(front_wf(), API), [])

    def test_closes_are_literal_and_valid(self):
        nodes = front_wf()["nodes"]
        for kind in front.FRONT_CLOSES:
            n = nodes["close_" + kind]
            body = n["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
            self.assertIn(body["outcome"]["default"], API.enum("close_call", "outcome"))
            self.assertEqual(n["on_enter"]["text"], SPEC["closes"][kind]["farewell"])

    def test_no_hooks_on_tools(self):
        for n in front_wf()["nodes"].values():
            for t in n.get("tools", []):
                self.assertNotIn("post_process_code", t)
                self.assertNotIn("pre_process_code", t)

    def test_question_back_never_repeats_the_security_question(self):
        # B asks_back PUB-12: the spec's purpose line said to ask again and the judge counted a third phone question
        spec = dict(SPEC, purpose_before_verify="Say you can only discuss that once verified, and ask the security question again.",
                    agent_identity="Say you are the bank's digital assistant, then continue.")
        nodes = front.build(API, spec, after_verify="next")
        for name in ("identity", "identity_explain"):
            task = nodes[name]["task_message"]
            self.assertIn(spec["purpose_before_verify"], task)
            self.assertIn("whatever the rule for that question says", task)
            self.assertIn("do not repeat the security question", task)
        for ex in (ROOT / "examples").glob("*/front.json"):
            self.assertNotIn("security question again", ex.read_text(), ex)


class PromiseFailureLintTest(unittest.TestCase):
    def wf(self, fail_to):
        nodes = {"rec": g.api_request("rec", API.pre_action("create_promise", {"product_id": "p1", "amount": 1, "date": "2026-10-16"}),
                                      fail_to, transitions=[g.is_true("ok_close", "rec_response.data.ok", "recorded")]),
                 "ok_close": g.close(API, "ok_close", "promise", None, "Bye."),
                 "fail_close": g.close(API, "fail_close", "no_promise", "service_error", "I could not record it. Bye."),
                 "end": g.end()}
        return {"initial_node": "rec", "nodes": nodes}

    def test_a_failed_promise_may_not_end_where_a_recorded_one_does(self):
        self.assertTrue(any("same step as a recorded one" in e for e in lint(self.wf("ok_close"), API)))
        self.assertFalse(any("same step as a recorded one" in e for e in lint(self.wf("fail_close"), API)))


class NoLeakTest(unittest.TestCase):
    """Builder code and skills must not know a brief. Values of the practice briefs must not appear in them."""
    BANNED = [r"20\d\d-\d\d-\d\d", r"\bdate_of_birth\b", r"\bphone_last4\b", r"\bminimum_payment\b", r"\binstalment_amount\b",
              r"\bnot_reached\b", r"\bnot_verified\b", r"\bno_promise\b", r"\brestructuring\b", r"Freya Bank", r"\b10:00\b", r"\b19:00\b"]

    def test_kit_and_skills(self):
        files = [p for p in (ROOT / "builder").rglob("*.py") if "tests" not in p.parts]
        files += [p for p in (ROOT / ".claude/skills").rglob("*.md") if "build-phone-agent" not in p.parts]
        hits = []
        for p in files:
            text = p.read_text()
            for pat in self.BANNED:
                for m in re.finditer(pat, text):
                    hits.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()


class LadderTest(unittest.TestCase):
    def setUp(self):
        from builder.kit import ladder
        self.ladder = ladder
        self.spec = json.load(open(ROOT / "builder/tests/fixtures/ladder-brief-a.json"))
        self.others = ["close_promise", "close_service_error", "close_paid", "close_dispute", "hardship", "xfer_restructuring", "human_check", "close_refused"]
        self.nodes = ladder.build(API, self.spec, tools=[API.tool("create_promise", "d")])

    def routes(self, step, kind, **vars_):
        """Which node the first matching transition of `step` goes to, for this reply kind and these variables."""
        n = self.nodes["neg_" + step]
        env = {n["name"] + "_turn": kind, **vars_}
        for tr in n["transitions"]:
            for c in tr["condition"].get("conditions", []):
                cs = c.get("conditions", [c])
                if all(str(env.get(x["variable"])) == str(x["operand"]) for x in cs if x["operator"] == "equals") and \
                        all(x["operator"] == "equals" for x in cs):
                    return tr["target_node"]
        return None

    def test_spec_is_consistent(self):
        self.assertEqual(self.ladder.check(self.spec, self.others), [])

    def test_counting_is_in_the_graph(self):
        self.assertEqual(self.routes("ask_today", "refuses"), "neg_attempt1_full")
        self.assertEqual(self.routes("ask_today", "too_much"), "neg_floor_a")
        self.assertEqual(self.routes("floor_a", "refuses"), "neg_attempt1_floor")
        self.assertEqual(self.routes("floor_a", "too_much"), "neg_attempt1_floor")      # falls back to refuses
        self.assertEqual(self.routes("attempt1_floor", "refuses", attempts="2"), "neg_attempt2")
        self.assertEqual(self.routes("attempt1_floor", "refuses", attempts="1"), "close_refused")
        self.assertEqual(self.routes("attempt2", "refuses"), "close_refused")
        self.assertEqual(self.routes("attempt2", "hardship"), "hardship")
        self.assertIsNone(self.routes("attempt2", "chat"))                                 # stays

    def test_lint_clean(self):
        nodes = dict(self.nodes)
        for o in self.others:
            nodes[o] = g.close(API, o, "no_promise", "refused", "Bye.") if o.startswith("close") else g.close(API, o, "transferred", "x", "Bye.")
        nodes["start"] = g.always("neg_ask_today") and g.code("start", "x = 1\n", "neg_ask_today")
        nodes["end"] = g.end()
        self.assertEqual([e for e in lint({"initial_node": "start", "nodes": nodes}, API) if "not reachable" not in e], [])


class ReadListTest(unittest.TestCase):
    def test_flattened_keys(self):
        src = pycode.with_params("vars['out'] = read_list('fetch_account', 'products')\nvars['m'] = money(vars['out'][1]['past_due'])\n", {})
        v = pycode.run_locally(src, {"fetch_account_response.data.products.1.past_due": "310.5", "fetch_account_response.data.products.0.product_id": "p1",
                                     "fetch_account_response.data.products.1.product_id": "p2", "other.products.0.x": "y"})
        self.assertEqual([p["product_id"] for p in v["out"]], ["p1", "p2"])
        self.assertEqual(v["m"], "310.50")

    def test_mapped_json(self):
        src = pycode.with_params("vars['out'] = read_list('n', 'products')\n", {})
        self.assertEqual(pycode.run_locally(src, {"products": '[{"a": 1}]'})["out"], [{"a": 1}])


class RetryTest(unittest.TestCase):
    def test_failed_promise_is_retried_by_the_engine(self):
        from builder.kit import ladder
        spec = json.load(open(ROOT / "builder/tests/fixtures/ladder-brief-a.json"))
        nodes = ladder.build(API, spec, tools=[API.tool("create_promise", "d")])
        trs = nodes["neg_ask_today"]["transitions"]
        self.assertEqual([t["target_node"] for t in trs[:2]], ["close_promise", "neg_retry_record"])
        r = nodes["neg_retry_record"]
        body = r["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(body["amount"]["default"], "{{create_promise_args.amount}}")
        self.assertEqual(r["transitions"][0]["target_node"], "close_promise")
        self.assertEqual(r["passthrough_default_transition"], "close_service_error")
