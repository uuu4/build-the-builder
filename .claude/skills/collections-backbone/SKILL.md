---
name: collections-backbone
description: The step structure of a collections call (opening, someone else, identity, account, facts, conversation, ends) and how to place a brief's rules on it. Use in step 3 of build-phone-agent, with freya-workflow-rules for the plan format.
---

# The backbone of a collections call

Start from this structure and adapt it to the brief. `examples/plan-brief-a.json` is a complete example; copy its
shape, never its values.

```text
opening ──customer──► identity ──all verified──► load_account (fetch) ──► facts (code) ──► collect
   │                     │ no tries left / declined                                          │
   ├─someone else──► facts_third_party ──► third_party                                         ├─ tool results / call_result
   └─wrong number, deceased, unclear ──► ends                                                  └─► ends
```

## Steps

- **opening** (talk): fixed first line from the brief (`say`), `first_entry_only`. Extract one enum, for example
  `party`, with a value for each way the opening can end (customer, someone else, wrong number, ...). Route on it with
  `equals`. No tools. The task repeats the brief's words that must not be said yet.
- **identity** (talk, tool `verify_identity`): questions one at a time, the answer format, which answer to ask again.
  Leave on the **tool result**: the "all verified" field (as a boolean: `"equals": true`) to the next step, "no tries
  left" to the failure end. Refusals by an extracted enum.
- **load_account** (fetch): the account tool runs by itself, no model; map the products list to a variable
  (`{"data.products": "accounts"}`), `on_fail` to a service-error end.
- **facts** (code): computes today, bands, deadlines, floors, named dates, the callback window and a calendar from
  `now` and the products, into `{{date_facts}}`. The parameters are the plan's `dates` block, from the brief.
- **collect** (talk): the whole conversation after verification. Its task has the facts block and every rule of
  disclosure, dates, amounts, persuasion, special situations and recording, as numbered instructions. Tools: the
  promise tool and the transfer tool (and the note tool when the brief uses it).
- **third_party** (talk, tool `schedule_callback`): the facts block for the window; what may not be said.
- Rare situations that can happen anywhere (a human request before verification, for example) can be a global node.

## Ends

Every row of the brief's outcome table is an end: `{"outcome", "reason"}` with the exact codes. Add `farewell` when
the call ends without the model speaking (identity failed, deceased, wrong number). Use `if_tool_ok` when a recorded
promise must win over the end's own outcome (refusals or hardship after a promise on another product).

## Leaving collect

Routing runs right after a tool result, before the model speaks. So:
- Leave on a tool result only when nothing more must be said (a transfer: route on `tool_ok` plus the tool's
  argument, e.g. `{"var": "transfer_to_agent_args.queue", "equals": "<queue>"}`).
- After a recorded promise the agent must still speak (confirmation sentence, goodbye). Do not leave on the promise
  tool's success. Extract a `call_result` enum (promise done, refused, dispute, ...) and route on it; it is filled
  from the customer's next message.
- A tool that failed the allowed number of times: `{"tool_failed": "<tool>", "min": n}` to the service-error end.

## Prompts

- Numbered instructions, one rule each, in the brief's order of the call. Quote fixed sentences exactly.
- Tell the agent to use the exact dates and amounts in `{{date_facts}}`; never let it compute dates.
- Name each tool in the task and say when to call it. Do not name other steps.
- Counts matter ("offer once", "two attempts", "one sentence of sympathy"): write them as numbers.
