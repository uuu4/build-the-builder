"""cli compile: expand the agent's plan into a Freya workflow.

    python3 -m builder.cli compile out/<slot>/plan.json --tools out/<slot>/tools.json -o out/<slot>/workflow.json

The agent writes a short plan: which steps the call has, what each step says and may call, and where
each answer leads. This command turns it into the workflow JSON and adds everything that must not be
left to the agent (docs/workflow-format.md, docs/tools-and-code.md):
- full tool definitions from tools.json (the plan names a tool, it never writes one)
- the closing tool at workflow level, with outcome and reason baked from final_outcome/final_reason
- for every end of the call: a code node that writes final_outcome/final_reason, then an end_call node
- conditions in the shapes the engine reads: top-level OR group, both spellings of a boolean,
  counters for tool success and failure
- min_confidence on every extracted value, enum_values, a turn cap with a target on every step
- an "always" exit on every passthrough node, silent entry on code and fetch nodes
- date and amount facts as code (builder.templates.dates), with the parameters from the plan

Plan (see docs/interfaces.md for the full contract):
{
  "system_prompt": "...",
  "start": "<node>",
  "default_on_max": "end:<end>",          # where a step goes when its turn cap is reached
  "dates": {...},                          # parameters for the facts/check code (optional)
  "test_variables": {...},                 # optional, for chat tests
  "nodes":  {"<key>": <talk|fetch|facts|check|set>},
  "global_nodes": {"<key>": <talk|set> + "when", "desc", "excluded"},
  "ends":   {"<end>": {"outcome": "...", "reason": "...", "farewell": "...",
                       "if_tool_ok": {"tool": "create_promise", "outcome": "promise", "reason": ""}}}
}
talk:  {"kind": "talk", "say": "fixed first line" | null, "first_entry_only": bool, "task": "...",
        "loop_prompt": "...", "routing_prompt": "...", "tools": ["name" | {"name", "description", "map"}],
        "extract": [{"name", "type", "enum", "description", "min_confidence", "pattern"}],
        "routes": [{"to": "<node>|end:<end>|__previous__", "when": <cond>, "desc": "...", "tool_call": bool}],
        "max_turns": 30, "on_max": "<target>"}
fetch: {"kind": "fetch", "tool": "get_account", "map": {"data.products": "accounts"}, "next": "...", "on_fail": "..."}
facts: {"kind": "facts", "next": "..."}            check: {"kind": "check", "next": "..."}
set:   {"kind": "set", "vars": {"name": "string value"}, "next": "..."}
cond:  "always" | {"intent": "..."} | {"var": v, "equals"|"not_equals"|"gt"|"lt"|"contains": x}
       | {"var": v, "is_set": true} | {"var": v, "is_set": false} | {"tool_ok": t, "min": 1}
       | {"tool_failed": t, "min": 1} | {"all": [cond, ...]} | {"any": [cond, ...]}
"""
import argparse
import copy
import re

from .common import assert_code_safe, code_literal, event, read_json, write_json

GENERIC_SYSTEM_RULES = (
    "Rules for every step: call at most one tool per message. After every tool result, either speak to the "
    "customer or call the next tool; never end a turn with nothing. Every tool result has a field "
    "what_to_do_next: follow it. Never say that something was recorded or done unless the tool result says it "
    "worked. Do not invent figures, dates or reasons."
)
DEFAULT_MAX_TURNS = 30
DEFAULT_MIN_CONFIDENCE = 0.7
END_PREFIX = "end:"


class PlanError(ValueError):
    pass


# ---------- conditions ----------

def _bool_like(x):
    return isinstance(x, bool) or str(x) in ("true", "True", "false", "False")


def _spellings(x):
    s = str(x).lower() if isinstance(x, bool) else str(x)
    base = "true" if s.lower() == "true" else "false"
    return [base, base.capitalize()]


