# Hackathon sayfası (kopya)

Kaynak: https://www.freyavoice.ai/hackathon · 2026-10-10 14:10 TSİ'de çekildi (kit v2). Sayfa değişirse sayfa geçerli. Saatler UTC: gizli brief'ler Paz 17:00 UTC = 20:00 TSİ, teslim 20:00 UTC = 23:00 TSİ. Pratik vakaların tablosu kit'teki `public-test-set.json`'da.

---

## What this is

A bank has customers who are late on a payment. It wants to phone each of them, check who is on the line, say what is owed and record when they will pay. On Freya, software makes that call instead of a person.

> **Phone agent:** Your credit card has 420 dollars past due. Can you pay today?

> **Customer:** Not today. I can do it on Friday.

> **Phone agent:** 420 dollars on Friday the sixteenth. Do you confirm?

> **Customer:** Yes.

> `create_promise 420.00 2026-10-16` — recorded in the bank's system

A piece of one call. The last line is what the bank's system keeps. We check that record, and we check the conversation.  
That software does not know the bank's rules by itself. Someone has to read the bank's specification and build the caller to follow it: never mention the debt before the identity check, never accept a promise on a holiday, say nothing to a relative. Today a person does this by hand, and one bank takes days.

The question of this hackathon: can a program do that work instead?

#### Three words used on this page

- **Phone agent:** The software that talks to the customer. It lives on Freya as a workflow: steps, prompts and tools.

- **Brief:** The bank's specification for these calls: who to ask for, how to check identity, which payment dates are allowed, how to close the call.

- **Builder:** The program you write. It reads a brief and creates the phone agent. Nobody edits the phone agent by hand.

You write the builder. We score the phone agent it creates.
*(Figure: one run. You write the orange box, everything else is provided.)*

#### How the weekend goes

- You download the kit from the Data tab. Two briefs, the bank's tool API, thirteen practice customers, the Freya workflow reference and a small working builder.

- You run the sample builder. It creates a phone agent on Freya in your workspace.

- You test that phone agent. Simulated customers talk to it in text. You see which ones it handled correctly and why the others failed.

- You write your own builder and repeat steps 2 and 3 as often as you like.

- On Sunday we publish briefs you have not seen. Same kind of call, different rules: other identity questions, other limits and deadlines, another outcome table, another calendar. The seven tool names stay the same. Their fields and allowed values can change.

- You run your builder once on each new brief and submit the phone agents it created, your code and the builder's trace.

- We test those phone agents on customers nobody has seen. The share they handle correctly is your score.

The three hours in orange are for running the builder and fixing bugs, not for tuning it to the new briefs.  

#### What counts

- Only the phone agents are scored. Your rank comes from their score. We also rerun the builders of the top entries to verify them. Build time is the second tie-break.

- A customer counts as handled when the bank's records are right afterwards and the conversation followed the brief. There is no partial credit.

- The builder must work alone. One command, a brief as input, a phone agent as output. No manual edits after it runs.

- The final briefs are hidden so that a builder tuned to the two public briefs does not win. It has to read a brief it has never seen.

- After the hidden briefs open you may fix a bug in your builder. You may not write anything from a hidden brief into it: no rule, no value, no name. Fixing a crash on a table your parser did not expect is allowed. Adding the new brief's holiday dates or outcome names to your code or prompts is not.

- Calls are in English. The phone agent gets the date and time of the call as a variable, `now`. Every date rule uses it.

- Every phone agent runs on the same Freya model. Your builder may use any model or coding agent you like.

#### Inside a phone agent

A phone agent on Freya is a workflow. Each step has its own prompt and tools. Conditional routes decide which step takes the conversation next. Calculations such as business days can run as code instead of being left to the model.

*(Figure legend: one step · a tool it calls · a route with a condition)*
What a phone agent can look like inside. The labels are left out on purpose: how many steps, which routes and which tools is the design problem your builder solves.

---

## Thirteen practice cases and the kit

Everything here is synthetic. The bank, the customers, the debts and the payments do not exist.

