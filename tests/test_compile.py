"""Tests for cli compile. Uses the kit's tool API; plan values here are test data only."""
import json
import pathlib
import unittest

from builder.cli.compile import PlanError, compile_plan, condition
from builder.cli.tools import build_tools

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = build_tools(json.loads((ROOT / "tools" / "openapi.json").read_text()))


def plan():
    return {
        "system_prompt": "You are the bank's digital assistant. Speak English.",
        "start": "opening",
        "default_on_max": "end:unclear",
        "nodes": {
            "opening": {"kind": "talk", "say": "Hello, am I speaking with {{title}} {{last_name}}?",
                        "task": "Find out who is on the line. Do not call a tool in this turn.",
                        "extract": [{"name": "party", "enum": ["customer", "other"], "description": "who answered"}],
                        "routes": [{"to": "identity", "when": {"var": "party", "equals": "customer"}},
                                   {"to": "end:unclear", "when": {"var": "party", "equals": "other"}}]},
            "identity": {"kind": "talk", "say": None, "task": "Ask the two questions and call verify_identity.",
                         "tools": ["verify_identity"],
                         "routes": [{"to": "load", "when": {"var": "verify_identity_response.data.all_verified", "equals": True}},
                                    {"to": "end:failed", "when": {"var": "verify_identity_response.data.wrong_answers_left", "equals": "0"}}]},
            "load": {"kind": "fetch", "tool": "get_account", "map": {"data.products": "accounts"},
                     "next": "talk_debt", "on_fail": "end:failed"},
            "talk_debt": {"kind": "talk", "task": "State the debt and get a promise. Call create_promise after a clear yes.",
                          "tools": [{"name": "create_promise", "description": "CALL it after a clear yes."}],
                          "routes": [{"to": "end:promised", "when": {"tool_ok": "create_promise"}},
                                     {"to": "end:refused", "when": {"intent": "The customer refuses to pay"}}],
                          "max_turns": 40},
        },
        "global_nodes": {
            "human": {"kind": "talk", "when": {"intent": "The customer asks for a human"},
                      "task": "Call transfer_to_agent with the general queue.", "tools": ["transfer_to_agent"],
                      "routes": [{"to": "end:human", "when": {"tool_ok": "transfer_to_agent"}},
                                 {"to": "__previous__", "when": "always"}],
                      "excluded": ["opening"]},
        },
        "ends": {
            "promised": {"outcome": "promise", "reason": "", "farewell": "Thank you. Goodbye."},
            "refused": {"outcome": "no_promise", "reason": "refused",
                        "if_tool_ok": {"tool": "create_promise", "outcome": "promise", "reason": ""}},
            "failed": {"outcome": "not_verified", "reason": "failed"},
            "unclear": {"outcome": "not_reached", "reason": "unclear"},
            "human": {"outcome": "transferred", "reason": "human"},
        },
    }


def run_code(node, variables):
    code = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    v = dict(variables)
    exec(code, {"vars": v})
    return v


