"""Read the bank's tool API file and turn its operations into Freya tool definitions."""
import json

HDR = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}
# Body fields the model may see. Everything that is not here is baked from a variable or a literal.
_SCHEMA_KEYS = ("type", "description", "enum")


class Api:
    """One tool API file. `ops[name]` holds the request fields, the required list and the response fields."""

    def __init__(self, path):
        self.doc = json.load(open(path))
        self.base_url = (self.doc.get("servers") or [{}])[0].get("url", "").rstrip("/")
        self.ops = {}
        for p, methods in self.doc.get("paths", {}).items():
            for method, op in methods.items():
                name = op.get("operationId") or p.strip("/").split("/")[-1]
                req = self._resolve(op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}))
                ok = op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
                self.ops[name] = {"path": p, "method": method.upper(), "fields": req.get("properties", {}),
                                  "required": req.get("required", []), "response": self._resolve(ok).get("properties", {})}

    def _resolve(self, s):
        """Follow a local $ref (#/components/...) one level at a time."""
        while isinstance(s, dict) and "$ref" in s:
            node = self.doc
            for part in s["$ref"].lstrip("#/").split("/"):
                node = node.get(part, {})
            s = node
        return s or {}

    def enum(self, op, field):
        return list(self._resolve(self.ops[op]["fields"].get(field, {})).get("enum", []))

    def url(self, op):
        return self.base_url + self.ops[op]["path"]

    def _body(self, op, baked, model_fields, descriptions):
        props = {}
        for f, s in self.ops[op]["fields"].items():
            s = self._resolve(s)
            leaf = {k: s[k] for k in _SCHEMA_KEYS if k in s}
            leaf.setdefault("type", "string")
            if f in baked:
                leaf["default"] = baked[f]
            elif model_fields is None or f in model_fields:
                # a placeholder no variable carries: the model fills it, and the field shows with its enum and description
                leaf["default"] = "{{%s}}" % f
                if f in descriptions:
                    leaf["description"] = descriptions[f]
            else:
                continue
            props[f] = leaf
        return {"type": "object", "properties": props, "required": [f for f in self.ops[op]["required"] if f in props]}

    def tool(self, op, description, baked=None, model_fields=None, descriptions=None, post_code="", retries=0, timeout_ms=12000):
        """A tool for a conversation node's `tools`. `baked` fields are fixed ({{var}} or literal), the rest the model fills."""
        baked = dict(baked or {})
        if "customer_id" in self.ops[op]["fields"]:
            baked.setdefault("customer_id", "{{customer_id}}")
        t = {"type": "function", "config": {"timeoutMs": timeout_ms, "maxRetries": retries},
             "function": {"name": op, "handler": "__function__:api_call", "description": description,
                          "parameters": {"type": "object", "properties": {
                              "url": {"type": "string", "default": self.url(op)},
                              "method": {"type": "string", "default": self.ops[op]["method"]},
                              "headers": HDR,
                              "body": self._body(op, baked, model_fields, descriptions or {})}}}}
        if post_code:
            t["post_process_code"] = post_code
        return t

    def pre_action(self, op, values, retries=2, timeout_ms=12000):
        """An engine-run call for an api_request node. Every field is baked; a field left out of `values` is not sent."""
        values = dict(values)
        if "customer_id" in self.ops[op]["fields"]:
            values.setdefault("customer_id", "{{customer_id}}")
        t = self.tool(op, "", baked=values, model_fields=(), retries=retries, timeout_ms=timeout_ms)
        del t["function"]["description"]
        return t
