"""cli lint: check a Freya workflow JSON before it goes to the platform. Local, seconds, no network.

    python3 -m builder.cli lint <workflow.json> [-o report.json] [--lifecycle close_call] [--strict | --lenient]

Accepts a bare workflow object or {"name": ..., "workflow": {...}}. The platform strips or drops invalid
things without an error (tools on a code node, a `const` url, a missing post hook ...), so this is the
only early warning. Rules come from docs/workflow-format.md and docs/tools-and-code.md.

Report: {"errors": [{"path", "msg"}], "warnings": [...], "stats": {...}}. Exit code 1 if there are errors.
Paths look like nodes.identity.transitions[0].target_node, tools[0].config.alwaysRunsAt.

  ERRORS   initial_node/nodes, agent_config, null, node name/type, transition targets and condition shape,
           end_call nodes, dead ends, passthrough nodes, tools/pre_actions placement, max_node_turns,
           tool parameters (handler, url/method default, no const, body leaves with default), hooks (no
           braces, compile, post hook), retries on writing tools, lifecycle tools, code nodes,
           extraction (type, min_confidence), baking collisions, empty task_message
  WARNINGS reachability and paths to an end node, boolean routing, snake_case, enum/extraction_prompt,
           date-like names not typed date, prompts that name nodes or skip a tool, lifecycle defaults,
           final_outcome never written, code node as initial_node

--lifecycle names the lifecycle tools (default close_call; repeat or comma-separate; "none" turns the
check off). `--lenient` / `--strict`: workflows exported by the platform itself (the base agent: nodes carry
`position`) hold JSON null, max_node_turns without max_turn_transition and api_call tools without a post
hook. Auto-detected lenient mode reports exactly those three as warnings, everything else is unchanged.
`--strict` turns that off. Builder output is always strict.

Judgement calls (the tool-doc rules left these open):
- a lifecycle tool (alwaysRunsAt) needs no post hook: the model never sees its result
- an `__function__:end_call` tool in a node's tools lets the model end the call, so the node is no dead end
  and counts as a path to the end; its name is not required in task_message
- read-only = name starts with get_, or the method default is GET (cli tools does the same)
- a test_variables key equal to a model-filled body field is a collision, except customer_id (BAKED_ON_PURPOSE)
"""
import argparse
import re
import sys

from .common import event, read_json, write_json

NODE_TYPES = ("conversation", "api_request", "code", "end_call")
EXTRACTION_TYPES = ("string", "integer", "float", "boolean", "date", "datetime", "name", "phone_number")
VALUE_OPS = ("equals", "not_equals", "greater_than", "less_than", "contains")
FLAG_OPS = ("is_set", "is_not_set")
OPERATORS = VALUE_OPS + FLAG_OPS + ("always", "matches_intent")
ALWAYS_RUNS_AT = ("start_of_call", "end_of_call", "each_turn")
API_CALL = "__function__:api_call"
CODE_EXEC = "__function__:code_exec"
END_HANDLER = "__function__:end_call"
RESERVED_PARAMS = ("url", "method", "headers", "body", "connect_retries")
BAKED_ON_PURPOSE = ("customer_id",)
BOOL_OTHER = {"true": "True", "True": "true", "false": "False", "False": "false"}
DEFAULT_LIFECYCLE = ("close_call",)

SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
ONE_VAR = re.compile(r"^\{\{\s*([A-Za-z_]\w*)\s*\}\}$")
PLACEHOLDER = re.compile(r"\{\{.*?\}\}", re.S)
VARS_WRITE = re.compile(r"""vars\s*\[\s*(['"])([A-Za-z_]\w*)\1\s*\]\s*[-+*/%|&^]?=(?!=)""")
DATE_TOKENS = ("date", "day", "birthday", "dob")


def _dict_key(name):
    # {"final_outcome": ...} inside a code string: how cli compile hands values to vars
    return re.compile(r"""\\?['"]""" + re.escape(name) + r"""\\?['"]\s*:""")


def _str(x):
    return isinstance(x, str) and x.strip() != ""


def _j(prefix, key):
    return str(key) if not prefix else prefix + "." + str(key)


def _ix(prefix, i):
    return "%s[%d]" % (prefix, i)


def _list(x):
    return x if isinstance(x, list) else []


def _dict(x):
    return x if isinstance(x, dict) else {}


def _word(key, text):
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])", text) is not None


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_export(wf):
    """The platform's own export carries the editor layout: `position` on nodes, or `nodePositions`."""
    if "nodePositions" in wf:
        return True
    for group in (wf.get("nodes"), wf.get("global_nodes")):
        for n in _dict(group).values():
            if isinstance(n, dict) and "position" in n:
                return True
    return False


