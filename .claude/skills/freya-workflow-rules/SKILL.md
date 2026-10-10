---
name: freya-workflow-rules
description: The plan format that builder.cli compile turns into a Freya workflow, and the Freya rules behind it. Use when you write or fix out/<slot>/plan.json.
---

# Plan format and Freya rules

The full format is in the docstring of `builder/cli/compile.py` and in `docs/interfaces.md`. The background is in
`docs/workflow-format.md` and `docs/tools-and-code.md`; read them once.

## Plan

```json
{
  "system_prompt": "identity, language, tone, rules for every step",
  "start": "opening",
  "default_on_max": "end:<end>",
  "dates": { "now_var", "products_var", "weekend", "holidays", "bands", "floor_field_by_type", "product_label",
             "named_dates", "callback", "calendar_days" },
  "nodes": { "<key>": { "kind": "talk|fetch|facts|check|set", ... } },
  "global_nodes": { "<key>": { "kind": "talk", "when": <cond>, "excluded": [...], ... } },
  "ends": { "<end>": { "outcome": "<code>", "reason": "<code or empty>", "farewell": "...", "if_tool_ok": {...} } }
}
```

- talk: `say` (fixed first line, `{{var}}` allowed) or null (the model writes it), `first_entry_only`, `task`,
  `tools` (names from tools.json, or `{"name", "description", "map"}`), `extract` (`name`, `type`, `enum`,
  `description`, `min_confidence`), `routes`, `max_turns`, `on_max`.
- route: `{"to": "<node>" | "end:<end>" | "__previous__" (global only), "when": <cond>, "desc": "..."}`.
- cond: `"always"`, `{"intent": "..."}`, `{"var": v, "equals": x}` (`true`/`false` become both spellings),
  `not_equals`, `gt`, `lt`, `contains`, `{"var": v, "is_set": true}`, `{"tool_ok": t, "min": n}`,
  `{"tool_failed": t, "min": n}`, `{"all": [...]}`, `{"any": [...]}`.
- Variables you can use in prompts and conditions: call variables; extracted names; `<tool>_response.data.<field>`;
  `<tool>_args.<field>`; `<tool>_success_count`, `<tool>_failure_count`; from facts: `date_facts`, `today`,
  `deadline_<product_id>`, `band_<product_id>`, `floor_<product_id>`, `attempts_<product_id>`, each named date.

## Freya rules the compiler cannot fix for you

- The routing model does not see `task_message`. A routing rule in a prompt does nothing; put it in routes.
- The model does not know step names. Do not write "go to the identity step".
- Prefer an extracted enum plus `equals` over several `intent` routes.
- Extract dates as `type: "date"`. Set `min_confidence` (the compiler sets 0.7 when you leave it out).
- A fixed line (`say`, `farewell`) is spoken word for word, so it must be exactly right.
- Each tool result carries `what_to_do_next`. Better result sentences go in `tool-notes.json`
  (`{"<tool>": {"on_ok", "on_fail", "cases": [{"field", "equals", "next"}], "fields": {"<field>": "description"}}}`).
- The closing tool runs by itself at the end of every call with the outcome of the end that was reached. Never give
  it to a step.
