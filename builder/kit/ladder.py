"""The persuasion ladder: one node per offer, so that "how many attempts are left" is a place in the graph, not a memory.

The brief decides the shape (which offer follows which answer). The kit makes every step the same way:
- the offer is a fixed line computed in code (`say`, usually "{{var}}") spoken on entry,
- the customer's last message is classified into one of REPLY_KINDS by an extraction field of this step only,
- a deterministic route picks the next step, a situation node, or a close,
- inside a step the model handles what is not counting: a proposed date or amount, the read-back, the promise call.

Spec (JSON, from the brief):
{
  "rules": ["negotiation rules from the brief that hold in every step, one sentence each"],
  "facts": "text with {{vars}} the code node set: amounts, deadline, date table",
  "record": "now" | "defer",
  "promise_tool": "name of the promise tool (record now only)",
  "on_recorded": "node after a recorded promise", "record_failures": 2, "on_record_failed": "node after that many failed calls",
  "on_agreed": "node after an agreement (record defer only; agreed_amount / agreed_date are extracted)",
  "situations": {"paid": "node", "dispute": "node", "hardship": "node", "new_plan": "node", "human": "node"},
  "start": "first step",
  "steps": {
    "<step>": {"say": "line spoken on entry, or empty", "task": "what this step offers and what to do",
               "on": {"<reply kind>": "<node>" or [{"if": {"<var>": "<value>"}, "go": "<node>"}, {"go": "<node>"}]}}
  }
}
A reply kind that a step's `on` does not name keeps the conversation in the step. `too_much` and `no_talk` fall back to the
step's `refuses` route when they are not named, because the briefs count them as a refusal of the offer on the table.
"""
from . import graph as g

REPLY_KINDS = {
    "accepts": "they say yes to the offer just made, or agree to pay on the offered terms",
    "proposes": "they propose their own date or amount, or change the date or amount (a proposal is never a refusal)",
    "confirms": "they say yes to the read-back question that asks them to confirm",
    "refuses": "a flat no to the offer on the table or to paying, with no date and no amount, or no real answer",
    "too_much": "they say the amount is too much or more than they can afford, without proposing another amount",
    "no_talk": "they say they do not want to talk",
    "paid": "they say they have ALREADY paid this past-due amount. Saying they WILL pay is not this. Chat about their day is never this",
    "dispute": "they say the debt is not theirs, they never had the product, or it was closed or paid off in the past",
    "hardship": "they mention illness, a death in the family or losing their job",
    "new_plan": "they ask for a new payment plan or lower instalments. Asking for a discount or saying the amount is too much is NOT this",
    "human": "they ask to speak to a human",
    "question": "they ask a question",
    "chat": "they talk about something unrelated (their day, traffic, family events)",
}
FALLBACK_TO_REFUSES = ("too_much", "no_talk")


def _route(kind, rule, var, node_of):
    """`rule` is a target, or a list of {"if": {var: value}, "go": target} tried in order. A target is a step or a node."""
    if isinstance(rule, str):
        return [g.eq(node_of(rule), var, kind, f"customer: {kind}")]
    out = []
    for r in rule:
        conds = [(var, kind)] + [(k, v) for k, v in (r.get("if") or {}).items()]
        out.append(g.and_eq(node_of(r["go"]), [conds], f"customer: {kind}" + (f" and {r['if']}" if r.get("if") else "")))
    return out


def build(api, spec, tools, prefix="neg_", max_turns=12, turn_limit_target=None):
    """Return {node_key: node} for the ladder steps, named `{prefix}<step>`; enter at `{prefix}<start>`.
    `tools`: tool objects every step offers. Targets in `on` are step names or other node names."""
    record_now = spec.get("record", "now") == "now"
    kinds = dict(REPLY_KINDS)
    if not record_now:
        kinds.pop("confirms")
    base_rules = "\n".join("- " + r for r in spec.get("rules") or [])
    node_of = lambda t: prefix + t if t in spec["steps"] else t  # noqa: E731
    nodes = {}
    for step, s in spec["steps"].items():
        name = prefix + step
        var = name + "_turn"
        trs = []
        if record_now:
            pt = spec["promise_tool"]
            trs.append(g.is_true(spec["on_recorded"], f"{pt}_response.data.ok", "The promise was recorded"))
            trs.append(g.greater(spec["on_record_failed"], f"{pt}_failure_count", int(spec.get("record_failures", 2)) - 1, "Recording failed too often"))
        else:
            trs.append(g.and_eq(spec["on_agreed"], [[(var, "accepts")]], "Agreed"))
        for kind, target in (spec.get("situations") or {}).items():
            if kind in kinds:
                trs.append(g.eq(target, var, kind, f"customer: {kind}"))
        on = dict(s.get("on") or {})
        for k in FALLBACK_TO_REFUSES:
            if k not in on and "refuses" in on:
                on[k] = on["refuses"]
        for kind, rule in on.items():
            trs += _route(kind, rule, var, node_of)
        how = ("When amount and date are agreed, read back the product, the amount and the date and ask the customer to confirm. "
               f"Only after a clear yes, call {spec.get('promise_tool')}. If its result is not ok, nothing was recorded: never say it was.") if record_now else \
              "When the customer accepts an offer, repeat the amount and the date in one sentence. Do not call any tool."
        task = ("The customer's identity is verified.\n\nFACTS (computed, trust them; never compute a date or an amount yourself):\n" + spec.get("facts", "") +
                "\n\nRULES FOR EVERY STEP:\n" + base_rules + "\n- A date or amount the customer proposes is never a refusal: check it against the facts and answer it."
                "\n- If the customer corrects a date or an amount, use the corrected value." "\n- " + how +
                "\n- Never make an offer that this step does not name. The system moves to the next offer by itself when the customer refuses."
                "\n\nTHIS STEP:\n" + s["task"])
        extract = [g.enum_field(var, list(kinds), "Classify ONLY the customer's last message. " + " ".join(f"{k}: {v}." for k, v in kinds.items()))]
        if not record_now:
            extract += [{"name": "agreed_amount", "type": "float", "description": "The amount the customer agreed to pay, if they agreed", "min_confidence": 0.6},
                        {"name": "agreed_date", "type": "date", "description": "The date the customer agreed to pay on, if they agreed", "min_confidence": 0.6}]
        nodes[name] = g.conversation(name, task, trs, tools=tools, extract=extract,
                                     on_enter={"type": "tts", "text": s["say"]} if s.get("say") else {"type": "llm", "prompt": s["task"]},
                                     max_turns=max_turns, max_turn_target=turn_limit_target)
    return nodes


def check(spec, known_nodes):
    """Problems in a ladder spec: unknown targets, unknown reply kinds. Empty list means fine."""
    errs = []
    names = set(known_nodes) | set(spec["steps"])
    if spec["start"] not in spec["steps"]:
        errs.append(f"start {spec['start']!r} is not a step")
    for step, s in spec["steps"].items():
        for kind, rule in (s.get("on") or {}).items():
            if kind not in REPLY_KINDS:
                errs.append(f"{step}: unknown reply kind {kind!r}")
            for r in ([{"go": rule}] if isinstance(rule, str) else rule):
                if r["go"] not in names:
                    errs.append(f"{step}: {kind} goes to unknown node {r['go']!r}")
    return errs