class _Linter:
    def __init__(self, wf, lifecycle, lenient):
        if isinstance(wf, dict) and isinstance(wf.get("workflow"), dict) and "nodes" not in wf:
            wf = wf["workflow"]
        self.wf = wf
        self.lifecycle = tuple(lifecycle)
        self.lenient = lenient
        self.errors, self.warnings = [], []
        self.nodes, self.gnodes = {}, {}
        self.node_items = []   # (path, key, node, is_global)
        self.tool_entries = []  # (path, tool, kind, node_type)
        self.written = {}      # variable name -> where the workflow writes it
        self.code_strings = []  # every Python string in the workflow

    # ---- reporting -------------------------------------------------------------------------
    def err(self, path, msg):
        self.errors.append({"path": path, "msg": msg})

    def warn(self, path, msg):
        self.warnings.append({"path": path, "msg": msg})

    def soft(self, path, msg):
        """An error, except that a platform export may carry it: then a warning."""
        if self.lenient:
            self.warn(path, msg + " (lenient: platform export)")
        else:
            self.err(path, msg)

    # ---- driver ----------------------------------------------------------------------------
    def run(self):
        wf = self.wf
        if not isinstance(wf, dict):
            self.err("", "the workflow must be a JSON object")
            return self.report()
        if self.lenient is None:
            self.lenient = _is_export(wf)
        self.check_top()
        self.collect()
        for path, key, node, is_global in self.node_items:
            self.check_node(path, key, node, is_global)
        for path, tool, kind, node_type in self.tool_entries:
            self.check_tool(path, tool, kind)
        self.check_workflow_tools()
        self.check_graph()
        self.check_collisions()
        return self.report()

    def report(self):
        seen, errors, warnings = set(), [], []
        for src, dst in ((self.errors, errors), (self.warnings, warnings)):
            for item in src:
                k = (item["path"], item["msg"])
                if k not in seen:
                    seen.add(k)
                    dst.append(item)
        nodes = list(self.nodes.values()) + list(self.gnodes.values())
        stats = {
            "nodes": len(self.nodes),
            "global_nodes": len(self.gnodes),
            "tools": len(self.tool_entries),
            "code_nodes": sum(1 for n in nodes if n.get("node_type") == "code"),
            "end_nodes": sum(1 for n in nodes if n.get("node_type") == "end_call"),
        }
        return {"errors": errors, "warnings": warnings, "stats": stats}

    # ---- rules 1, 2: structure -------------------------------------------------------------
    def check_top(self):
        wf = self.wf
        nodes = wf.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            self.err("nodes", "nodes must be a non-empty object")
        init = wf.get("initial_node")
        if not _str(init):
            self.err("initial_node", "initial_node is missing")
        elif isinstance(nodes, dict) and init not in nodes:
            self.err("initial_node", "initial_node %r is not a key of nodes" % init)
        elif isinstance(nodes, dict) and isinstance(nodes.get(init), dict) and nodes[init].get("node_type") == "code":
            self.warn("initial_node", "initial_node is a code node: the chat route can skip a first code step "
                      "(docs/api.md), so the values it computes can be empty")
        if "agent_config" in wf:
            self.err("agent_config", "remove agent_config: the platform fills in its defaults")
        if "context_variables" in wf:
            self.warn("context_variables", "the platform dropped this key on save in a test; write the values "
                      "into the prompts with {{variable}} instead")
        if "global_nodes" in wf and not isinstance(wf.get("global_nodes"), dict):
            self.err("global_nodes", "global_nodes must be an object")
        if "test_variables" in wf and not isinstance(wf.get("test_variables"), dict):
            self.err("test_variables", "test_variables must be an object")
        if "tools" in wf and not isinstance(wf.get("tools"), list):
            self.err("tools", "workflow-level tools must be a list")
        self.walk_nulls(wf, "")

    def walk_nulls(self, obj, path):
        if obj is None:
            self.soft(path, "null value: the schema is strict; leave the key out (or use \"\" for a string)")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                self.walk_nulls(v, _j(path, k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self.walk_nulls(v, _ix(path, i))

    # ---- collect nodes, tools, written variables -------------------------------------------
    def collect(self):
        wf = self.wf
        for group, is_global, base in ((wf.get("nodes"), False, "nodes"), (wf.get("global_nodes"), True, "global_nodes")):
            if not isinstance(group, dict):
                continue
            for key, node in group.items():
                path = _j(base, key)
                if not isinstance(node, dict):
                    self.err(path, "a node must be an object")
                    continue
                (self.gnodes if is_global else self.nodes)[key] = node
                self.node_items.append((path, key, node, is_global))
                for field in ("tools", "pre_actions"):
                    val = node.get(field)
                    if val is not None and not isinstance(val, list):
                        self.err(_j(path, field), "%s must be a list" % field)
                    for i, t in enumerate(_list(val)):
                        self.tool_entries.append((_ix(_j(path, field), i), t, field, node.get("node_type")))
        for i, t in enumerate(_list(wf.get("tools"))):
            self.tool_entries.append((_ix("tools", i), t, "workflow", None))
        self.collect_written()

    def collect_written(self):
        def add(name, where):
            if _str(name):
                self.written.setdefault(name, []).append(where)

        for path, key, node, is_global in self.node_items:
            for item in _list(node.get("extraction_schema")):
                if isinstance(item, dict):
                    add(item.get("name"), "an extraction in %s" % path)
            for m in _list(node.get("response_mapping")):
                if isinstance(m, dict):
                    add(m.get("variable"), "a response_mapping in %s" % path)
        for path, tool, kind, node_type in self.tool_entries:
            if not isinstance(tool, dict):
                continue
            for m in _list(tool.get("response_mapping")):
                if isinstance(m, dict):
                    add(m.get("variable"), "a response_mapping in %s" % path)
            for sub, code in self.tool_code(tool):
                self.code_strings.append(code)
                for m in VARS_WRITE.finditer(code):
                    add(m.group(2), "code in %s.%s" % (path, sub))
        for k in _dict(self.wf.get("test_variables")):
            add(k, "test_variables")

    @staticmethod
    def tool_code(tool):
        """(subpath, code) for every Python string a tool carries."""
        out = []
        for k in ("pre_process_code", "post_process_code"):
            if _str(tool.get(k)):
                out.append((k, tool[k]))
        code = _dict(_dict(_dict(_dict(tool.get("function")).get("parameters")).get("properties")).get("code")).get("default")
        if _str(code):
            out.append(("function.parameters.properties.code.default", code))
        return out

    # ---- nodes: rules 3, 6, 7, 8, 9, 15, 16, 18 ---------------------------------------------
    def check_node(self, path, key, node, is_global):
        nt = node.get("node_type")
        if node.get("name") != key:
            self.err(_j(path, "name"), "name %r must equal the node key %r" % (node.get("name"), key))
        if not _str(nt):
            self.err(_j(path, "node_type"), "node_type is missing")
        elif nt not in NODE_TYPES:
            self.warn(_j(path, "node_type"), "node_type %r is not used by this builder (%s)" % (nt, ", ".join(NODE_TYPES)))
        if not SNAKE.match(str(key)):
            self.warn(path, "node key %r should be snake_case" % key)
        # rule 8: the platform strips these silently
        if nt in ("api_request", "code", "end_call") and node.get("tools"):
            self.err(_j(path, "tools"), "tools are stripped silently on a %s node: only conversation nodes keep "
                     "them; put the call in an api_request node in front" % nt)
        if nt in ("conversation", "end_call") and node.get("pre_actions"):
            self.err(_j(path, "pre_actions"), "pre_actions are stripped silently on a %s node: only api_request "
                     "and code nodes keep them" % nt)
        if nt == "end_call":
            self.check_end_node(path, node)
        else:
            self.check_transitions(path, node, is_global)
        if is_global:
            self.check_global(path, node)
        # rule 9
        mnt, mtt = node.get("max_node_turns"), node.get("max_turn_transition")
        if mnt is not None and (not isinstance(mnt, int) or isinstance(mnt, bool) or mnt < 1):
            self.err(_j(path, "max_node_turns"), "max_node_turns must be a positive integer")
        if _str(mtt):
            self.check_target(_j(path, "max_turn_transition"), mtt, is_global)
        elif mnt is not None:
            self.soft(_j(path, "max_turn_transition"), "max_node_turns is set but max_turn_transition is not: "
                      "without it the cap changes nothing")
        # rules 7, 15
        if node.get("passthrough") is True or nt == "code":
            self.check_passthrough(path, node, is_global)
        if nt == "code":
            self.check_code_node(path, node)
        if nt == "api_request" and not node.get("pre_actions"):
            self.warn(_j(path, "pre_actions"), "api_request node has no pre_actions: it calls nothing")
        self.check_extraction(path, node)
        if nt == "conversation":
            self.check_prompts(path, key, node)

    def has_end_tool(self, node):
        for t in _list(node.get("tools")):
            if _dict(_dict(t).get("function")).get("handler") == END_HANDLER:
                return True
        return False

    def check_end_node(self, path, node):
        trs = node.get("transitions")
        if trs is None:
            self.warn(_j(path, "transitions"), "set transitions to [] on an end_call node")
        elif trs != []:
            self.err(_j(path, "transitions"), "an end_call node must have transitions == []")
        fn = _dict(_dict(node.get("terminal")).get("function"))
        if fn.get("handler") != END_HANDLER:
            self.err(_j(path, "terminal"), "an end_call node needs terminal.function.handler %r" % END_HANDLER)
        if node.get("disable_inactivity_monitor") is not True:
            self.warn(_j(path, "disable_inactivity_monitor"), "set disable_inactivity_monitor to true on an end_call node")
        if _dict(node.get("on_enter")).get("type") != "silent":
            self.warn(_j(path, "on_enter"), 'set on_enter to {"type": "silent"}: the farewell comes from terminal, '
                      "not from on_enter")

    def check_global(self, path, node):
        cond = node.get("condition")
        if cond is None:
            if node.get("is_tool_call") is not True:
                self.warn(_j(path, "condition"), "global node has no condition: nothing activates it")
        else:
            self.check_condition(_j(path, "condition"), cond, True)
        for i, k in enumerate(_list(node.get("excluded_nodes"))):
            if not isinstance(k, str) or (k not in self.nodes and k not in self.gnodes):
                self.warn(_ix(_j(path, "excluded_nodes"), i), "excluded node %r does not exist" % (k,))

    # ---- transitions: rules 4, 5, 6 ----------------------------------------------------------
    def check_target(self, path, target, is_global):
        if not _str(target):
            self.err(path, "target_node is missing")
        elif target == "__previous__":
            if not is_global:
                self.err(path, "__previous__ is only allowed inside a global node")
        elif target not in self.nodes and target not in self.gnodes:
            self.err(path, "target node %r does not exist" % target)

    def check_transitions(self, path, node, is_global):
        trs = node.get("transitions")
        tp = _j(path, "transitions")
        if trs is None:
            trs = []
        elif not isinstance(trs, list):
            self.err(tp, "transitions must be a list")
            return
        for i, t in enumerate(trs):
            p = _ix(tp, i)
            if not isinstance(t, dict):
                self.err(p, "a transition must be an object")
                continue
            self.check_target(_j(p, "target_node"), t.get("target_node"), is_global)
            if "condition" not in t or t.get("condition") is None:
                self.err(_j(p, "condition"), "transition has no condition (use {\"operator\": \"always\"} for none)")
            else:
                self.check_condition(_j(p, "condition"), t["condition"], True)
        if not trs and node.get("passthrough") is not True and node.get("node_type") != "code":
            returns = is_global and (node.get("passthrough_default_transition") == "__previous__"
                                     or node.get("return_to_previous_on_interrupt") is True)
            if not returns and not self.has_end_tool(node):
                self.err(tp, "dead end: the node has no transitions, so the call can never leave it "
                         "(add one, or make it an end_call node)")

    def check_condition(self, path, cond, top):
        if not isinstance(cond, dict):
            self.err(path, "condition must be an object")
            return
        if "logic" in cond:
            logic = cond.get("logic")
            if logic not in ("or", "and"):
                self.err(_j(path, "logic"), 'logic must be "or" or "and", not %r' % (logic,))
            elif top and logic != "or":
                self.err(_j(path, "logic"), 'a top-level group must use logic "or"; nest an "and" group inside it')
            conds = cond.get("conditions")
            if not isinstance(conds, list) or not conds:
                self.err(_j(path, "conditions"), "a group needs a non-empty conditions list")
                return
            for k, c in enumerate(conds):
                self.check_condition(_ix(_j(path, "conditions"), k), c, False)
            self.check_bool_group(path, cond, logic, conds)
            return
        op = cond.get("operator")
        if op not in OPERATORS:
            self.err(_j(path, "operator"), "unknown operator %r (use %s)" % (op, ", ".join(OPERATORS)))
        elif op == "matches_intent":
            if not _str(cond.get("description")):
                self.err(_j(path, "description"), "matches_intent needs a description")
        elif op != "always":
            if not _str(cond.get("variable")):
                self.err(_j(path, "variable"), "%s needs a variable" % op)
            if op in VALUE_OPS and "operand" not in cond:
                self.err(_j(path, "operand"), "%s needs an operand" % op)
        if top and op in ("equals", "not_equals") and self.bool_spelling(cond) is not None:
            self.warn(path, "routing on a boolean: a bare %s on %r tests one spelling only; the value can arrive as "
                      "'true' or 'True'. Use an OR group that tests both, or a string flag" % (op, cond.get("variable")))

    @staticmethod
    def bool_spelling(leaf):
        if not isinstance(leaf, dict) or leaf.get("operator") not in ("equals", "not_equals"):
            return None
        o = leaf.get("operand")
        if isinstance(o, bool):
            return "True" if o else "False"
        return o if isinstance(o, str) and o in BOOL_OTHER else None

    def check_bool_group(self, path, group, logic, conds):
        # equals needs the other spelling in the same OR group; not_equals in the same AND group
        need = {"equals": "or", "not_equals": "and"}
        for k, c in enumerate(conds):
            s = self.bool_spelling(c)
            if s is None or need[c["operator"]] != logic:
                continue
            other = BOOL_OTHER[s]
            if not any(self.bool_spelling(d) == other and d.get("variable") == c.get("variable")
                       and d.get("operator") == c.get("operator") for d in conds if isinstance(d, dict)):
                self.warn(_ix(_j(path, "conditions"), k),
                          "routing on a boolean: %s %r tests one spelling of %r; add the same test with %r in this "
                          "%s group (the value can arrive as 'true' or 'True'), or use a string flag"
                          % (c["operator"], s, c.get("variable"), other, logic.upper()))

    # ---- passthrough and code nodes: rules 7, 15 ----------------------------------------------
    def check_passthrough(self, path, node, is_global):
        trs = node.get("transitions")
        if not isinstance(trs, list) or not trs:
            self.err(_j(path, "transitions"), "a passthrough node needs transitions ending with "
                     '{"operator": "always"}, or it deadlocks')
        else:
            last = trs[-1]
            cond = _dict(_dict(last).get("condition"))
            if cond.get("operator") != "always" or "logic" in cond or "variable" in cond:
                self.err(_ix(_j(path, "transitions"), len(trs) - 1),
                         'the last transition of a passthrough node must be {"operator": "always"}, or it deadlocks '
                         "when nothing matches")
        dflt = node.get("passthrough_default_transition")
        if not _str(dflt):
            self.err(_j(path, "passthrough_default_transition"), "a passthrough node needs passthrough_default_transition")
        else:
            self.check_target(_j(path, "passthrough_default_transition"), dflt, is_global)

    def check_code_node(self, path, node):
        if node.get("passthrough") is not True:
            self.err(_j(path, "passthrough"), "a code node must be passthrough: true")
        found = False
        for i, a in enumerate(_list(node.get("pre_actions"))):
            fn = _dict(_dict(a).get("function"))
            if fn.get("handler") != CODE_EXEC:
                continue
            found = True
            cp = _j(_ix(_j(path, "pre_actions"), i), "function.parameters.properties.code.default")
            code = _dict(_dict(_dict(fn.get("parameters")).get("properties")).get("code")).get("default")
            if not _str(code):
                self.err(cp, "the code_exec snippet must be a non-empty string in code.default")
            else:
                self.check_code(cp, code)
        if not found:
            self.err(_j(path, "pre_actions"), "a code node needs a %s function in pre_actions" % CODE_EXEC)

    def check_code(self, path, code):
        """No double braces (Freya leaves them unresolved and the snippet crashes), and it must compile."""
        if "{{" in code or "}}" in code:
            self.err(path, "the code contains '{{' or '}}': Freya leaves it unresolved and the snippet breaks; "
                     "read values from vars and avoid nested dict literals that end in '}}'")
        try:
            compile(code, path, "exec")
        except (SyntaxError, ValueError) as e:
            self.err(path, "the code does not compile: %s%s" % (getattr(e, "msg", None) or e,
                                                                 " (line %s)" % e.lineno if getattr(e, "lineno", None) else ""))

    # ---- extraction: rule 16 ----------------------------------------------------------------
    def check_extraction(self, path, node):
        ex = node.get("extraction_schema")
        if ex is None:
            return
        ep = _j(path, "extraction_schema")
        if not isinstance(ex, list):
            self.err(ep, "extraction_schema must be a list")
            return
        for i, item in enumerate(ex):
            p = _ix(ep, i)
            if not isinstance(item, dict):
                self.err(p, "an extraction item must be an object")
                continue
            name, typ = item.get("name"), item.get("type")
            if not _str(name):
                self.err(_j(p, "name"), "an extraction item needs a name")
            if typ not in EXTRACTION_TYPES:
                self.err(_j(p, "type"), "type %r is not one of %s" % (typ, ", ".join(EXTRACTION_TYPES)))
            mc = item.get("min_confidence")
            if mc is None:
                self.err(_j(p, "min_confidence"), "min_confidence is missing: the default 0.95 silently discards "
                         "values that the extractor is less sure about")
            elif not _number(mc) or not 0 <= mc <= 1:
                self.err(_j(p, "min_confidence"), "min_confidence must be a number from 0 to 1")
            if "enum" in item:
                self.warn(_j(p, "enum"), "use enum_values: the old enum type is deprecated and becomes string")
            if "extraction_prompt" in item:
                self.warn(_j(p, "extraction_prompt"), "extraction_prompt replaces the whole built-in template; "
                          "without the extractor placeholders it returns nothing on every turn")
            if _str(name) and typ not in ("date", "datetime") and \
                    any(tok in DATE_TOKENS for tok in name.lower().split("_")):
                self.warn(_j(p, "type"), "%r looks like a date but is typed %r: only date/datetime give the "
                          "extractor today's date" % (name, typ))

    # ---- prompts: rule 18 -------------------------------------------------------------------
    def check_prompts(self, path, key, node):
        tm = node.get("task_message")
        tp = _j(path, "task_message")
        if not _str(tm):
            self.err(tp, "task_message is empty")
            return
        plain = PLACEHOLDER.sub("", tm)
        for other in list(self.nodes) + list(self.gnodes):
            if other != key and _word(other, plain):
                self.warn(tp, "task_message names the node %r: the model does not know node names and may narrate "
                          "steps that have not happened" % other)
        for t in _list(node.get("tools")):
            fn = _dict(_dict(t).get("function"))
            name = fn.get("name")
            if _str(name) and fn.get("handler") != END_HANDLER and not _word(name, tm):
                self.warn(tp, "task_message never mentions the tool %r: say when to call it" % name)

    # ---- tools: rules 11, 12, 13 --------------------------------------------------------------
    def check_tool(self, path, tool, kind):
        if not isinstance(tool, dict):
            self.err(path, "a tool must be an object")
            return
        fn = tool.get("function")
        if not isinstance(fn, dict):
            self.err(_j(path, "function"), "the tool has no function object")
            return
        handler = fn.get("handler")
        if not _str(handler):
            self.err(_j(path, "function.handler"), "handler is missing: the tool cannot run")
        elif not handler.startswith("__function__:"):
            self.warn(_j(path, "function.handler"), "handler %r does not look like __function__:<name>" % handler)
        if not _str(fn.get("name")):
            self.err(_j(path, "function.name"), "the tool has no name")
        cfg = tool.get("config")
        cfg = cfg if isinstance(cfg, dict) else {}
        runs_at = cfg.get("alwaysRunsAt")
        if runs_at is not None:
            if not isinstance(runs_at, list):
                self.err(_j(path, "config.alwaysRunsAt"), "alwaysRunsAt must be a list")
            else:
                for v in runs_at:
                    if v == "each_turn":
                        self.err(_j(path, "config.alwaysRunsAt"), "each_turn is accepted by the schema but not "
                                 "implemented: the tool never fires")
                    elif v not in ALWAYS_RUNS_AT:
                        self.err(_j(path, "config.alwaysRunsAt"), "unknown alwaysRunsAt value %r" % (v,))
        lifecycle = isinstance(runs_at, list) and bool(runs_at)
        is_api = handler == API_CALL
        if is_api:
            self.check_api_params(path, fn)
            self.check_no_const(path, tool)
        # hooks (rule 12)
        has_post = _str(tool.get("post_process_code"))
        for k in ("pre_process_code", "post_process_code"):
            code = tool.get(k)
            if code is None:
                continue
            if not isinstance(code, str):
                self.err(_j(path, k), "%s must be a string" % k)
            elif code.strip():
                if not is_api and _str(handler) and handler in (CODE_EXEC, END_HANDLER):
                    self.warn(_j(path, k), "the platform removes hooks from a %s tool when the workflow is saved" % handler)
                self.check_code(_j(path, k), code)
        if is_api:
            if not has_post:
                if not lifecycle:
                    self.soft(_j(path, "post_process_code"), "api_call tool %r has no post hook: after a result the "
                              "model can go silent or read past a failure; add post_process_code that sets "
                              "data.what_to_do_next" % fn.get("name"))
            elif "what_to_do_next" not in tool["post_process_code"]:
                self.warn(_j(path, "post_process_code"), "the post hook never sets what_to_do_next")
            self.check_retries(path, fn, cfg)

    def check_api_params(self, path, fn):
        pp = _j(path, "function.parameters.properties")
        params = fn.get("parameters")
        props = _dict(_dict(params).get("properties"))
        if not props:
            self.err(_j(path, "function.parameters.properties"), "an api_call tool needs parameters.properties")
            return
        for k in ("url", "method"):
            d = _dict(props.get(k)).get("default")
            if not _str(d):
                self.err(_j(pp, k + ".default"), "%s.default is missing: the engine reads only default "
                         "(a const is not sent; a missing url fails with 'URL is required')" % k)
        body = props.get("body")
        if not isinstance(body, dict):
            return
        bprops = body.get("properties")
        if isinstance(bprops, dict):
            self.check_body_props(_j(pp, "body.properties"), bprops)
            for i, r in enumerate(_list(body.get("required"))):
                if not isinstance(r, str) or r not in bprops:
                    self.warn(_ix(_j(pp, "body.required"), i), "required field %r is not in body.properties" % (r,))
        if "default" in body:
            for k in props:
                if k not in RESERVED_PARAMS:
                    self.err(_j(pp, k), "field spec at the top level of parameters.properties next to a body.default "
                             "object: the engine looks in body.properties, so the model loses its type, enum and "
                             "description; declare %r under body.properties" % k)
            if not isinstance(bprops, dict) or not bprops:
                self.warn(_j(pp, "body"), "the body exists only as a body.default object: the dashboard editor "
                          "shows an empty form and saving removes the tool")

    def check_body_props(self, path, props):
        for k, spec in props.items():
            p = _j(path, k)
            if not isinstance(spec, dict):
                self.err(p, "a body field spec must be an object")
            elif spec.get("type") == "object" and isinstance(spec.get("properties"), dict):
                self.check_body_props(_j(p, "properties"), spec["properties"])
            elif "default" not in spec:
                self.err(_j(p, "default"), 'body field %r has no default: write "{{%s}}" (model fills it) or a '
                         "literal (baked)" % (k, k))

    def check_no_const(self, path, tool):
        def walk(obj, p, in_props):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "const" and not in_props:
                        self.err(_j(p, k), "const does not bake: the engine reads only default, and a {{var}} in a "
                                 "const never resolves; use default")
                    walk(v, _j(p, k), k == "properties" and not in_props)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, _ix(p, i), False)
        walk(tool, path, False)

    @staticmethod
    def read_only(fn):
        method = _dict(_dict(_dict(fn.get("parameters")).get("properties")).get("method")).get("default")
        return str(fn.get("name") or "").startswith("get_") or (isinstance(method, str) and method.upper() == "GET")

    def check_retries(self, path, fn, cfg):
        mr = cfg.get("maxRetries")
        rp = _j(path, "config.maxRetries")
        if mr is None:
            if not self.read_only(fn):
                self.warn(rp, "writing tool %r has no maxRetries: set 0, a retried write can record twice" % fn.get("name"))
        elif not _number(mr):
            self.err(rp, "maxRetries must be a number")
        elif mr > 0 and not self.read_only(fn):
            self.err(rp, "writing tool %r has maxRetries %s: a retried write can record the same thing twice; "
                     "use 0 (only get_* tools may retry)" % (fn.get("name"), mr))

    # ---- workflow-level and lifecycle tools: rule 14 -------------------------------------------
    def check_workflow_tools(self):
        wf_tools = _list(self.wf.get("tools"))
        for i, t in enumerate(wf_tools):
            if not isinstance(t, dict):
                continue
            ra = _dict(t.get("config")).get("alwaysRunsAt")
            if not (isinstance(ra, list) and ra):
                self.err(_ix("tools", i) + ".config.alwaysRunsAt",
                         "a workflow-level tool without a non-empty alwaysRunsAt never runs and the model never sees it")
        for name in self.lifecycle:
            idx = [i for i, t in enumerate(wf_tools) if _dict(_dict(t).get("function")).get("name") == name]
            if not idx:
                self.err("tools", "lifecycle tool %r is missing at workflow level (a lifecycle tool in a node runs "
                         "only on that node)" % name)
                continue
            p = _ix("tools", idx[0])
            tool = wf_tools[idx[0]]
            ra = _dict(tool.get("config")).get("alwaysRunsAt")
            if not (isinstance(ra, list) and "end_of_call" in ra):
                self.err(_j(p, "config.alwaysRunsAt"), "lifecycle tool %r must run at end_of_call" % name)
            body = _dict(_dict(_dict(_dict(tool.get("function")).get("parameters")).get("properties")).get("body")).get("properties")
            for field, want in (("outcome", "{{final_outcome}}"), ("reason", "{{final_reason}}")):
                if isinstance(body, dict) and isinstance(body.get(field), dict):
                    got = body[field].get("default")
                    if got != want:
                        self.warn(_j(p, "function.parameters.properties.body.properties.%s.default" % field),
                                  "%s of %r should be baked as %r (so the routes decide it, not the model), not %r"
                                  % (field, name, want, got))
            key = _dict_key("final_outcome")
            if "final_outcome" not in self.written and not any(key.search(c) for c in self.code_strings):
                self.warn(p, "the workflow never writes final_outcome (vars['final_outcome'] in code, an extraction, "
                          "a response_mapping): %r would send an empty outcome" % name)

    # ---- graph: rule 10 ------------------------------------------------------------------------
    def check_graph(self):
        init = self.wf.get("initial_node")
        if not isinstance(init, str) or init not in self.nodes:
            return
        allk = dict(self.nodes)
        allk.update(self.gnodes)
        edges = {}
        for k, n in allk.items():
            s = set()
            for t in _list(n.get("transitions")):
                if isinstance(t, dict) and isinstance(t.get("target_node"), str):
                    s.add(t["target_node"])
            for f in ("passthrough_default_transition", "max_turn_transition"):
                if isinstance(n.get(f), str):
                    s.add(n[f])
            edges[k] = s
        reach, todo = set(), [init] + list(self.gnodes)
        while todo:
            k = todo.pop()
            if k in reach or k not in allk:
                continue
            reach.add(k)
            todo.extend(edges[k])
        for k in self.nodes:
            if k not in reach:
                self.warn(_j("nodes", k), "not reachable from initial_node (no transition leads here)")
        can_end = {k for k, n in allk.items() if n.get("node_type") == "end_call" or self.has_end_tool(n)}
        changed = True
        while changed:
            changed = False
            for k in allk:
                if k not in can_end and (edges[k] & can_end or (k in self.gnodes and "__previous__" in edges[k])):
                    can_end.add(k)
                    changed = True
        for k in self.nodes:
            if k in reach and k not in can_end:
                self.warn(_j("nodes", k), "no path from this node to an end_call node")

    # ---- baking collisions: rule 17 --------------------------------------------------------------
    def check_collisions(self):
        for path, tool, kind, node_type in self.tool_entries:
            if kind != "tools" or not isinstance(tool, dict):
                continue
            fn = _dict(tool.get("function"))
            if fn.get("handler") != API_CALL:
                continue
            bprops = _dict(_dict(_dict(_dict(fn.get("parameters")).get("properties")).get("body")).get("properties"))
            for field, spec in bprops.items():
                m = ONE_VAR.match(spec.get("default", "")) if isinstance(spec, dict) and isinstance(spec.get("default"), str) else None
                if not m or m.group(1) != field or field in ("final_outcome", "final_reason"):
                    continue
                where = self.written.get(field)
                if not where:
                    continue
                fp = _j(path, "function.parameters.properties.body.properties.%s.default" % field)
                if all(w == "test_variables" for w in where):
                    if field in BAKED_ON_PURPOSE:
                        continue
                    msg = "test_variables sets %r, so the value would be baked and the model never sees it " \
                          "(fine only for a call variable; otherwise rename one of them)" % field
                else:
                    msg = "%r is model-filled ({{%s}}) but the workflow also writes it (%s): it would be baked and " \
                          "the model never sees it; rename the body default or the written variable" \
                          % (field, field, "; ".join(sorted(set(where))))
                self.err(fp, msg)


def lint_workflow(wf, lifecycle=DEFAULT_LIFECYCLE, lenient=None):
    """Lint a workflow dict (bare, or {"name", "workflow"}). Returns {"errors", "warnings", "stats"}.

    lenient=None detects a platform export (see module docstring); True/False force the mode.
    """
    return _Linter(wf, lifecycle, lenient).run()


def _lifecycle_names(values):
    if values is None:
        return DEFAULT_LIFECYCLE
    names = []
    for v in values:
        for part in v.split(","):
            part = part.strip()
            if part and part.lower() != "none":
                names.append(part)
    return tuple(names)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli lint", description=__doc__.split("\n")[0])
    ap.add_argument("workflow")
    ap.add_argument("-o", "--out", help="write the report JSON here")
    ap.add_argument("--lifecycle", action="append",
                    help="lifecycle tool name(s), default close_call; repeat or comma-separate; none = skip")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--lenient", dest="lenient", action="store_const", const=True, default=None,
                      help="report null / max_node_turns / missing post hook as warnings (auto for platform exports)")
    mode.add_argument("--strict", dest="lenient", action="store_const", const=False,
                      help="never treat a workflow as a platform export")
    args = ap.parse_args(argv)
    try:
        wf = read_json(args.workflow)
    except OSError as e:
        print(f"cli lint: cannot read {args.workflow}: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        report = {"errors": [{"path": "", "msg": f"not valid JSON: {e}"}], "warnings": [],
                  "stats": {"nodes": 0, "global_nodes": 0, "tools": 0, "code_nodes": 0, "end_nodes": 0}}
    else:
        report = lint_workflow(wf, _lifecycle_names(args.lifecycle), args.lenient)
    if args.out:
        write_json(args.out, report)
    s, e, w = report["stats"], report["errors"], report["warnings"]
    summary = (f"{len(e)} errors, {len(w)} warnings; {s['nodes']} nodes, {s['global_nodes']} global, "
               f"{s['tools']} tools, {s['code_nodes']} code, {s['end_nodes']} end")
    event("cli lint", summary, [args.workflow], args.out)
    print(summary)
    for item in e:
        print(f"  ERROR {item['path'] or '<root>'}: {item['msg']}")
    for item in w:
        print(f"  warn  {item['path'] or '<root>'}: {item['msg']}")
    if args.out:
        print(f"-> {args.out}")
    return 1 if e else 0
