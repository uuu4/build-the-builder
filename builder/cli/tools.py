"""cli tools: turn the bank's tool API (OpenAPI) into Freya tool definitions.

    python3 -m builder.cli tools tools/openapi.json -o out/<slot>/tools.json [--notes out/<slot>/tool-notes.json]

Nothing here knows a brief. Every name, field, enum and URL comes from the OpenAPI file.
Rules from docs/tools-and-code.md:
- every body field is a leaf under body.properties with its own default
- call variables (customer_id) are baked with "{{var}}", the model never sees them
- other fields get "{{<field>}}" so the model fills them, with type, description and enum on the leaf
- tools that write get maxRetries 0 (a retried write can record twice), read-only tools 2
- a post hook drops the response headers and adds data.what_to_do_next, so the model does not go
  silent after a result or read past a negative one
- the closing tool becomes a lifecycle tool (end_of_call) whose outcome fields are baked from
  variables the routes write, so the model does not choose the outcome

tool-notes.json (optional, written by the builder agent) lets the agent set, per tool:
  {"<tool>": {"description": "...", "fields": {"<field>": "description for the model"},
              "on_ok": "...", "on_fail": "...",
              "cases": [{"field": "verified", "equals": false, "next": "... <wrong_answers_left> ..."}]}}
A <field> in a sentence is replaced with that field's value from the response.
"""
import argparse

from .common import assert_code_safe, code_literal, event, read_json, write_json

DEFAULT_BAKED = {"customer_id": "customer_id"}
DEFAULT_LIFECYCLE = {"close_call": {"outcome": "final_outcome", "reason": "final_reason"}}
TIMEOUT_MS = 12000

GENERIC_OK = "The call worked. Say the result to the customer in one short sentence, then continue with the next step."
GENERIC_FAIL = ("The call FAILED. Nothing was done. Do not say it was recorded or done. "
                "Tell the customer in one short sentence that it did not go through.")

POST_HOOK = '''import json
try:
    _cfg = json.loads(__CFG__)
    def _fill(text, d):
        out = str(text)
        for k, v in d.items():
            out = out.replace('<' + str(k) + '>', str(v))
        return out
    def _is_false(v):
        return v is False or str(v).strip().lower() == 'false'
    def _same(a, b):
        return str(a).strip().lower() == str(b).strip().lower()
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            d = dict(ok=False, error='service error, no usable response')
            result['data'] = d
        failed = _is_false(d.get('ok')) or bool(d.get('error')) or str(result.get('status', 'success')) not in ('success', 'None')
        if failed:
            msg = _cfg.get('on_fail') or _cfg.get('generic_fail')
            err = d.get('error')
            if err:
                msg = msg + ' (error: ' + str(err) + ')'
        else:
            msg = None
            for c in _cfg.get('cases') or []:
                if isinstance(c, dict) and c.get('field') in d and _same(d.get(c.get('field')), c.get('equals')):
                    msg = c.get('next')
                    break
            if msg is None:
                msg = _cfg.get('on_ok') or _cfg.get('generic_ok')
                negatives = [k for k, v in d.items() if k != 'ok' and _is_false(v)]
                if negatives and not _cfg.get('on_ok'):
                    msg = msg + ' These fields came back false: ' + ', '.join(negatives) + '. Read what each one means before you answer.'
        d['what_to_do_next'] = _fill(msg, d)
except Exception:
    pass
'''

DROP_EMPTY_HOOK = '''import json
try:
    _req = set(json.loads(__REQ__))
    b = config.get('body')
    if isinstance(b, dict):
        for k in list(b.keys()):
            v = b.get(k)
            unresolved = isinstance(v, str) and (v.strip() == '' or ('{' + '{') in v)
            if k not in _req and (v is None or unresolved):
                b.pop(k, None)
except Exception:
    pass
'''


def _servers(spec):
    servers = spec.get("servers") or []
    if not servers or not servers[0].get("url"):
        raise ValueError("tool API has no servers[0].url")
    return servers[0]["url"].rstrip("/")


