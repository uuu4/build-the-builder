---
name: collections-builder
description: Build a Freya phone agent for a bank's collections brief with the team's kit (builder/kit), deploy it and test it. Use when builder/build.py asks for a phone agent.
---

# Build a collections phone agent with the kit

You get one or more brief files, a tool API file and a slot. You write two files, generate the workflow with code, deploy it and test it. Work from the repository root.

Every value comes from the brief files and the tool API file you were given. Nothing comes from memory, from another brief, or from files of other slots in `out/`, `baseline/` or `submission/`, or from `practice/` (apart from brief files you were given): do not open them. When a later file (a memo, a mail) changes an earlier one, the later one wins.

## Steps

1. **Read.** All brief files, then the tool API file. Then `python3 -m builder.cli spec-doc`, then `builder/kit/front.py`, `builder/kit/ladder.py`, `builder/kit/graph.py`, `builder/kit/pycode.py`, `builder/kit/openapi.py`. Read `docs/workflow-format.md` and `docs/tools-and-code.md` only for what the kit does not cover.
2. **List the rules.** Write `out/<slot>/rules.md`: every numbered or implied rule, one line each, with where it goes (front spec, back half, closing). Raw bank material (mail, policy extract, memo, code list): resolve conflicts first, newest wins, and note what you chose.
3. **Front spec.** Write `out/<slot>/front.json` in the format `spec-doc` prints. The kit builds the opening, who answered, someone else on the line, the callback and the identity check from it. Field names, enum values and response fields come from the tool API file.
4. **Generator.** Write `out/<slot>/gen.py`. It builds the front with `front.build(api, spec, after_verify="fetch_account")`, adds the back half (below), lints and writes `out/<slot>/workflow.json`. Run it.
5. **Deploy.** `python3 -m builder.cli deploy <slot> out/<slot>/workflow.json`.
6. **Test.** `python3 -m builder.cli test <slot> --brief <letter>` when `public-test-set.json` has practice customers for this brief, otherwise skip. Run it in the foreground and wait. Never end your turn while a test runs. It refuses near the deadline; then stop testing.
7. **Fix.** Read each FAIL and its reason. Fix `gen.py` or `front.json`, regenerate, deploy, test again. Prefer a fix in code or routing over a sentence in a prompt. Stop when the deadline is near: a deployed, linted workflow matters more than one more round.
8. End with one line: workflow id, agent id, last test result.

Never edit the workflow on the platform and never edit `workflow.json` by hand: change the generator and run it.

## The back half

What the practice runs taught. Each point cost passes when it was missing.

**Account and facts in code.** After identity, an `api_request` node calls the account tool (`api.pre_action(...)`, read-only, `retries=2`) with a node-level mapping of the product list (`data.<field>`). Then a code node (`g.code`, source from `pycode.with_params(body, params)`; it gives you `P`, `isbiz`, `nextbiz`, `nth_biz_after`, `say`, `get_now`) works out everything that is arithmetic: per product its name in words, amounts, band, deadline, floor, persuasion attempts with their exact amount and date, and a date table (each date: allowed, or what to offer instead and why). Put dates as ISO and spoken words. The model never computes a date, a deadline or an amount. Read the product list with `read_list(<api_request node name>, <list field>)` from the helpers: a node-level mapping of a list does not arrive; the flattened `<node>_response.data.<field>.<i>.<key>` keys do. Numbers arrive as strings: use `num()` and `money()`. Wrap everything in `try`; on failure set a flag and route to a literal close.

**Fixed lines are fixed.** A sentence the brief requires word for word (the debt statement, a confirmation sentence, a closing sentence) is built in code and spoken with `on_enter: {"type": "tts", "text": "{{var}}"}`, or is a close's farewell. Do not ask the model to remember it.

**Situations by extraction, not by intent.** One enum extraction per conversation node for what the customer's last message is (for example: proposes a date or amount, accepts, refuses, already paid, disputes, hardship, wants a new payment plan, wants a human, question, chat). Describe each value precisely, with what it is NOT: talk about the weather, a wedding or a busy day is `chat`, never `paid`; "why do you need that?" is a `question`. Branch with `g.eq`/`g.any_eq`. Each node gets its own variable name, so a stale value from an earlier node cannot fire.

**Counting in the graph: the ladder.** Every offer the brief allows is one step of `builder/kit/ladder.py`: write `out/<slot>/ladder.json` (format in the module docstring), build it with `ladder.build(...)` and check it with `ladder.check(...)`. Draw the brief's offer rules as a small state machine first (in `rules.md`): which offer comes first, what follows a refusal, what follows "too much", what a second refusal does, how the number of attempts depends on the product. A condition on a product property (e.g. the number of attempts of its band) is an `"if"` on a variable your code node sets as a string. Each step's `say` is a line your code node built ("{{attempt1_line}}"), with the exact amount and date. Never route a refusal with an intent description like "refused the last offer": the router does not know which offer is on the table, the graph does. An earlier version did that and closed after the first refusal.

**Recording.** The promise tool goes in `tools` of the node that confirms. Its description: call only after the read-back and a clear yes, once per product, with the exact ISO date and amount from the facts. Route on the result: `g.is_true(..., "<tool>_response.data.ok")` to the next step; `g.greater(..., "<tool>_failure_count", N)` when the brief's retry limit is used up. Tell the model in the prompt: after a failed result, nothing was recorded; never say it was.

**Closing.** Every path ends in exactly one close. Use `g.close(api, name, outcome, reason, farewell)` with literal values from the brief's outcome table. When the outcome depends on what happened (several products), compute `final_outcome`/`final_reason` in a code node (never set the reason when the outcome needs none), give that code node a first transition `g.unset(<literal close>, "final_outcome")`, then `g.close_from_vars(...)`. The farewell is the close's `say`; the brief's goodbye rule goes there.

**No Python hooks on tools.** `pre_process_code`/`post_process_code` run in the platform's code sandbox. When the sandbox is down the whole tool call fails, even when the bank already recorded it. Say how to read each result in the prompt instead, and route on result variables.

**Words.** A fixed line never contains "recorded", "booked" or "registered" before the tool said so (say "we are recording this call", not "this call is recorded"). Never invent figures, dates or terms the brief does not allow.

**Several products.** State all of them first, one sentence each. Facts and attempts per product. One read-back, one confirmation, then one promise call per product. Product ids from the account result only.

**Turns.** Every conversation node: `max_turns` with a `max_turn_target` that closes sensibly. Tell the model in the system prompt: after every tool result speak or call the next tool; one tool per message; do not say goodbye yourself.

## Budget

`build.py` gives you a deadline. Deploy a first complete version early (about a third of the time), then improve. A test of ten customers takes 3 to 11 minutes. Log a choice you were unsure about with `python3 -m builder.cli event uncertain_default "<what and why>"`.