def _element(c, path):
    """One condition element: a leaf dict or a group."""
    if not isinstance(c, dict):
        raise PlanError(f"{path}: condition must be an object, 'always' or {{'intent': ...}}")
    if "all" in c or "any" in c:
        key = "all" if "all" in c else "any"
        items = c[key]
        if not items:
            raise PlanError(f"{path}: empty {key}")
        return {"logic": "and" if key == "all" else "or",
                "conditions": [_element(x, f"{path}.{key}[{i}]") for i, x in enumerate(items)]}
    if "intent" in c:
        raise PlanError(f"{path}: an intent cannot be combined with variable conditions; use its own route")
    if "tool_ok" in c or "tool_failed" in c:
        tool = c.get("tool_ok") or c.get("tool_failed")
        counter = f"{tool}_success_count" if "tool_ok" in c else f"{tool}_failure_count"
        return {"variable": counter, "operator": "greater_than", "operand": int(c.get("min", 1)) - 1}
    var = c.get("var")
    if not var:
        raise PlanError(f"{path}: condition needs 'var'")
    for key, op in (("equals", "equals"), ("not_equals", "not_equals")):
        if key in c:
            if _bool_like(c[key]):
                spell = _spellings(c[key])
                leaves = [{"variable": var, "operator": op, "operand": s} for s in spell]
                return {"logic": "or" if op == "equals" else "and", "conditions": leaves}
            return {"variable": var, "operator": op, "operand": str(c[key])}
    for key, op in (("gt", "greater_than"), ("lt", "less_than"), ("contains", "contains")):
        if key in c:
            return {"variable": var, "operator": op, "operand": c[key]}
    if "is_set" in c:
        return {"variable": var, "operator": "is_set" if c["is_set"] else "is_not_set"}
    raise PlanError(f"{path}: unknown condition {c}")


def condition(c, path):
    if c in (None, "always") or c == {"always": True}:
        return {"operator": "always"}
    if isinstance(c, dict) and "intent" in c:
        return {"operator": "matches_intent", "description": str(c["intent"])}
    el = _element(c, path)
    if el.get("logic") == "or":
        return el
    return {"logic": "or", "conditions": [el]}


def _describe(c):
    """A short readable description; the routing model reads transition descriptions."""
    if c in (None, "always"):
        return "always"
    if not isinstance(c, dict):
        return str(c)
    if "intent" in c:
        return str(c["intent"])
    if "all" in c or "any" in c:
        key = "all" if "all" in c else "any"
        return (" and " if key == "all" else " or ").join(_describe(x) for x in c[key])
    if "tool_ok" in c:
        return f"{c['tool_ok']} succeeded"
    if "tool_failed" in c:
        return f"{c['tool_failed']} failed"
    var = c.get("var", "?")
    for key, word in (("equals", "is"), ("not_equals", "is not"), ("gt", "is above"), ("lt", "is below"),
                      ("contains", "contains")):
        if key in c:
            return f"{var} {word} {c[key]}"
    if "is_set" in c:
        return f"{var} is {'known' if c['is_set'] else 'not known'}"
    return var


# ---------- compiler ----------

