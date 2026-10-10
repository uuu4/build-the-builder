"""Node and transition helpers in the shapes the platform is known to accept (docs/workflow-format.md)."""


def _grp(conds):
    return {"logic": "or", "conditions": conds}


def eq(target, var, val, desc=None):
    return {"target_node": target, "description": desc or f"{var} is {val}", "condition": _grp([{"variable": var, "operator": "equals", "operand": str(val)}])}


def any_eq(target, var, vals, desc=None):
    return {"target_node": target, "description": desc or f"{var} is one of {', '.join(map(str, vals))}",
            "condition": _grp([{"variable": var, "operator": "equals", "operand": str(v)} for v in vals])}


def is_true(target, var, desc=None):
    """Booleans arrive as 'true' or 'True'. Test both."""
    return any_eq(target, var, ["true", "True"], desc or f"{var} is true")


def greater(target, var, n, desc=None):
    return {"target_node": target, "description": desc or f"{var} > {n}", "condition": _grp([{"variable": var, "operator": "greater_than", "operand": n}])}


def and_eq(target, pairs_options, desc):
    """OR over several AND groups. `pairs_options` is a list of [(var, val), ...] lists."""
    return {"target_node": target, "description": desc, "condition": _grp([
        {"logic": "and", "conditions": [{"variable": v, "operator": "equals", "operand": str(x)} for v, x in pairs]} for pairs in pairs_options])}


def intent(target, desc):
    return {"target_node": target, "description": desc, "condition": {"operator": "matches_intent", "description": desc}}


def always(target, desc="always"):
    return {"target_node": target, "description": desc, "condition": {"operator": "always"}}


def enum_field(name, values, description, min_confidence=0.6):
    return {"name": name, "type": "string", "enum_values": list(values), "description": description, "min_confidence": min_confidence}


def conversation(name, task, transitions, tools=(), extract=(), on_enter=None, first_entry_only=True, max_turns=None, max_turn_target=None):
    n = {"name": name, "node_type": "conversation", "task_message": task, "transitions": list(transitions)}
    if on_enter:
        n["on_enter"] = on_enter
        n["on_enter_first_entry_only"] = first_entry_only
    if tools:
        n["tools"] = list(tools)
    if extract:
        n["extraction_schema"] = list(extract)
    if max_turns:
        n["max_node_turns"] = max_turns
        if max_turn_target:
            n["max_turn_transition"] = max_turn_target
    return n


def code(name, source, next_node, transitions=()):
    if "{{" in source or "}}" in source:
        raise ValueError(f"code node {name}: '{{{{' or '}}}}' in source")
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": next_node,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {
                "type": "object", "properties": {"code": {"type": "string", "default": source}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": list(transitions) + [always(next_node)]}


def api_request(name, pre_action, next_node, transitions=(), mapping=(), say=None):
    n = {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": next_node,
         "on_enter": {"type": "tts", "text": say} if say else {"type": "silent"}, "disable_inactivity_monitor": True,
         "pre_actions": [pre_action], "transitions": list(transitions) + [always(next_node)]}
    if mapping:
        n["response_mapping"] = [{"path": p, "variable": v} for p, v in mapping]
    return n


def end(name="end", function_name="call_closed"):
    """Hangs up silently. The farewell is spoken by the node before it."""
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": function_name, "handler": "__function__:end_call",
                                                          "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}


def close(api, name, outcome, reason, farewell, end_node="end"):
    """Says the farewell, then records the outcome with close_call, then hangs up.

    The outcome is baked as a literal: no model call, no code sandbox, no variable that might be unset.
    close_call is idempotent enough to retry: the API says a 500 recorded nothing."""
    values = {"outcome": outcome}
    if reason:
        values["reason"] = reason
    return api_request(name, api.pre_action("close_call", values, retries=2), end_node, say=farewell)