def _leaf(name, schema):
    leaf = {"type": schema.get("type", "string")}
    desc = schema.get("description")
    enum = schema.get("enum")
    if enum:
        values = ", ".join(str(e) for e in enum)
        desc = (desc + " " if desc else "") + f"One of: {values}."
        leaf["enum"] = list(enum)
    if schema.get("format") == "date":
        desc = (desc + " " if desc else "") + "Date as YYYY-MM-DD."
    if desc:
        leaf["description"] = desc
    return leaf


def _is_read_only(name, method):
    return method.upper() == "GET" or name.startswith("get_")


def build_tools(spec, notes=None, baked=None, lifecycle=None):
    notes = notes or {}
    baked = DEFAULT_BAKED if baked is None else baked
    lifecycle = DEFAULT_LIFECYCLE if lifecycle is None else lifecycle
    base = _servers(spec)
    tools, order, warnings = {}, [], []
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            name = op.get("operationId") or path.strip("/").split("/")[-1]
            schema = (op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")) or {}
            props, required = schema.get("properties", {}), list(schema.get("required", []))
            note = notes.get(name, {})
            life = lifecycle.get(name)
            body_props = {}
            field_notes = note.get("fields") or {}
            for field, fs in props.items():
                if field in field_notes:
                    fs = {**fs, "description": " ".join(x for x in (fs.get("description"), field_notes[field]) if x)}
                leaf = _leaf(field, fs)
                if field in baked:
                    leaf = {"type": leaf["type"], "default": "{{" + baked[field] + "}}"}
                elif life and field in life:
                    leaf["default"] = "{{" + life[field] + "}}"
                else:
                    leaf["default"] = "{{" + field + "}}"
                body_props[field] = leaf
            model_fields = [f for f in props if f not in baked and not (life and f in life)]
            summary = (op.get("summary") or "").strip()
            extra = (op.get("description") or "").strip()
            description = note.get("description") or " ".join(x for x in (summary, extra) if x)
            tool = {
                "type": "function",
                "config": {"timeoutMs": TIMEOUT_MS, "maxRetries": 2 if _is_read_only(name, method) else 0},
                "function": {
                    "name": name,
                    "handler": "__function__:api_call",
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "default": base + path},
                            "method": {"type": "string", "default": method.upper()},
                            "connect_retries": {"type": "number", "default": 2},
                            "headers": {"type": "object", "properties": {
                                "Content-Type": {"type": "string", "default": "application/json"}}},
                            "body": {"type": "object", "properties": body_props,
                                     "required": [f for f in required if f in model_fields]},
                        },
                    },
                },
            }
            cfg = {"generic_ok": GENERIC_OK, "generic_fail": GENERIC_FAIL, "cases": note.get("cases") or []}
            for k in ("on_ok", "on_fail"):
                if note.get(k):
                    cfg[k] = note[k]
            tool["post_process_code"] = POST_HOOK.replace("__CFG__", code_literal(cfg))
            tool["pre_process_code"] = DROP_EMPTY_HOOK.replace("__REQ__", code_literal(required))
            if life:
                tool["config"]["alwaysRunsAt"] = ["end_of_call"]
                missing = [f for f in life if f not in props]
                if missing:
                    warnings.append(f"{name}: lifecycle fields not in the API: {missing}")
            for k in ("post_process_code", "pre_process_code"):
                assert_code_safe(tool[k], f"{name}.{k}")
            tools[name] = tool
            order.append(name)
    for name in lifecycle:
        if name not in tools:
            warnings.append(f"lifecycle tool {name} is not in the API")
    return {"tools": tools, "order": order, "lifecycle": [n for n in order if n in lifecycle],
            "baked": baked, "warnings": warnings}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli tools", description=__doc__.split("\n")[0])
    ap.add_argument("openapi")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--notes", help="tool-notes.json written by the agent")
    args = ap.parse_args(argv)
    spec = read_json(args.openapi)
    notes = read_json(args.notes) if args.notes else {}
    out = build_tools(spec, notes)
    write_json(args.out, out)
    summary = f"{len(out['order'])} tools ({', '.join(out['order'])}), lifecycle: {out['lifecycle']}"
    if out["warnings"]:
        summary += f"; warnings: {out['warnings']}"
    event("cli tools", summary, [args.openapi, args.notes or ""], args.out)
    print(summary)
    print(f"-> {args.out}")
    return 0