class Compile(unittest.TestCase):
    def setUp(self):
        self.wf, self.warnings = compile_plan(plan(), TOOLS)

    def test_top_level_shape(self):
        wf = self.wf
        self.assertEqual(wf["initial_node"], "opening")
        self.assertNotIn("agent_config", wf)
        self.assertIn("what_to_do_next", wf["system_prompt"])
        self.assertTrue(wf["system_prompt"].startswith("You are the bank's"))
        self.assertEqual([t["function"]["name"] for t in wf["tools"]], ["close_call"])
        def walk(x, path="wf"):
            self.assertIsNotNone(x, path)
            if isinstance(x, dict):
                for k, v in x.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    walk(v, f"{path}[{i}]")
        walk(wf)
        self.assertEqual(wf["nodes"]["opening"]["transitions"][0]["description"], "party is customer")

    def test_ends_become_set_then_end_nodes(self):
        n = self.wf["nodes"]
        for end in ("promised", "refused", "failed", "unclear", "human"):
            self.assertEqual(n[f"set_{end}"]["node_type"], "code")
            self.assertEqual(n[f"set_{end}"]["transitions"][-1]["target_node"], f"end_{end}")
            self.assertEqual(n[f"end_{end}"]["node_type"], "end_call")
            self.assertEqual(n[f"end_{end}"]["transitions"], [])
        self.assertEqual(n["end_promised"]["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"], "custom")
        self.assertEqual(n["end_failed"]["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"], "none")

    def test_set_code_writes_final_outcome_and_prefers_recorded_promise(self):
        n = self.wf["nodes"]
        v = run_code(n["set_failed"], {})
        self.assertEqual((v["final_outcome"], v["final_reason"]), ("not_verified", "failed"))
        v = run_code(n["set_refused"], {})
        self.assertEqual((v["final_outcome"], v["final_reason"]), ("no_promise", "refused"))
        v = run_code(n["set_refused"], {"create_promise_success_count": "1"})
        self.assertEqual((v["final_outcome"], v["final_reason"]), ("promise", ""))
        for key in ("set_promised", "set_refused"):
            code = n[key]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
            self.assertNotIn("{{", code)
            self.assertNotIn("}}", code)

    def test_tools_come_from_tools_json_with_override(self):
        talk = self.wf["nodes"]["talk_debt"]
        t = talk["tools"][0]
        self.assertEqual(t["function"]["name"], "create_promise")
        self.assertEqual(t["function"]["description"], "CALL it after a clear yes.")
        self.assertIn("post_process_code", t)
        self.assertEqual(t["config"]["maxRetries"], 0)

    def test_fetch_node(self):
        f = self.wf["nodes"]["load"]
        self.assertEqual(f["node_type"], "api_request")
        self.assertTrue(f["passthrough"])
        self.assertEqual(f["response_mapping"], [{"path": "data.products", "variable": "accounts"}])
        self.assertEqual(f["transitions"][0]["condition"]["conditions"][0]["variable"], "load_failure_count")
        self.assertEqual(f["transitions"][-1]["condition"], {"operator": "always"})
        self.assertEqual(f["transitions"][-1]["target_node"], "talk_debt")

    def test_conditions(self):
        tr = self.wf["nodes"]["identity"]["transitions"][0]["condition"]
        self.assertEqual(tr["logic"], "or")
        self.assertEqual(sorted(c["operand"] for c in tr["conditions"]), ["True", "true"])
        ok = self.wf["nodes"]["talk_debt"]["transitions"][0]["condition"]["conditions"][0]
        self.assertEqual(ok, {"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0})
        self.assertEqual(self.wf["nodes"]["talk_debt"]["transitions"][1]["condition"]["operator"], "matches_intent")
        self.assertEqual(condition({"all": [{"var": "a", "equals": "x"}, {"var": "b", "gt": 2}]}, "t"),
                         {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                             {"variable": "a", "operator": "equals", "operand": "x"},
                             {"variable": "b", "operator": "greater_than", "operand": 2}]}]})

    def test_extraction_defaults(self):
        e = self.wf["nodes"]["opening"]["extraction_schema"][0]
        self.assertEqual(e["min_confidence"], 0.7)
        self.assertEqual(e["enum_values"], ["customer", "other"])
        self.assertNotIn("enum", e)

    def test_turn_caps_everywhere(self):
        for key, node in self.wf["nodes"].items():
            if node["node_type"] == "conversation":
                self.assertIn("max_turn_transition", node, key)
        self.assertEqual(self.wf["nodes"]["talk_debt"]["max_node_turns"], 40)
        self.assertEqual(self.wf["nodes"]["opening"]["max_turn_transition"], "set_unclear")

    def test_global_node_excludes_quiet_nodes(self):
        g = self.wf["global_nodes"]["human"]
        self.assertEqual(g["condition"]["operator"], "matches_intent")
        for k in ("opening", "load", "set_promised", "end_promised"):
            self.assertIn(k, g["excluded_nodes"])
        self.assertEqual(g["transitions"][-1]["target_node"], "__previous__")

    def test_plan_errors(self):
        bad = plan(); bad["nodes"]["opening"]["routes"][0]["to"] = "nowhere"
        with self.assertRaises(PlanError):
            compile_plan(bad, TOOLS)
        bad = plan(); bad["nodes"]["talk_debt"]["tools"] = ["close_call"]
        with self.assertRaisesRegex(PlanError, "end of the call"):
            compile_plan(bad, TOOLS)
        bad = plan(); bad["ends"]["failed"]["outcome"] = "maybe"
        with self.assertRaisesRegex(PlanError, "not in the tool API"):
            compile_plan(bad, TOOLS)
        bad = plan(); bad["nodes"]["load"]["tool"] = "create_promise"
        with self.assertRaisesRegex(PlanError, "need it"):
            compile_plan(bad, TOOLS)
        bad = plan(); bad["nodes"]["opening"]["routes"].append({"to": "__previous__", "when": "always"})
        with self.assertRaisesRegex(PlanError, "global"):
            compile_plan(bad, TOOLS)


if __name__ == "__main__":
    unittest.main()
