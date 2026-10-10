"""Tests for cli lint.

    python3 -m unittest discover -s tests
"""
import contextlib
import copy
import io
import json
import pathlib
import tempfile
import unittest

from builder.cli import lint
from builder.cli.lint import lint_workflow
from builder.cli.tools import build_tools

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "tools" / "openapi.json").read_text())
BASE = json.loads((ROOT / "examples" / "base-agent.json").read_text())

FINISH_CODE = (
    "try:\n"
    "    if vars.get('create_promise_success_count'):\n"
    "        vars['final_outcome'] = 'promise'\n"
    "        vars['final_reason'] = ''\n"
    "    else:\n"
    "        vars['final_outcome'] = 'no_promise'\n"
    "        vars['final_reason'] = 'refused'\n"
    "except Exception:\n"
    "    vars['final_outcome'] = 'no_promise'\n"
    "    vars['final_reason'] = 'refused'\n"
)


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def good_workflow():
    """conversation -> code -> end_call, tools from cli tools, close_call at workflow level."""
    tools = copy.deepcopy(build_tools(SPEC)["tools"])
    return {
        "initial_node": "negotiate",
        "system_prompt": "You are the phone assistant of Freya Bank. Speak English, one or two short sentences.",
        "test_variables": {"customer_id": "c_test", "now": "2026-10-14T11:00"},
        "nodes": {
            "negotiate": {
                "name": "negotiate",
                "node_type": "conversation",
                "on_enter": {"type": "tts", "text": "Hello, this is Freya Bank."},
                "task_message": ("Call get_account once, tell the customer the amount that is late and ask when they "
                                 "can pay. Read the amount and the date back, and call create_promise after a clear yes."),
                "tools": [tools["get_account"], tools["create_promise"]],
                "extraction_schema": [
                    {"name": "next_action", "type": "string", "enum_values": ["pay", "refuse", "unclear"],
                     "description": "What the customer chose", "min_confidence": 0.7},
                    {"name": "promised_day", "type": "date", "description": "Day the customer will pay",
                     "min_confidence": 0.7},
                ],
                "max_node_turns": 20,
                "max_turn_transition": "goodbye",
                "transitions": [
                    {"target_node": "finish", "description": "The promise was recorded",
                     "condition": {"logic": "or", "conditions": [
                         {"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}]}},
                    {"target_node": "finish", "description": "The customer refuses",
                     "condition": {"logic": "or", "conditions": [
                         {"variable": "next_action", "operator": "equals", "operand": "refuse"}]}},
                    always("negotiate"),
                ],
            },
            "finish": {
                "name": "finish",
                "node_type": "code",
                "passthrough": True,
                "passthrough_default_transition": "goodbye",
                "on_enter": {"type": "silent"},
                "pre_actions": [{
                    "type": "function",
                    "function": {
                        "name": "code_exec",
                        "handler": "__function__:code_exec",
                        "parameters": {"type": "object", "properties": {
                            "code": {"type": "string", "default": FINISH_CODE},
                            "timeout_ms": {"type": "number", "default": 10000}}},
                    },
                }],
                "transitions": [always("goodbye")],
            },
            "goodbye": {
                "name": "goodbye",
                "node_type": "end_call",
                "on_enter": {"type": "silent"},
                "disable_inactivity_monitor": True,
                "transitions": [],
                "terminal": {"type": "function", "function": {
                    "name": "closing_end",
                    "handler": "__function__:end_call",
                    "parameters": {"type": "object", "properties": {
                        "message_mode": {"type": "string", "default": "custom"},
                        "spoken_message": {"type": "string", "default": "Goodbye."}}}}},
            },
        },
        "global_nodes": {},
        "tools": [tools["close_call"]],
    }


def hits(report, kind, path_part, msg_part=""):
    return [i for i in report[kind] if path_part in i["path"] and msg_part in i["msg"]]


class LintCase(unittest.TestCase):
    def assertError(self, wf, path_part, msg_part="", **kw):
        report = lint_workflow(wf, **kw)
        self.assertTrue(hits(report, "errors", path_part, msg_part),
                        "no error at %r containing %r; got %r" % (path_part, msg_part, report["errors"]))
        return report

    def assertWarning(self, wf, path_part, msg_part="", **kw):
        report = lint_workflow(wf, **kw)
        self.assertTrue(hits(report, "warnings", path_part, msg_part),
                        "no warning at %r containing %r; got %r" % (path_part, msg_part, report["warnings"]))
        return report


class GoodWorkflows(LintCase):
    def test_base_agent_has_no_errors(self):
        report = lint_workflow(BASE)
        self.assertEqual(report["errors"], [], msg=report["errors"])
        self.assertIsInstance(report["warnings"], list)
        self.assertEqual(report["stats"], {"nodes": 2, "global_nodes": 0, "tools": 6, "code_nodes": 0, "end_nodes": 0})

    def test_base_agent_strict_shows_what_lenient_hides(self):
        report = lint_workflow(BASE, lenient=False)
        paths = sorted(e["path"] for e in report["errors"])
        self.assertEqual(paths, sorted([
            "nodes.identity.max_turn_transition", "nodes.identity.max_turn_transition",
            "nodes.identity.passthrough_default_transition",
            "nodes.collection.max_turn_transition", "nodes.collection.max_turn_transition",
            "nodes.collection.passthrough_default_transition",
            "nodes.identity.tools[0].post_process_code",
            "nodes.collection.tools[0].post_process_code", "nodes.collection.tools[1].post_process_code",
        ]))

    def test_good_workflow_has_no_errors(self):
        report = lint_workflow(good_workflow())
        self.assertEqual(report["errors"], [], msg=report["errors"])
        self.assertEqual(report["warnings"], [], msg=report["warnings"])
        self.assertEqual(report["stats"], {"nodes": 3, "global_nodes": 0, "tools": 4, "code_nodes": 1, "end_nodes": 1})

    def test_wrapped_workflow_is_accepted(self):
        report = lint_workflow({"name": "agent", "workflow": good_workflow()})
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["stats"]["nodes"], 3)

    def test_every_tool_from_cli_tools_lints_clean(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["tools"] = [t for k, t in copy.deepcopy(build_tools(SPEC)["tools"]).items()
                                             if k != "close_call"]
        wf["nodes"]["negotiate"]["task_message"] = " ".join(
            "Use %s when needed." % t["function"]["name"] for t in wf["nodes"]["negotiate"]["tools"])
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])


class StructureErrors(LintCase):
    def test_missing_initial_node(self):
        wf = good_workflow()
        del wf["initial_node"]
        self.assertError(wf, "initial_node", "missing")

    def test_initial_node_not_a_key(self):
        wf = good_workflow()
        wf["initial_node"] = "nowhere"
        self.assertError(wf, "initial_node", "not a key of nodes")

    def test_empty_nodes(self):
        wf = good_workflow()
        wf["nodes"] = {}
        self.assertError(wf, "nodes", "non-empty")

    def test_null_value_anywhere(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["role_message"] = None
        self.assertError(wf, "nodes.negotiate.role_message", "null")
        wf = good_workflow()
        wf["nodes"]["negotiate"]["tools"][0]["function"]["parameters"]["properties"]["url"]["default"] = None
        self.assertError(wf, "nodes.negotiate.tools[0].function.parameters.properties.url.default", "null")

    def test_agent_config(self):
        wf = good_workflow()
        wf["agent_config"] = {"model": "x"}
        self.assertError(wf, "agent_config", "remove agent_config")

    def test_node_name_must_equal_key(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["name"] = "other"
        self.assertError(wf, "nodes.finish.name", "must equal the node key")

    def test_node_type_missing_and_unknown(self):
        wf = good_workflow()
        del wf["nodes"]["finish"]["node_type"]
        self.assertError(wf, "nodes.finish.node_type", "missing")
        wf = good_workflow()
        wf["nodes"]["finish"]["node_type"] = "transfer_call"
        self.assertWarning(wf, "nodes.finish.node_type", "transfer_call")

    def test_key_not_snake_case_warns(self):
        wf = good_workflow()
        wf["nodes"]["Finish-Up"] = wf["nodes"].pop("finish")
        wf["nodes"]["Finish-Up"]["name"] = "Finish-Up"
        wf["nodes"]["negotiate"]["transitions"][0]["target_node"] = "Finish-Up"
        wf["nodes"]["negotiate"]["transitions"][1]["target_node"] = "Finish-Up"
        report = self.assertWarning(wf, "nodes.Finish-Up", "snake_case")
        self.assertEqual(report["errors"], [])


class TransitionErrors(LintCase):
    def test_bad_target(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["target_node"] = "nope"
        self.assertError(wf, "nodes.negotiate.transitions[0].target_node", "does not exist")

    def test_previous_only_in_global_nodes(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["target_node"] = "__previous__"
        self.assertError(wf, "nodes.negotiate.transitions[0].target_node", "__previous__")

    def test_target_may_be_a_global_node(self):
        wf = good_workflow()
        wf["global_nodes"]["escalate"] = dict(copy.deepcopy(wf["nodes"]["goodbye"]), name="escalate",
                                              condition={"operator": "matches_intent", "description": "wants a human"})
        wf["nodes"]["negotiate"]["transitions"][0]["target_node"] = "escalate"
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])

    def test_top_level_and_group(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["condition"]["logic"] = "and"
        self.assertError(wf, "nodes.negotiate.transitions[0].condition.logic", 'top-level group must use logic "or"')

    def test_nested_and_group_is_fine(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["condition"] = {"logic": "or", "conditions": [
            {"logic": "and", "conditions": [
                {"variable": "next_action", "operator": "equals", "operand": "pay"},
                {"variable": "promised_day", "operator": "is_set"}]}]}
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])

    def test_condition_shapes(self):
        wf = good_workflow()
        tr = wf["nodes"]["negotiate"]["transitions"]
        tr[0]["condition"] = {"operator": "matches_intent"}
        self.assertError(wf, "transitions[0].condition.description", "matches_intent needs a description")
        tr[0]["condition"] = {"logic": "or", "conditions": [{"variable": "x", "operator": "equals"}]}
        self.assertError(wf, "transitions[0].condition.conditions[0].operand", "needs an operand")
        tr[0]["condition"] = {"logic": "or", "conditions": [{"operator": "is_set"}]}
        self.assertError(wf, "transitions[0].condition.conditions[0].variable", "needs a variable")
        tr[0]["condition"] = {"logic": "or", "conditions": [{"variable": "x", "operator": "like", "operand": "a"}]}
        self.assertError(wf, "transitions[0].condition.conditions[0].operator", "unknown operator")
        tr[0]["condition"] = {"logic": "or", "conditions": []}
        self.assertError(wf, "transitions[0].condition.conditions", "non-empty")
        del tr[0]["condition"]
        self.assertError(wf, "transitions[0].condition", "no condition")

    def test_bare_variable_condition_is_valid(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][1]["condition"] = {
            "variable": "next_action", "operator": "equals", "operand": "refuse"}
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])

    def test_boolean_routing_warns_without_both_spellings(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["condition"] = {"logic": "or", "conditions": [
            {"variable": "booking_ok", "operator": "equals", "operand": "true"}]}
        report = self.assertWarning(wf, "transitions[0].condition.conditions[0]", "routing on a boolean")
        self.assertEqual(report["errors"], [])
        wf["nodes"]["negotiate"]["transitions"][0]["condition"]["conditions"].append(
            {"variable": "booking_ok", "operator": "equals", "operand": "True"})
        self.assertEqual(hits(lint_workflow(wf), "warnings", "transitions[0]", "boolean"), [])

    def test_boolean_not_equals_needs_and_group(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][0]["condition"] = {"logic": "or", "conditions": [
            {"logic": "and", "conditions": [
                {"variable": "ok", "operator": "not_equals", "operand": "false"},
                {"variable": "ok", "operator": "not_equals", "operand": "False"}]}]}
        self.assertEqual(hits(lint_workflow(wf), "warnings", "transitions[0]", "boolean"), [])
        wf["nodes"]["negotiate"]["transitions"][0]["condition"]["conditions"][0]["conditions"].pop()
        self.assertWarning(wf, "transitions[0]", "boolean")

    def test_bare_boolean_leaf_warns(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"][1]["condition"] = {
            "variable": "ok", "operator": "equals", "operand": "True"}
        self.assertWarning(wf, "transitions[1].condition", "boolean")

    def test_max_turn_transition_target_is_checked(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["max_turn_transition"] = "nope"
        self.assertError(wf, "nodes.negotiate.max_turn_transition", "does not exist")


class NodeShapeErrors(LintCase):
    def test_dead_end_node(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"] = []
        self.assertError(wf, "nodes.negotiate.transitions", "dead end")

    def test_end_tool_makes_a_node_no_dead_end(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["transitions"] = []
        wf["nodes"]["negotiate"]["tools"].append(copy.deepcopy(BASE["nodes"]["identity"]["tools"][1]))
        report = lint_workflow(wf)
        self.assertEqual(hits(report, "errors", "negotiate"), [], msg=report["errors"])

    def test_global_node_returning_previous_is_no_dead_end(self):
        wf = good_workflow()
        wf["global_nodes"]["off_topic"] = {
            "name": "off_topic", "node_type": "conversation", "description": "redirect",
            "condition": {"operator": "matches_intent", "description": "unrelated"},
            "task_message": "Bring the customer back to the subject.", "on_enter": {"type": "tts", "text": "Back to the subject."},
            "passthrough": True, "passthrough_default_transition": "__previous__", "excluded_nodes": ["goodbye"],
            "transitions": [always("__previous__")]}
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])
        self.assertEqual(report["stats"]["global_nodes"], 1)
        wf["global_nodes"]["off_topic"]["passthrough"] = False
        wf["global_nodes"]["off_topic"]["transitions"] = []
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [])  # still returns via passthrough_default_transition

    def test_end_call_node_rules(self):
        wf = good_workflow()
        wf["nodes"]["goodbye"]["transitions"] = [always("negotiate")]
        self.assertError(wf, "nodes.goodbye.transitions", "transitions == []")
        wf = good_workflow()
        del wf["nodes"]["goodbye"]["terminal"]
        self.assertError(wf, "nodes.goodbye.terminal", "__function__:end_call")
        wf = good_workflow()
        wf["nodes"]["goodbye"]["terminal"]["function"]["handler"] = "__function__:api_call"
        self.assertError(wf, "nodes.goodbye.terminal", "__function__:end_call")
        wf = good_workflow()
        wf["nodes"]["goodbye"]["disable_inactivity_monitor"] = False
        wf["nodes"]["goodbye"]["on_enter"] = {"type": "tts", "text": "bye"}
        self.assertWarning(wf, "nodes.goodbye.disable_inactivity_monitor")
        self.assertWarning(wf, "nodes.goodbye.on_enter", "silent")

    def test_passthrough_without_final_always(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["transitions"] = [{
            "target_node": "goodbye", "description": "x",
            "condition": {"logic": "or", "conditions": [{"variable": "a", "operator": "is_set"}]}}]
        self.assertError(wf, "nodes.finish.transitions[0]", "must be")

    def test_passthrough_needs_default_transition(self):
        wf = good_workflow()
        del wf["nodes"]["finish"]["passthrough_default_transition"]
        self.assertError(wf, "nodes.finish.passthrough_default_transition", "needs passthrough_default_transition")
        wf["nodes"]["finish"]["passthrough_default_transition"] = "nope"
        self.assertError(wf, "nodes.finish.passthrough_default_transition", "does not exist")

    def test_passthrough_without_transitions_is_an_error(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["transitions"] = []
        self.assertError(wf, "nodes.finish.transitions", "passthrough")

    def test_tools_on_code_node(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["tools"] = [copy.deepcopy(wf["nodes"]["negotiate"]["tools"][0])]
        self.assertError(wf, "nodes.finish.tools", "stripped silently")

    def test_pre_actions_on_conversation_node(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["pre_actions"] = copy.deepcopy(wf["nodes"]["finish"]["pre_actions"])
        self.assertError(wf, "nodes.negotiate.pre_actions", "stripped silently")

    def test_empty_tools_and_pre_actions_are_fine(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["tools"] = []
        wf["nodes"]["negotiate"]["pre_actions"] = []
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])

    def test_max_node_turns_without_transition(self):
        wf = good_workflow()
        del wf["nodes"]["negotiate"]["max_turn_transition"]
        self.assertError(wf, "nodes.negotiate.max_turn_transition", "max_node_turns is set")
        wf["nodes"]["negotiate"]["max_turn_transition"] = None
        self.assertError(wf, "nodes.negotiate.max_turn_transition", "max_node_turns is set")

    def test_unreachable_node_and_no_path_to_end_warn(self):
        wf = good_workflow()
        wf["nodes"]["island"] = dict(copy.deepcopy(wf["nodes"]["goodbye"]), name="island")
        self.assertWarning(wf, "nodes.island", "not reachable")
        wf = good_workflow()
        wf["nodes"]["loop_a"] = {"name": "loop_a", "node_type": "conversation", "task_message": "Talk.",
                                 "transitions": [always("loop_a")]}
        wf["nodes"]["negotiate"]["transitions"].insert(0, {
            "target_node": "loop_a", "description": "x",
            "condition": {"logic": "or", "conditions": [{"variable": "z", "operator": "is_set"}]}})
        self.assertWarning(wf, "nodes.loop_a", "no path")

    def test_code_node_as_initial_node_warns(self):
        wf = good_workflow()
        wf["initial_node"] = "finish"
        self.assertWarning(wf, "initial_node", "code node")


class ToolErrors(LintCase):
    def tool(self, wf):
        return wf["nodes"]["negotiate"]["tools"][1]  # create_promise

    def test_missing_handler(self):
        wf = good_workflow()
        del self.tool(wf)["function"]["handler"]
        self.assertError(wf, "nodes.negotiate.tools[1].function.handler", "missing")

    def test_url_and_method_need_default(self):
        wf = good_workflow()
        props = self.tool(wf)["function"]["parameters"]["properties"]
        del props["url"]["default"]
        del props["method"]["default"]
        self.assertError(wf, "tools[1].function.parameters.properties.url.default", "URL is required")
        self.assertError(wf, "tools[1].function.parameters.properties.method.default")

    def test_const_in_tool(self):
        wf = good_workflow()
        props = self.tool(wf)["function"]["parameters"]["properties"]
        props["url"] = {"type": "string", "const": "https://x.example/v1/promise"}
        report = self.assertError(wf, "tools[1].function.parameters.properties.url.const", "const")
        self.assertTrue(hits(report, "errors", "url.default"))

    def test_a_body_field_called_const_is_not_a_const(self):
        wf = good_workflow()
        self.tool(wf)["function"]["parameters"]["properties"]["body"]["properties"]["const"] = {
            "type": "string", "default": "{{const}}"}
        report = lint_workflow(wf)
        self.assertEqual(hits(report, "errors", "const"), [])

    def test_body_leaf_needs_default(self):
        wf = good_workflow()
        del self.tool(wf)["function"]["parameters"]["properties"]["body"]["properties"]["amount"]["default"]
        self.assertError(wf, "body.properties.amount.default", "no default")

    def test_nested_body_leaf_needs_default(self):
        wf = good_workflow()
        body = self.tool(wf)["function"]["parameters"]["properties"]["body"]["properties"]
        body["address"] = {"type": "object", "properties": {"city": {"type": "string"}}}
        self.assertError(wf, "body.properties.address.properties.city.default", "no default")

    def test_field_spec_next_to_body_default(self):
        wf = good_workflow()
        props = self.tool(wf)["function"]["parameters"]["properties"]
        props["body"] = {"type": "object", "default": {"amount": "{{amount}}"}}
        props["amount"] = {"type": "number", "description": "How much"}
        self.assertError(wf, "tools[1].function.parameters.properties.amount", "body.default")

    def test_missing_post_hook(self):
        wf = good_workflow()
        del self.tool(wf)["post_process_code"]
        self.assertError(wf, "nodes.negotiate.tools[1].post_process_code", "no post hook")

    def test_post_hook_without_what_to_do_next_warns(self):
        wf = good_workflow()
        self.tool(wf)["post_process_code"] = "try:\n    result.pop('header', None)\nexcept Exception:\n    pass\n"
        report = self.assertWarning(wf, "nodes.negotiate.tools[1].post_process_code", "what_to_do_next")
        self.assertEqual(report["errors"], [])

    def test_lifecycle_tool_needs_no_post_hook(self):
        wf = good_workflow()
        wf["tools"][0].pop("post_process_code", None)
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])

    def test_hooks_must_compile_and_have_no_braces(self):
        wf = good_workflow()
        self.tool(wf)["post_process_code"] = "d = {'a': {'b': 1}}\nresult['data']['what_to_do_next'] = 'x'\n"
        self.assertError(wf, "nodes.negotiate.tools[1].post_process_code", "'}}'")
        wf = good_workflow()
        self.tool(wf)["pre_process_code"] = "x = (\n"
        self.assertError(wf, "nodes.negotiate.tools[1].pre_process_code", "does not compile")
        wf = good_workflow()
        self.tool(wf)["pre_process_code"] = "vars['a'] = '{{b}}'\n"
        self.assertError(wf, "nodes.negotiate.tools[1].pre_process_code", "'{{'")

    def test_write_tool_with_retries(self):
        wf = good_workflow()
        self.tool(wf)["config"]["maxRetries"] = 2
        self.assertError(wf, "nodes.negotiate.tools[1].config.maxRetries", "create_promise")

    def test_get_tool_may_retry(self):
        wf = good_workflow()
        self.assertEqual(wf["nodes"]["negotiate"]["tools"][0]["config"]["maxRetries"], 2)
        self.assertEqual(lint_workflow(wf)["errors"], [])

    def test_write_tool_without_max_retries_warns(self):
        wf = good_workflow()
        del self.tool(wf)["config"]["maxRetries"]
        self.assertWarning(wf, "nodes.negotiate.tools[1].config.maxRetries", "set 0")

    def test_pre_actions_tools_are_checked_too(self):
        wf = good_workflow()
        wf["nodes"]["fetch"] = {
            "name": "fetch", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "goodbye",
            "on_enter": {"type": "silent"}, "pre_actions": [copy.deepcopy(wf["nodes"]["negotiate"]["tools"][0])],
            "transitions": [always("goodbye")]}
        wf["nodes"]["fetch"]["pre_actions"][0].pop("post_process_code")
        wf["nodes"]["negotiate"]["transitions"][1]["target_node"] = "fetch"
        self.assertError(wf, "nodes.fetch.pre_actions[0].post_process_code", "no post hook")


class WorkflowToolErrors(LintCase):
    def test_workflow_tool_without_always_runs_at(self):
        wf = good_workflow()
        del wf["tools"][0]["config"]["alwaysRunsAt"]
        self.assertError(wf, "tools[0].config.alwaysRunsAt", "never runs")
        wf["tools"][0]["config"]["alwaysRunsAt"] = []
        self.assertError(wf, "tools[0].config.alwaysRunsAt", "never runs")

    def test_each_turn_is_not_implemented(self):
        wf = good_workflow()
        wf["tools"][0]["config"]["alwaysRunsAt"] = ["end_of_call", "each_turn"]
        self.assertError(wf, "tools[0].config.alwaysRunsAt", "not implemented")

    def test_lifecycle_tool_missing_or_not_at_end_of_call(self):
        wf = good_workflow()
        wf["tools"] = []
        self.assertError(wf, "tools", "close_call")
        wf = good_workflow()
        wf["tools"][0]["config"]["alwaysRunsAt"] = ["start_of_call"]
        self.assertError(wf, "tools[0].config.alwaysRunsAt", "end_of_call")

    def test_lifecycle_names_are_configurable(self):
        wf = good_workflow()
        wf["tools"] = []
        self.assertEqual(lint_workflow(wf, lifecycle=())["errors"], [])
        self.assertError(wf, "tools", "close_call", lifecycle=("close_call",))
        self.assertError(wf, "tools", "wrap_up", lifecycle=("wrap_up",))

    def test_lifecycle_defaults_warn(self):
        wf = good_workflow()
        body = wf["tools"][0]["function"]["parameters"]["properties"]["body"]["properties"]
        body["outcome"]["default"] = "{{outcome}}"
        body["reason"]["default"] = "{{reason}}"
        report = self.assertWarning(wf, "body.properties.outcome.default", "{{final_outcome}}")
        self.assertTrue(hits(report, "warnings", "body.properties.reason.default", "{{final_reason}}"))
        self.assertEqual(report["errors"], [])

    def test_final_outcome_never_written_warns(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = "pass\n"
        self.assertWarning(wf, "tools[0]", "never writes final_outcome")
        wf["nodes"]["finish"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = \
            'vars["final_outcome"] = "promise"\n'
        self.assertEqual(hits(lint_workflow(wf), "warnings", "tools[0]", "never writes final_outcome"), [])


class CodeNodeErrors(LintCase):
    def code_prop(self, wf):
        return wf["nodes"]["finish"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]

    def test_code_with_double_brace(self):
        wf = good_workflow()
        self.code_prop(wf)["default"] = "x = {'a': {'b': 1}}\nvars['final_outcome'] = 'promise'\n"
        self.assertError(wf, "nodes.finish.pre_actions[0].function.parameters.properties.code.default", "'}}'")

    def test_code_does_not_compile(self):
        wf = good_workflow()
        self.code_prop(wf)["default"] = "def broken(:\n"
        self.assertError(wf, "nodes.finish.pre_actions[0]", "does not compile")

    def test_code_must_be_a_string(self):
        wf = good_workflow()
        del self.code_prop(wf)["default"]
        self.assertError(wf, "nodes.finish.pre_actions[0]", "non-empty string")

    def test_code_node_needs_code_exec(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["pre_actions"] = []
        self.assertError(wf, "nodes.finish.pre_actions", "code_exec")

    def test_code_node_must_be_passthrough(self):
        wf = good_workflow()
        wf["nodes"]["finish"]["passthrough"] = False
        self.assertError(wf, "nodes.finish.passthrough", "passthrough")


class ExtractionErrors(LintCase):
    def items(self, wf):
        return wf["nodes"]["negotiate"]["extraction_schema"]

    def test_missing_min_confidence(self):
        wf = good_workflow()
        del self.items(wf)[0]["min_confidence"]
        self.assertError(wf, "nodes.negotiate.extraction_schema[0].min_confidence", "0.95")

    def test_min_confidence_range(self):
        wf = good_workflow()
        self.items(wf)[0]["min_confidence"] = 7
        self.assertError(wf, "extraction_schema[0].min_confidence", "0 to 1")

    def test_type_and_name(self):
        wf = good_workflow()
        self.items(wf)[0]["type"] = "enum"
        del self.items(wf)[1]["name"]
        self.assertError(wf, "extraction_schema[0].type", "not one of")
        self.assertError(wf, "extraction_schema[1].name")

    def test_warnings(self):
        wf = good_workflow()
        self.items(wf)[0]["enum"] = ["a", "b"]
        self.items(wf)[0]["extraction_prompt"] = "custom"
        self.items(wf)[1]["type"] = "string"
        self.assertWarning(wf, "extraction_schema[0].enum", "enum_values")
        self.assertWarning(wf, "extraction_schema[0].extraction_prompt", "replaces")
        self.assertWarning(wf, "extraction_schema[1].type", "date")

    def test_update_is_not_a_date(self):
        wf = good_workflow()
        self.items(wf)[0]["name"] = "last_update"
        self.assertEqual(hits(lint_workflow(wf), "warnings", "extraction_schema[0].type"), [])


class CollisionErrors(LintCase):
    def test_extraction_collides_with_model_filled_field(self):
        wf = good_workflow()
        # create_promise.amount is model-filled ({{amount}}); an extraction named amount would bake it
        wf["nodes"]["negotiate"]["extraction_schema"].append(
            {"name": "amount", "type": "float", "description": "Amount", "min_confidence": 0.7})
        self.assertError(wf, "tools[1].function.parameters.properties.body.properties.amount.default",
                         "the model never sees it")

    def test_response_mapping_collides(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["tools"][0]["response_mapping"] = [{"path": "data.products", "variable": "product_id"}]
        self.assertError(wf, "body.properties.product_id.default", "response_mapping")

    def test_code_write_collides(self):
        wf = good_workflow()
        code = wf["nodes"]["finish"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
        code["default"] += "vars['date'] = '2026-10-16'\n"
        self.assertError(wf, "body.properties.date.default", "code in")

    def test_test_variable_collides_except_customer_id(self):
        wf = good_workflow()
        self.assertEqual(lint_workflow(wf)["errors"], [])  # customer_id is in test_variables and baked on purpose
        wf["test_variables"]["product_id"] = "p1"
        self.assertError(wf, "body.properties.product_id.default", "test_variables")

    def test_lifecycle_fields_and_other_names_are_fine(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["extraction_schema"].append(
            {"name": "final_outcome", "type": "string", "description": "x", "min_confidence": 0.7})
        report = lint_workflow(wf)
        self.assertEqual(report["errors"], [], msg=report["errors"])


class PromptWarnings(LintCase):
    def test_empty_task_message(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["task_message"] = "  "
        self.assertError(wf, "nodes.negotiate.task_message", "empty")
        del wf["nodes"]["negotiate"]["task_message"]
        self.assertError(wf, "nodes.negotiate.task_message", "empty")

    def test_task_message_names_another_node(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["task_message"] += " Then move on to finish."
        self.assertWarning(wf, "nodes.negotiate.task_message", "'finish'")
        # a longer word is not a match, a placeholder is not a mention
        wf["nodes"]["negotiate"]["task_message"] = wf["nodes"]["negotiate"]["task_message"].replace(
            "Then move on to finish.", "Do not hurry, nothing is finished yet. Say {{finish}}.")
        self.assertEqual(hits(lint_workflow(wf), "warnings", "task_message", "names the node"), [])

    def test_task_message_skips_a_tool(self):
        wf = good_workflow()
        wf["nodes"]["negotiate"]["task_message"] = "Talk to the customer about the late amount."
        report = self.assertWarning(wf, "nodes.negotiate.task_message", "'get_account'")
        self.assertTrue(hits(report, "warnings", "nodes.negotiate.task_message", "'create_promise'"))
        self.assertEqual(report["errors"], [])

    def test_context_variables_warns(self):
        wf = good_workflow()
        wf["context_variables"] = {"items": []}
        self.assertWarning(wf, "context_variables", "dropped")


class Robustness(LintCase):
    def test_odd_values_never_raise(self):
        junk = [None, 0, -3, "", "x", [], {}, [1], {"a": 1}, True, 2.5, ["a"], {"logic": "or"}, [{"x": 1}],
                {"conditions": [1, None]}, {"operator": "equals", "operand": {}}]
        spots = [
            ("initial_node",), ("nodes",), ("tools",), ("test_variables",), ("global_nodes",),
            ("nodes", "negotiate", "transitions"), ("nodes", "negotiate", "transitions", 0, "condition"),
            ("nodes", "negotiate", "transitions", 0, "target_node"), ("nodes", "negotiate", "tools"),
            ("nodes", "negotiate", "tools", 1, "function"), ("nodes", "negotiate", "tools", 1, "config"),
            ("nodes", "negotiate", "extraction_schema"), ("nodes", "negotiate", "extraction_schema", 0),
            ("nodes", "negotiate", "max_node_turns"), ("nodes", "negotiate", "task_message"),
            ("nodes", "finish", "pre_actions"), ("nodes", "finish", "pre_actions", 0, "function"),
            ("nodes", "goodbye", "terminal"), ("nodes", "goodbye", "transitions"), ("tools", 0, "config"),
            ("tools", 0, "function", "parameters"),
        ]
        for spot in spots:
            for value in junk:
                wf = good_workflow()
                parent = wf
                for k in spot[:-1]:
                    parent = parent[k]
                parent[spot[-1]] = copy.deepcopy(value)
                for mode in (None, False, True):
                    report = lint_workflow(wf, lenient=mode)
                    self.assertEqual(sorted(report), ["errors", "stats", "warnings"])
                    json.dumps(report)


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lint.main(argv)
        return code, out.getvalue(), err.getvalue()

    def write(self, tmp, name, obj):
        p = pathlib.Path(tmp) / name
        p.write_text(json.dumps(obj))
        return str(p)

    def test_clean_workflow_returns_zero_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            wf = self.write(tmp, "wf.json", good_workflow())
            rep = str(pathlib.Path(tmp) / "out" / "report.json")
            code, out, _ = self.run_main([wf, "-o", rep])
            self.assertEqual(code, 0, msg=out)
            report = json.loads(pathlib.Path(rep).read_text())
            self.assertEqual(sorted(report), ["errors", "stats", "warnings"])
            self.assertEqual(report["errors"], [])
            self.assertIn("0 errors", out.splitlines()[0])

    def test_workflow_with_errors_returns_one(self):
        bad = good_workflow()
        bad["agent_config"] = {}
        bad["nodes"]["negotiate"]["transitions"][0]["target_node"] = "nope"
        with tempfile.TemporaryDirectory() as tmp:
            wf = self.write(tmp, "wf.json", {"name": "x", "workflow": bad})
            code, out, _ = self.run_main([wf])
            self.assertEqual(code, 1)
            self.assertIn("ERROR agent_config", out)
            self.assertIn("ERROR nodes.negotiate.transitions[0].target_node", out)

    def test_base_agent_returns_zero_and_strict_returns_one(self):
        base = str(ROOT / "examples" / "base-agent.json")
        self.assertEqual(self.run_main([base])[0], 0)
        self.assertEqual(self.run_main([base, "--strict"])[0], 1)

    def test_lifecycle_option(self):
        wf = good_workflow()
        wf["tools"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "wf.json", wf)
            self.assertEqual(self.run_main([path])[0], 1)
            self.assertEqual(self.run_main([path, "--lifecycle", "none"])[0], 0)
            self.assertEqual(self.run_main([path, "--lifecycle", "wrap_up,close_call"])[0], 1)

    def test_unreadable_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_main([str(pathlib.Path(tmp) / "missing.json")])[0], 2)
            p = pathlib.Path(tmp) / "bad.json"
            p.write_text("{not json")
            rep = str(pathlib.Path(tmp) / "r.json")
            code, out, _ = self.run_main([str(p), "-o", rep])
            self.assertEqual(code, 1)
            self.assertEqual(len(json.loads(pathlib.Path(rep).read_text())["errors"]), 1)

    def test_registered_in_the_command_table(self):
        from builder.cli.__main__ import COMMANDS
        self.assertEqual(COMMANDS["lint"], "builder.cli.lint")

    def test_non_object_workflow(self):
        report = lint_workflow([1, 2])
        self.assertEqual(len(report["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
