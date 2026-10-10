---
name: build-phone-agent
description: Build a Freya phone agent from a bank's collections brief and tool API with the builder's code tools, test it and fix what fails. Use whenever you are asked to build or improve a phone agent from a brief.
---

# Build a phone agent from a brief

You turn a bank's brief into a phone agent on Freya. You decide what the agent must do; the code tools in
`builder.cli` write the parts that must not go wrong. Work from the repository root. Read only the brief files and
the tool API file you were given, the files under `docs/`, `examples/` and these skills. **Never use a rule, value
or name from any other brief, including the examples.** Every date, amount, code and sentence in your plan must come
from the brief you were given or from its tool API.

`<slot>` is the brief's file name without `.md` (for several brief files: the last one). All your files go to `out/<slot>/`.

## Steps

1. **Tools.** `python3 -m builder.cli tools <tool_api.json> -o out/<slot>/tools.json`
   Read the summary: tool names, fields and allowed values. Those are the only values the agent may send.
2. **Read the brief** with the skill `read-collections-brief`. Write `out/<slot>/rules.json`. If the brief has several
   documents (mail, policy, memo, code list), read all of them in date order; a later document changes an earlier one.
3. **Plan the call** with the skills `collections-backbone` and `freya-workflow-rules`. Write `out/<slot>/plan.json`.
   `examples/plan-brief-a.json` shows a complete plan for another brief: copy its structure, never its values.
   Optional: `out/<slot>/tool-notes.json` with a better description or result sentence per tool, then run step 1 again
   with `--notes out/<slot>/tool-notes.json`.
4. **Compile and lint.**
   `python3 -m builder.cli compile out/<slot>/plan.json --tools out/<slot>/tools.json -o out/<slot>/workflow.json`
   `python3 -m builder.cli lint out/<slot>/workflow.json -o out/<slot>/lint.json`
   Fix the **plan** until compile prints no PLAN ERROR and lint has 0 errors. Read every warning.
5. **Deploy.** `python3 -m builder.cli deploy out/<slot>/workflow.json --slot <slot> -o out/<slot>/deployed.json`
   It lints, dry-runs on Freya, saves, publishes and reads the workflow back. If it prints "platform changed", the
   platform dropped something: fix the plan.
6. **Test.** On a practice brief: `python3 tools/run_cases.py <agent_id> --brief <A|B>` (or the builder's
   `cli cases-run` when it exists). Run it in the foreground and wait; a run takes 3 to 11 minutes. Read every FAIL
   line and its reason. On a new brief without practice customers, test what the time allows (see Budget).
7. **Fix and repeat.** Change `plan.json` (prompts, routes, ends) or `rules.json`, then steps 4 to 6 again. Do not edit
   `workflow.json` by hand except to fix a lint error, and say so in one line when you do.
8. **Finish** with one line: `workflow_id`, `agent_id`, and how many customers passed in the last run (or "not tested").

## Budget

The whole build has 30 minutes (`BUILD_DEADLINE` in the environment is the end, as a Unix time). Leave the last 5
minutes to the builder's own wrap-up. A test run takes up to 11 minutes and only one runs at a time, so do not start
one with less than 12 minutes left. A clean compile, lint and deploy matter more than one more test.

## Rules

- Prefer rules in routes and code over rules in prompts: a customer that passes once can fail the next time.
- Every date the agent says comes from `{{date_facts}}` or `{{check_text}}`, never from the model's own arithmetic.
- When a tool call fails, the agent must say so. It never says something is recorded when it is not.
- Never change a phone agent on the platform by hand. Change the plan and deploy.