class Compiler:
    def __init__(self, plan, tools):
        self.plan = plan
        self.tools = tools.get("tools", {})
        self.lifecycle = tools.get("lifecycle", [])
        self.baked = set(tools.get("baked", {}))
        self.nodes, self.globals, self.warnings = {}, {}, []
        self.ends_used = []
        self.generated = set()
        self.dates = plan.get("dates")

    # targets
    def target(self, t, path, allow_previous=False):
        if not isinstance(t, str) or not t:
            raise PlanError(f"{path}: missing target")
        if t.startswith(END_PREFIX):
            end = t[len(END_PREFIX):]
            if end not in self.plan.get("ends", {}):
                raise PlanError(f"{path}: unknown end '{end}'")
            if end not in self.ends_used:
                self.ends_used.append(end)
            return f"set_{end}"
        if t == "__previous__":
            if not allow_previous:
                raise PlanError(f"{path}: __previous__ is only allowed in global nodes")
            return t
        if t not in self.plan.get("nodes", {}) and t not in self.plan.get("global_nodes", {}):
            raise PlanError(f"{path}: unknown node '{t}'")
        return t

    def tool(self, ref, path):
        name = ref if isinstance(ref, str) else ref.get("name")
        if name not in self.tools:
            raise PlanError(f"{path}: unknown tool '{name}' (not in tools.json)")
        if name in self.lifecycle:
            raise PlanError(f"{path}: '{name}' runs by itself at the end of the call; do not give it to a step")
        t = copy.deepcopy(self.tools[name])
        if isinstance(ref, dict):
            if ref.get("description"):
                t["function"]["description"] = ref["description"]
            if ref.get("map"):
                t["response_mapping"] = [{"path": p, "variable": v} for p, v in ref["map"].items()]
        return t

    def transitions(self, routes, path, allow_previous=False):
        out = []
        for i, r in enumerate(routes or []):
            p = f"{path}.routes[{i}]"
            tr = {"target_node": self.target(r.get("to"), p, allow_previous),
                  "description": r.get("desc") or _describe(r.get("when")),
                  "condition": condition(r.get("when"), p)}
            if r.get("tool_call"):
                tr["is_tool_call"] = True
            out.append(tr)
        return out

    def extraction(self, items, path):
        out = []
        for i, x in enumerate(items or []):
            if "name" not in x:
                raise PlanError(f"{path}.extract[{i}]: needs a name")
            typ = x.get("type", "string")
            if re.search(r"date", x["name"]) and typ == "string":
                typ = "date"
                self.warnings.append(f"{path}.extract[{i}]: '{x['name']}' made a date type")
            e = {"name": x["name"], "type": typ, "description": x.get("description", ""),
                 "min_confidence": x.get("min_confidence", DEFAULT_MIN_CONFIDENCE)}
            enum = x.get("enum") or x.get("enum_values")
            if enum:
                e["enum_values"] = [str(v) for v in enum]
            if x.get("pattern"):
                e["validation_pattern"] = x["pattern"]
                e["max_retries"] = int(x.get("max_retries", 1))
            out.append(e)
        return out

    def on_enter(self, say):
        if say in (None, "", "llm"):
            return {"type": "llm"}
        if say == "silent":
            return {"type": "silent"}
        return {"type": "tts", "text": str(say)}

    def code_node(self, key, code, nxt, path):
        return self._code_node(key, code, self.target(nxt, f"{path}.next"), path)

    @staticmethod
    def _code_node(key, code, target, path):
        assert_code_safe(code, path)
        return {
            "name": key, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {
                "name": "code_exec", "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": code},
                    "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": [{"target_node": target, "description": "always", "condition": {"operator": "always"}}],
        }

    def talk(self, key, spec, path, is_global=False):
        node = {"name": key, "node_type": "conversation", "on_enter": self.on_enter(spec.get("say")),
                "task_message": spec.get("task") or ""}
        if not node["task_message"]:
            raise PlanError(f"{path}: a talk step needs a task")
        if spec.get("first_entry_only"):
            node["on_enter_first_entry_only"] = True
        for k_plan, k_wf in (("loop_prompt", "loop_prompt"), ("routing_prompt", "routing_prompt"),
                             ("loop_condition", "loop_condition")):
            if spec.get(k_plan):
                node[k_wf] = spec[k_plan]
        tools = [self.tool(t, f"{path}.tools[{i}]") for i, t in enumerate(spec.get("tools") or [])]
        if tools:
            node["tools"] = tools
        ext = self.extraction(spec.get("extract"), path)
        if ext:
            node["extraction_schema"] = ext
        node["transitions"] = self.transitions(spec.get("routes"), path, allow_previous=is_global)
        node["max_node_turns"] = int(spec.get("max_turns", DEFAULT_MAX_TURNS))
        on_max = spec.get("on_max") or self.plan.get("default_on_max")
        if not on_max:
            raise PlanError(f"{path}: needs on_max (or a plan-level default_on_max)")
        node["max_turn_transition"] = self.target(on_max, f"{path}.on_max", allow_previous=is_global)
        if not node["transitions"] and not is_global:
            self.warnings.append(f"{path}: no routes; the step only ends through its turn cap")
        return node

    def fetch(self, key, spec, path):
        t = self.tool(spec.get("tool"), f"{path}.tool")
        body = t["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
        model_filled = [f for f, leaf in body.items()
                        if f not in self.baked and leaf.get("default") == "{{" + f + "}}"]
        if model_filled:
            raise PlanError(f"{path}: a fetch step runs without the model, but these fields need it: {model_filled}")
        nxt = self.target(spec.get("next"), f"{path}.next")
        node = {"name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": nxt,
                "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [t],
                "transitions": []}
        if spec.get("map"):
            node["response_mapping"] = [{"path": p, "variable": v} for p, v in spec["map"].items()]
        if spec.get("on_fail"):
            node["transitions"].append({"target_node": self.target(spec["on_fail"], f"{path}.on_fail"),
                                        "description": "the call failed",
                                        "condition": {"logic": "or", "conditions": [
                                            {"variable": f"{key}_failure_count", "operator": "greater_than", "operand": 0}]}})
        node["transitions"].append({"target_node": nxt, "description": "always", "condition": {"operator": "always"}})
        return node

    @staticmethod
    def set_code(values, guard=None):
        """Code that writes string values into vars. guard: optional (counter, values) applied when counter > 0."""
        for k in list(values) + list((guard or (None, {}))[1]):
            if not re.fullmatch(r"[A-Za-z_]\w*", k):
                raise PlanError(f"set: bad variable name {k!r}")
        lines = ["import json", "try:",
                 f"    _vals = json.loads({code_literal({k: str(v) for k, v in values.items()})})",
                 "    for _k in _vals:", "        vars[_k] = str(_vals[_k])"]
        if guard:
            counter, alt = guard
            lines += ["    try:",
                      f"        _n = float(vars.get(json.loads({code_literal(counter)})) or 0)",
                      "    except Exception:", "        _n = 0",
                      "    if _n > 0:",
                      f"        _alt = json.loads({code_literal({k: str(v) for k, v in alt.items()})})",
                      "        for _k in _alt:", "            vars[_k] = str(_alt[_k])"]
        lines += ["except Exception:", "    pass", ""]
        return "\n".join(lines)

    def build_node(self, key, spec, path, is_global=False):
        kind = spec.get("kind", "talk")
        if kind == "talk":
            return self.talk(key, spec, path, is_global)
        if is_global:
            if kind != "set":
                raise PlanError(f"{path}: a global node is a talk or a set step")
        if kind == "fetch":
            return self.fetch(key, spec, path)
        if kind in ("facts", "check"):
            if not self.dates:
                raise PlanError(f"{path}: a {kind} step needs plan.dates")
            from ..templates import dates as d
            code = d.build_facts_code(self.dates) if kind == "facts" else d.build_check_code(self.dates)
            return self.code_node(key, code, spec.get("next"), path)
        if kind == "set":
            return self.code_node(key, self.set_code(spec.get("vars") or {}), spec.get("next"), path)
        raise PlanError(f"{path}: unknown kind '{kind}'")

    def end_nodes(self):
        enum = None
        for name in self.lifecycle:
            body = self.tools[name]["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
            if "outcome" in body:
                enum = body["outcome"].get("enum")
        for end in self.ends_used:
            spec = self.plan["ends"][end]
            outcome, reason = spec.get("outcome"), spec.get("reason") or ""
            if not outcome:
                raise PlanError(f"ends.{end}: needs an outcome")
            if enum and outcome not in enum:
                raise PlanError(f"ends.{end}: outcome '{outcome}' is not in the tool API ({enum})")
            alt = spec.get("if_tool_ok")
            guard = None
            if alt:
                if enum and alt.get("outcome") not in enum:
                    raise PlanError(f"ends.{end}.if_tool_ok: outcome '{alt.get('outcome')}' is not in the tool API")
                guard = (f"{alt['tool']}_success_count",
                         {"final_outcome": alt["outcome"], "final_reason": alt.get("reason") or ""})
            code = self.set_code({"final_outcome": outcome, "final_reason": reason}, guard)
            set_key, end_key = f"set_{end}", f"end_{end}"
            self.nodes[set_key] = self._code_node(set_key, code, end_key, f"ends.{end}")
            farewell = spec.get("farewell")
            params = {"message_mode": {"type": "string", "default": "custom" if farewell else "none"}}
            if farewell:
                params["spoken_message"] = {"type": "string", "default": str(farewell)}
            self.nodes[end_key] = {
                "name": end_key, "node_type": "end_call", "on_enter": {"type": "silent"},
                "disable_inactivity_monitor": True, "transitions": [],
                "terminal": {"type": "function", "function": {
                    "name": re.sub(r"\W", "_", end), "handler": "__function__:end_call",
                    "parameters": {"type": "object", "properties": params}}},
            }
            self.generated.update({set_key, end_key})

    def compile(self):
        plan = self.plan
        nodes = plan.get("nodes") or {}
        if not nodes:
            raise PlanError("plan.nodes is empty")
        start = plan.get("start")
        if start not in nodes:
            raise PlanError(f"plan.start '{start}' is not a node")
        for key, spec in nodes.items():
            if key.startswith(("set_", "end_")) and key[4:] in plan.get("ends", {}):
                raise PlanError(f"nodes.{key}: name is reserved for a generated end step")
            self.nodes[key] = self.build_node(key, spec, f"nodes.{key}")
        for key, spec in (plan.get("global_nodes") or {}).items():
            node = self.build_node(key, spec, f"global_nodes.{key}", is_global=True)
            node["condition"] = condition(spec.get("when"), f"global_nodes.{key}.when")
            node["description"] = spec.get("desc") or _describe(spec.get("when"))
            if spec.get("tool_call"):
                node["is_tool_call"] = True
            self.globals[key] = node
        self.end_nodes()
        quiet = sorted(k for k, n in self.nodes.items() if n["node_type"] != "conversation")
        for key, node in self.globals.items():
            spec = plan["global_nodes"][key]
            node["excluded_nodes"] = sorted(set(spec.get("excluded") or []) | set(quiet))
        system = (plan.get("system_prompt") or "").strip()
        wf = {
            "initial_node": start,
            "system_prompt": (system + "\n\n" if system else "") + GENERIC_SYSTEM_RULES,
            "nodes": self.nodes,
            "global_nodes": self.globals,
            "tools": [copy.deepcopy(self.tools[n]) for n in self.lifecycle],
        }
        if plan.get("test_variables"):
            wf["test_variables"] = {k: str(v) for k, v in plan["test_variables"].items()}
        if nodes[start].get("kind", "talk") != "talk":
            self.warnings.append("start is not a talk step; the chat route can skip a first code step (docs/api.md)")
        unused = set(plan.get("ends", {})) - set(self.ends_used)
        if unused:
            self.warnings.append(f"ends never reached: {sorted(unused)}")
        return wf


def compile_plan(plan, tools):
    c = Compiler(plan, tools)
    wf = c.compile()
    return wf, c.warnings


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli compile", description=__doc__.split("\n")[0])
    ap.add_argument("plan")
    ap.add_argument("--tools", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    try:
        wf, warnings = compile_plan(read_json(args.plan), read_json(args.tools))
    except PlanError as e:
        print(f"PLAN ERROR: {e}")
        event("cli compile", f"plan error: {e}", [args.plan, args.tools])
        return 1
    write_json(args.out, wf)
    n_conv = sum(1 for n in wf["nodes"].values() if n["node_type"] == "conversation")
    summary = (f"{len(wf['nodes'])} nodes ({n_conv} conversation), {len(wf['global_nodes'])} global, "
               f"{len(wf['tools'])} lifecycle tools, {len(warnings)} warnings")
    event("cli compile", summary, [args.plan, args.tools], args.out, warnings=warnings)
    print(summary)
    for w in warnings:
        print("  warn:", w)
    print(f"-> {args.out}")
    return 0
