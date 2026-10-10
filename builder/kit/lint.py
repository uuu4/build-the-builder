"""Local checks on a workflow before it goes to the platform. Returns a list of problems; empty means clean."""
import json


def _has_null(o):
    """A real null in the structure. The word null inside a code string is fine."""
    if o is None:
        return True
    if isinstance(o, dict):
        return any(_has_null(v) for v in o.values())
    if isinstance(o, list):
        return any(_has_null(v) for v in o)
    return False


def lint(wf, api=None):
    errs = []
    nodes = wf.get("nodes", {})
    if wf.get("initial_node") not in nodes:
        errs.append(f"initial_node {wf.get('initial_node')!r} is not a node")
    if "agent_config" in wf:
        errs.append("agent_config must be left out")
    if _has_null(wf):
        errs.append("a null value (the schema rejects null)")
    allnodes = {**nodes, **wf.get("global_nodes", {})}
    for k, n in allnodes.items():
        t = n.get("node_type", "conversation")
        for tr in n.get("transitions", []):
            if tr.get("target_node") not in allnodes and tr.get("target_node") != "__previous__":
                errs.append(f"{k}: transition to missing node {tr.get('target_node')!r}")
        for f in ("max_turn_transition", "passthrough_default_transition"):
            if n.get(f) and n[f] not in allnodes and n[f] != "__previous__":
                errs.append(f"{k}: {f} to missing node {n[f]!r}")
        if n.get("tools") and t != "conversation":
            errs.append(f"{k}: tools on a {t} node are dropped by the platform")
        if n.get("pre_actions") and t == "conversation":
            errs.append(f"{k}: pre_actions on a conversation node are dropped by the platform")
        if n.get("passthrough") and not any(tr.get("condition", {}).get("operator") == "always" for tr in n.get("transitions", [])):
            errs.append(f"{k}: passthrough node without an always transition deadlocks")
        if t == "end_call" and n.get("transitions"):
            errs.append(f"{k}: end_call node with transitions")
        if t == "conversation" and not (n.get("task_message") or "").strip():
            errs.append(f"{k}: empty task_message")
        for e in n.get("extraction_schema", []):
            if "min_confidence" not in e:
                errs.append(f"{k}: extraction field {e.get('name')} without min_confidence")
        for a in n.get("pre_actions", []):
            if a["function"]["handler"].endswith("code_exec"):
                src = a["function"]["parameters"]["properties"]["code"]["default"]
                if "{{" in src or "}}" in src:
                    errs.append(f"{k}: '{{{{' or '}}}}' in code")
                try:
                    compile(src, k, "exec")
                except SyntaxError as e:
                    errs.append(f"{k}: code does not compile: {e}")
        for tool in n.get("tools", []) + n.get("pre_actions", []):
            for hook in ("pre_process_code", "post_process_code"):
                if tool.get(hook):
                    try:
                        compile(tool[hook], f"{k}.{hook}", "exec")
                    except SyntaxError as e:
                        errs.append(f"{k}: {hook} of {tool['function']['name']} does not compile: {e}")
            if "const" in json.dumps(tool):
                errs.append(f"{k}: 'const' in tool {tool['function']['name']} is never sent")
        if api:
            for a in n.get("pre_actions", []):
                if a["function"]["name"] == "close_call":
                    body = a["function"]["parameters"]["properties"]["body"]["properties"]
                    out = body.get("outcome", {}).get("default")
                    allowed = api.enum("close_call", "outcome")
                    if allowed and out not in allowed and not str(out).startswith("{{"):
                        errs.append(f"{k}: close_call outcome {out!r} not in the tool API ({', '.join(allowed)})")
    reach, todo = set(), [wf.get("initial_node")]
    while todo:
        k = todo.pop()
        if k in reach or k not in allnodes:
            continue
        reach.add(k)
        n = allnodes[k]
        todo += [tr.get("target_node") for tr in n.get("transitions", [])] + [n.get("max_turn_transition"), n.get("passthrough_default_transition")]
    for k in nodes:
        if k not in reach:
            errs.append(f"{k}: not reachable from the initial node")
    if not any(n.get("node_type") == "end_call" for n in nodes.values()):
        errs.append("no end_call node")
    return errs