[Download the kit (version 2)](https://www.freyavoice.ai/hackathon/build-the-builder-v2.zip)

Unzip it and read `README.md` first. The kit has a version number in its file name and at the top of `README.md`. To run it you need a Freya API key. Create one in your Freya workspace under API keys.

| File | What it is |
|---|---|
| briefs/brief-a.md | Freya Bank's specification for customers who are late on one product. 47 rules. |
| briefs/brief-b.md | The extra rules for customers with up to three products. Builds on Brief A. |
| tools/openapi.json | The bank's tool API that the phone agent calls. Seven tools: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. |
| public-test-set.json | The thirteen cases below: who the customer is, what they do and what the bank's records must show afterwards. |
| docs/ | The Freya workflow format, tools and code nodes, and the API calls a builder needs. Written for a program to read. |
| freya.py | A small client for the Freya API. Creates a workflow once and updates it on later runs. Standard library only. |
| examples/base-agent.json | An example phone agent: two steps, four tools. The same one that is in your workspace. A place to start, not a good score. |
| examples/agent_builder.py | An example builder on the Claude Agent SDK with one skill. Claude reads the brief, builds the agent, tests it and fixes what fails. |
| env.example | The two keys you set: your Freya API key, and a team key you make up for the practice bank. |
| tools/run_cases.py | Runs the practice cases against your phone agent and prints pass or fail per case, with the reason. |

#### How one case runs
The mock bank API stands in for the bank's own systems. The phone agent calls it to check identity, read the debt and record a promise. We host it, so we can see what was really recorded. The scorer reads that record, not what the phone agent says it did. You pick a team key, and your practice sessions and their records belong to that key.  

#### Practice cases

Ten cases use Brief A and three use Brief B. Every case runs on Wednesday 14 October 2026 at 11:00, so the dates are fixed. Select a row to read the customer script and the checks. Download JSON

*(Tablo sayfada JavaScript ile dolduruluyor; 13 vakanın tamamı `public-test-set.json`'da.)*

---

## One number: the share of hidden cases passed

A case is one simulated customer. It passes only when three checks all pass. There is no partial credit.

The bank's API does not enforce the brief. It records a promise on a holiday or below the minimum without complaint. Keeping the rules is the phone agent's job.
Outcome is read from the bank's records. Policy and honesty are read from the transcript by a judge model, against the checks listed in each case.  
A correct refusal counts. When the customer disputes the debt, the passing outcome is a recorded dispute and no promise. A phone agent that pushes for a promise anyway fails.

#### The final benchmark

| Item | Value |
|---|---|
| Hidden briefs | 2. One is a clean specification. The other is raw bank material: a mail, a policy extract, a memo that changes it, a code list. |
| Customers per brief | 30, with one to three products, on several calendar days |
| How customers talk | Like people: a number said in two parts ("463..." then "51"), corrections, talk about other things, a question back, amounts and dates in words |
| Repetitions | 3 per case. The case passes only when all 3 runs pass. |
| Score | cases passed / 60 |
| First tie-break | Total promised amount recorded on the cases that passed |
| Second tie-break | Shorter total build time, read from the builder's traces |
| Third tie-break | Earlier submission time |

#### Score yourself

The kit includes the scorer. Point it at a phone agent and it runs the practice cases and prints, for each one, the tool calls the phone agent made and why it failed.

```
$ python3 tools/run_cases.py <agent_id> --brief A

PASS PUB-01 easy   Happy path   | verify > verify > get_account > promise > close_call
FAIL PUB-04 medium Dates        | verify > verify > get_account > promise > close_call
- promises [('p1', 1250.0, '2026-10-27')], expected [('p1', 1250.0, '2026-10-23')]
...
5 / 10 passed
```

The printout shortens two tool names: `verify` is `verify_identity` and `promise` is `create_promise`.

A ten-case run takes 3 to 11 minutes. One simulation runs at a time per workspace, and a team has one workspace. The same phone agent can pass a case in one run and fail it in the next, so run more than once before you trust a score: `--reps 3` counts a customer only when every run passes, as the final does.

---

## Two phone agents, one commit and the builder's trace

- On Sunday at 17:00 UTC we send two hidden briefs to every team. Each comes with its own tool API file.

- Run your builder on each brief and keep everything it prints. You may run it more than once. Submit one phone agent per brief, with the trace of the run that made it. Do not edit a phone agent after the run.

- Export each phone agent to a file with `freya.export_workflow` and commit the files. We load them into our own workspace, so what you export is what we score.

- Before 20:00 UTC, send the form below to the address in your kit email.

```
$ python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log
```

```
{
"team": "your-team-name",
"repo": "https://github.com/you/your-builder",
"commit": "9f2c1ab",
"run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
"workflows": {
"hidden-1": "submission/hidden-1.workflow.json",
"hidden-2": "submission/hidden-2.workflow.json"
},
"traces": {
"hidden-1": "traces/hidden-1.log",
"hidden-2": "traces/hidden-2.log"
}
}
```

#### The builder's trace

A trace is the record of one builder run: what it read, what it decided and what it created. We ask for one per hidden brief. Commit the files to your repository.

| In the trace | Why |
|---|---|
| Start and end time of the run | Build time breaks ties between equal scores. |
| Every model call the builder made: which model, and what it was asked for in one line | Shows how the builder works, not only what it produced. |
| What it created on Freya: workflow id, agent id, number of steps and tools | Ties the phone agent you submit to this run. |
| Any test it ran on its own phone agent, with the result | A builder that checks its own work is the point of the exercise. |

Plain text is fine. There is no required format. Remove API keys before you commit.

If you built your builder with a coding agent such as Claude Code or Codex, you may also share those session logs. This is optional. The top three teams talk their approach through with us, and a log is the easiest way to show it.

#### How we verify

We test the phone agents you submitted. For the top ten teams we also clone the repository at that commit, run the builder ourselves on the same briefs and compare with your trace. Every trace is also read by a reviewer agent that checks it against the submitted code and the phone agent it claims to have created. If our run scores clearly below yours, the entry is removed. We do this to catch phone agents that were edited by hand.

#### Limits

| Limit | Value |
|---|---|
| Builder run time | 30 minutes per brief, including any test the builder runs on its own phone agent |
| Workflows per workspace | 200. Update one in place instead of creating a new one per run. |
| Models the builder may use | Any. You pay for your builder's own model calls. |
| Model the phone agent runs on | The Freya model set in `freya.py`. The same for every team. Do not change it. |
| Practice simulations | 1 running at a time per workspace |

---

## Rules

- Enter solo or as a team of two.

- You submit a builder. A hand-built phone agent on its own is not a valid entry.

- The phone agents for the hidden briefs must come out of the submitted commit with no manual edits.

- Submit one builder trace per hidden brief. An entry without traces is not ranked.

- The phone agent may call only the tool API from the kit. A call to any other service fails the case.

- Do not probe or load-test the platform. One Freya key per team.

- You may fix your builder after the hidden briefs open. Nothing from a hidden brief may be written into it. A reviewer checks the commit for that.

- All data is synthetic. Do not bring real customer data.

#### Prizes

| Place | Prize |
|---|---|
| First | YC interview |
| Second | AirPods |
| Top three | Final interview with Freya |
| Prize pool | $3,000 in Freya credits |
