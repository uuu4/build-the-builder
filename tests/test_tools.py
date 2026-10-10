"""Tests for cli tools against the kit's tool API.

    python3 -m unittest discover -s tests
"""
import json
import pathlib
import unittest

from builder.cli.common import code_literal
from builder.cli.tools import build_tools

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tools" / "openapi.json").read_text())


def run_post(tool, result):
    env = {"result": result}
    exec(tool["post_process_code"], env)
    return env["result"]


def run_pre(tool, body):
    config = {"body": dict(body)}
    exec(tool["pre_process_code"], {"config": config, "vars": {}})
    return config["body"]


class ToolsFromKit(unittest.TestCase):
    def setUp(self):
        self.out = build_tools(SPEC)
        self.t = self.out["tools"]

    def test_all_seven_tools_in_api_order(self):
        names = [p.strip("/") for p in SPEC["paths"]]
        self.assertEqual(self.out["order"], names)
        self.assertEqual(len(names), 7)
        self.assertEqual(self.out["warnings"], [])

    def test_url_method_and_headers_are_baked(self):
        base = SPEC["servers"][0]["url"].rstrip("/")
        for name, tool in self.t.items():
            p = tool["function"]["parameters"]["properties"]
            self.assertEqual(p["url"]["default"], f"{base}/{name}")
            self.assertEqual(p["method"]["default"], "POST")
            self.assertEqual(p["headers"]["properties"]["Content-Type"]["default"], "application/json")
            self.assertEqual(tool["function"]["handler"], "__function__:api_call")
            self.assertNotIn("const", json.dumps(tool))

    def test_customer_id_is_baked_and_hidden_from_required(self):
        for tool in self.t.values():
            body = tool["function"]["parameters"]["properties"]["body"]
            self.assertEqual(body["properties"]["customer_id"], {"type": "string", "default": "{{customer_id}}"})
            self.assertNotIn("customer_id", body["required"])

    def test_model_fields_keep_enum_description_and_required(self):
        body = self.t["verify_identity"]["function"]["parameters"]["properties"]["body"]
        field = body["properties"]["field"]
        self.assertEqual(field["enum"], ["date_of_birth", "phone_last4"])
        self.assertEqual(field["default"], "{{field}}")
        self.assertIn("date_of_birth", field["description"])
        self.assertEqual(sorted(body["required"]), ["answer", "field"])
        date = self.t["create_promise"]["function"]["parameters"]["properties"]["body"]["properties"]["date"]
        self.assertIn("YYYY-MM-DD", date["description"])

    def test_retries_zero_on_writes_two_on_reads(self):
        self.assertEqual(self.t["get_account"]["config"]["maxRetries"], 2)
        for name in ("verify_identity", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call"):
            self.assertEqual(self.t[name]["config"]["maxRetries"], 0, name)

    def test_close_call_is_lifecycle_with_baked_outcome(self):
        cc = self.t["close_call"]
        self.assertEqual(cc["config"]["alwaysRunsAt"], ["end_of_call"])
        props = cc["function"]["parameters"]["properties"]["body"]["properties"]
        self.assertEqual(props["outcome"]["default"], "{{final_outcome}}")
        self.assertEqual(props["reason"]["default"], "{{final_reason}}")
        self.assertEqual(self.out["lifecycle"], ["close_call"])
        for name in self.out["order"]:
            if name != "close_call":
                self.assertNotIn("alwaysRunsAt", self.t[name]["config"])

    def test_no_double_braces_in_any_hook(self):
        for tool in self.t.values():
            for k in ("pre_process_code", "post_process_code"):
                self.assertNotIn("{{", tool[k])
                self.assertNotIn("}}", tool[k])

    def test_code_literal_survives_nested_json_and_braces_in_text(self):
        obj = {"a": {"b": {"c": 1}}, "s": "say {{x}} now"}
        lit = code_literal(obj)
        self.assertNotIn("}}", lit)
        self.assertNotIn("{{", lit)
        back = json.loads(eval(lit))
        self.assertEqual(back["a"]["b"]["c"], 1)


class PostHook(unittest.TestCase):
    def setUp(self):
        self.t = build_tools(SPEC)["tools"]

    def test_success_adds_next_step_and_drops_header(self):
        r = run_post(self.t["create_promise"], {"status": "success", "data": {"ok": True, "promise_id": "x"}, "header": {"a": "b"}})
        self.assertNotIn("header", r)
        self.assertIn("worked", r["data"]["what_to_do_next"])

    def test_failure_says_not_done(self):
        r = run_post(self.t["create_promise"], {"status": "success", "data": {"ok": False, "error": "service unavailable"}})
        self.assertIn("FAILED", r["data"]["what_to_do_next"])
        self.assertIn("service unavailable", r["data"]["what_to_do_next"])

    def test_http_error_without_body_is_a_failure(self):
        r = run_post(self.t["create_promise"], {"status": "error", "data": None, "status_code": 500})
        self.assertFalse(r["data"]["ok"])
        self.assertIn("FAILED", r["data"]["what_to_do_next"])

    def test_string_booleans_are_read(self):
        r = run_post(self.t["create_promise"], {"status": "success", "data": {"ok": "false"}})
        self.assertIn("FAILED", r["data"]["what_to_do_next"])

    def test_negative_fields_are_named(self):
        r = run_post(self.t["verify_identity"], {"status": "success", "data": {"ok": True, "verified": False, "wrong_answers_left": 2}})
        self.assertIn("verified", r["data"]["what_to_do_next"])

    def test_notes_cases_and_placeholders(self):
        notes = {"verify_identity": {"cases": [{"field": "verified", "equals": False, "next": "Wrong. <wrong_answers_left> left."}],
                                     "on_ok": "Correct."}}
        t = build_tools(SPEC, notes)["tools"]["verify_identity"]
        r = run_post(t, {"status": "success", "data": {"ok": "true", "verified": "false", "wrong_answers_left": 1}})
        self.assertEqual(r["data"]["what_to_do_next"], "Wrong. 1 left.")
        r = run_post(t, {"status": "success", "data": {"ok": True, "verified": True}})
        self.assertEqual(r["data"]["what_to_do_next"], "Correct.")

    def test_field_notes_reach_the_leaf(self):
        t = build_tools(SPEC, {"create_promise": {"fields": {"product_id": "Copy product_id from get_account."}}})["tools"]
        leaf = t["create_promise"]["function"]["parameters"]["properties"]["body"]["properties"]["product_id"]
        self.assertEqual(leaf["description"], "Copy product_id from get_account.")

    def test_hook_never_raises_on_odd_input(self):
        for odd in (None, "text", 5, {"data": "text"}, {"data": {"ok": None}}):
            run_post(self.t["get_account"], odd)


class PreHook(unittest.TestCase):
    def setUp(self):
        self.t = build_tools(SPEC)["tools"]

    def test_unresolved_optional_fields_are_dropped(self):
        body = run_pre(self.t["close_call"], {"customer_id": "c1", "outcome": "promise", "reason": "{{final_reason}}"})
        self.assertEqual(body, {"customer_id": "c1", "outcome": "promise"})
        body = run_pre(self.t["close_call"], {"customer_id": "c1", "outcome": "no_promise", "reason": "hardship"})
        self.assertEqual(body["reason"], "hardship")

    def test_required_fields_are_kept_even_if_empty(self):
        body = run_pre(self.t["create_promise"], {"customer_id": "c1", "product_id": "", "amount": 10, "date": "2026-10-16"})
        self.assertIn("product_id", body)


if __name__ == "__main__":
    unittest.main()
