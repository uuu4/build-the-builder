"""The back half for a customer with several late products: one persuasion ladder per product, in code.

Why it exists. A single negotiation node that is told "attempts are counted per product" loses count (PUB-12), and
a model that is told "a product's date may not pass its deadline" records the customer's date (PUB-13). Here the
graph holds the count (every product has its own copy of the ladder), and code holds the dates (every agreed date
is clamped to that product's deadline before it is read back).

Flow (K = spec["slots"], the most products a customer can have):

    m_today                 "can you pay all of them today?" (a ladder step, so refusals are classified the same way)
    enter_1 .. enter_K      code: which product is next? none left -> finish; a date the customer gave for everything
                            earlier -> agree this product on it (clamped) without asking; else its ladder
    p<k>_<step>             the ladder of product k (builder/kit/ladder.py, record "defer"), one copy per product
    save_<k>_<step>         code: the agreed amount and date of product k, date clamped to s<k>_deadline_iso
    refused_<k> paid_<k> dispute_<k>   code: product k gets no promise, reason noted for the end
    finish                  code: the read-back line of every agreed product, all in one message
    m_readback, m_fix       the one confirmation; a change is applied by code and read back again
    rg_<k> rec_<k> note_<k> the record stage: create_promise for agreed products (one retry), add_note for the others
    final                   code: promise if any promise was recorded, paid if every product is noted paid, else the
                            reason of the first product (in account order) whose note is not paid
    hardship, human_check, transfer_*, close_*   shared. Notes are written only at the end, so a transfer
                            (which allows no notes at all) never has one before it.

State the code nodes keep, per product k: st_<k> ('' | 'agreed' | 'noted'), amt_<k>, date_<k>, adj_<k> ('1' when
the date was moved to the deadline), reason_<k>, rec_ok_<k>. Shared: cur_slot, carry_date, floor_first.
The product facts come from builder/kit/dates.py with `slots`: s<k>_pid, s<k>_label, s<k>_due, s<k>_floor,
s<k>_deadline (ISO), s<k>_deadline_text, s<k>_attempts, s<k>_line_<name>.

Spec (JSON, every value from the brief; the ladder template is a ladder.py spec in which "{k}" stands for the product):
{
  "slots": 3,
  "today": {"say": "{{debt_statement}}", "task": "...", "rules": ["..."], "facts": "{{date_facts}}"},
  "ladder": {ladder.py spec; node names it may use: save_{k} (the agreed exit, rewritten per step), refused_{k},
             paid_{k}, dispute_{k}, hardship, transfer_new_plan, human_check; variables as s{k}_attempts;
             "start" is the first step, "start_floor" the first step when the customer already said the full amount is
             too much; a step may carry "offer": {"amount_var": "s{k}_due", "date_var": "end_of_week_iso"}, the
             variables holding the amount and date it proposed, used when the customer just says yes},
  "readback": {"intro": "Let me read back what we agreed. ", "item": "<label>: <amount> on <date>",
               "adjusted": " (the latest date I can record for it)", "sep": "; ", "ask": " Do you confirm?"},
  "hardship": {"say": "...", "task": "..."},          optional, defaults below
  "human": {"ask_first": "..."},
  "reasons": {"refused": "<note reason>", "hardship": "...", "dispute": "...", "paid": "...", "service_error": "..."},
  "queues": {"new_plan": "<queue value>", "hardship": "...", "human": "..."},
  "closes": {"promise": {"outcome": "...", "farewell": "..."}, "paid": {"outcome": "...", "farewell": "..."},
             "other": {"outcome": "...", "farewell": "..."},    the reason comes from the notes (first one that is not "paid")
             "new_plan": {"outcome": "...", "reason": "...", "farewell": "..."}, "hardship": {...}, "human": {...},
             "error": {"outcome": "...", "reason": "...", "farewell": "..."}},
  "situations": {"paid": "sentence spoken when the customer says a product is paid", "dispute": "..."},   optional
  "tools": {"promise": "create_promise", "note": "add_note", "transfer": "transfer_to_agent"}   optional
}
`build` returns the nodes; enter at `m_today`. Targets it uses that you provide: nothing (every node is built here).
"""
import copy
import json

from . import graph as g
from . import ladder
from .pycode import with_params

KINDS_TODAY = ("accepts",)


def _sub(obj, k):
    """Replace {k} (single braces) with the product number in every string of a ladder template."""
    return json.loads(json.dumps(obj).replace("{k}", str(k)))


def _code(name, body, next_node, transitions=(), **params):
    """A code node whose route lives in its own variable r_<name>, so a value left by another node can never steer
    this one. When the sandbox did not run the code (the variable is still unset) the node is tried once more
    (`<name>_again`, added by `_add_retries`) and then the call closes; the default is never "carry on"."""
    rv = "r_" + name
    trs = []
    for t in transitions:
        t = copy.deepcopy(t)
        t["condition"]["conditions"][0]["variable"] = rv
        t["description"] = t["description"].replace(t["description"].split(" is ")[0], rv, 1)
        trs.append(t)
    n = g.code(name, with_params(body, dict(params, rv=rv)), next_node, trs)
    n["_rv"] = rv
    return n


def _add_retries(nodes):
    for name, n in list(nodes.items()):
        rv = n.pop("_rv", None)
        if not rv:
            continue
        twin = copy.deepcopy(n)
        twin["name"] = name + "_again"
        nodes[name + "_again"] = twin
        n["transitions"] = n["transitions"][:-1] + [g.unset(name + "_again", rv, "the code did not run")] + n["transitions"][-1:]


# ---------------------------------------------------------------- code node sources
# Helpers from pycode.CALENDAR are in scope: P, isbiz, nextbiz, say, num, money, get_now, json, datetime, re.

_ENTER = r'''
try:
    k = P['k']
    n = int(num(vars.get('product_count')))
    vars['cur_slot'] = str(k)
    cd = str(vars.get('carry_date') or '')
    if k > n:
        vars[P['rv']] = 'done'
    elif cd != '':
        dl = str(vars.get('s%d_deadline' % k) or '')
        d = cd
        adj = ''
        if dl != '' and d > dl:
            d = dl
            adj = '1'
        vars['st_%d' % k] = 'agreed'
        vars['amt_%d' % k] = money(vars.get('s%d_due' % k))
        vars['date_%d' % k] = d
        vars['adj_%d' % k] = adj
        vars[P['rv']] = 'auto'
    elif str(vars.get('floor_first') or '') == '1' and k == 1:
        vars['floor_first'] = ''
        vars[P['rv']] = 'ask_floor'
    else:
        vars[P['rv']] = 'ask'
except Exception:
    vars[P['rv']] = 'error'
'''

_SAVE = r'''
try:
    k = P['k']
    d = str(vars.get('agreed_date') or '')[:10]
    if d == '' and P['offer_date_var'] != '':
        d = str(vars.get(P['offer_date_var']) or '')[:10]
    a = num(vars.get('agreed_amount'), 0.0)
    if a <= 0 and P['offer_amount_var'] != '':
        a = num(vars.get(P['offer_amount_var']), 0.0)
    due = num(vars.get('s%d_due' % k))
    if a <= 0 or a > due:
        a = due
    dl = str(vars.get('s%d_deadline' % k) or '')
    adj = ''
    if dl != '' and d > dl:
        d = dl
        adj = '1'
    vars['st_%d' % k] = 'agreed'
    vars['amt_%d' % k] = money(a)
    vars['date_%d' % k] = d
    vars['adj_%d' % k] = adj
    if str(vars.get(P['all_var']) or '') == 'yes':
        vars['carry_date'] = str(vars.get('agreed_date') or '')[:10] or d
    vars['agreed_date'] = ''
    vars['agreed_amount'] = ''
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_MARK = r'''
try:
    k = P['k']
    vars['st_%d' % k] = 'noted'
    vars['reason_%d' % k] = P['reasons'][P['why']]
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_ALL_YES = r'''
try:
    n = int(num(vars.get('product_count')))
    d0 = str(vars.get('agreed_date') or '')[:10]
    if d0 == '':
        d0 = str(vars.get('today') or '')
    for k in range(1, n + 1):
        dl = str(vars.get('s%d_deadline' % k) or '')
        d = d0
        adj = ''
        if dl != '' and d > dl:
            d = dl
            adj = '1'
        vars['st_%d' % k] = 'agreed'
        vars['amt_%d' % k] = money(vars.get('s%d_due' % k))
        vars['date_%d' % k] = d
        vars['adj_%d' % k] = adj
    vars['agreed_date'] = ''
    vars['agreed_amount'] = ''
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_FLOOR_MARK = r'''
vars['floor_first'] = '1'
vars[P['rv']] = 'ok'
'''

_HARDSHIP_MARK = r'''
try:
    n = int(num(vars.get('product_count')))
    for k in range(1, n + 1):
        if str(vars.get('st_%d' % k) or '') == '':
            vars['st_%d' % k] = 'noted'
            vars['reason_%d' % k] = P['reasons']['hardship']
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_FINISH = r'''
try:
    n = int(num(vars.get('product_count')))
    R = P['readback']
    parts = []
    for k in range(1, n + 1):
        if str(vars.get('st_%d' % k) or '') != 'agreed':
            continue
        d = datetime.date.fromisoformat(str(vars.get('date_%d' % k)))
        item = R['item'].replace('<label>', str(vars.get('s%d_label' % k))).replace('<amount>', str(vars.get('amt_%d' % k))).replace('<date>', say(d))
        if str(vars.get('adj_%d' % k) or '') == '1':
            item = item + R['adjusted'].replace('<label>', str(vars.get('s%d_label' % k)))
        parts.append(item)
    if parts:
        vars['readback'] = R['intro'] + R['sep'].join(parts) + '.' + R['ask']
        vars[P['rv']] = 'readback'
    else:
        vars['readback'] = ''
        vars[P['rv']] = 'record'
except Exception:
    vars[P['rv']] = 'error'
'''

_APPLY_FIX = r'''
try:
    n = int(num(vars.get('product_count')))
    kind = str(vars.get('fix_kind') or '')
    slot = str(vars.get('fix_slot') or '')
    targets = list(range(1, n + 1)) if slot == 'all' else [int(slot)] if slot.isdigit() else []
    for k in targets:
        if k < 1 or k > n or str(vars.get('st_%d' % k) or '') != 'agreed':
            continue
        if kind == 'drop':
            vars['st_%d' % k] = 'noted'
            vars['reason_%d' % k] = P['reasons']['refused']
            continue
        due = num(vars.get('s%d_due' % k))
        fd = str(vars.get('fix_date') or '')[:10]
        if fd != '':
            dl = str(vars.get('s%d_deadline' % k) or '')
            adj = ''
            if dl != '' and fd > dl:
                fd = dl
                adj = '1'
            vars['date_%d' % k] = fd
            vars['adj_%d' % k] = adj
        fa = num(vars.get('fix_amount'), 0.0)
        if fa > 0 and fa <= due:
            vars['amt_%d' % k] = money(fa)
    vars['fix_kind'] = ''
    vars['fix_slot'] = ''
    vars['fix_date'] = ''
    vars['fix_amount'] = ''
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_GATE = r'''
k = P['k']
st = str(vars.get('st_%d' % k) or '')
if st == 'agreed':
    vars[P['rv']] = 'promise'
elif st == 'noted' and str(vars.get('reason_%d' % k) or '') != '':
    vars[P['rv']] = 'note'
else:
    vars[P['rv']] = 'skip'
'''

_REC_OK = r'''
vars['rec_ok_%d' % P['k']] = '1'
vars[P['rv']] = 'ok'
'''

_REC_FAIL = r'''
k = P['k']
vars['st_%d' % k] = 'noted'
vars['reason_%d' % k] = P['reasons']['service_error']
vars[P['rv']] = 'failed'
'''

_FINAL = r'''
try:
    n = int(num(vars.get('product_count')))
    recorded = False
    reasons = []
    for k in range(1, n + 1):
        if str(vars.get('rec_ok_%d' % k) or '') == '1':
            recorded = True
        elif str(vars.get('st_%d' % k) or '') == 'noted':
            reasons.append(str(vars.get('reason_%d' % k) or P['reasons']['refused']))
    R = P['reasons']
    if recorded:
        vars['final_outcome'] = P['outcomes']['promise']
        vars['final_reason'] = ''
        vars[P['rv']] = 'promise'
    elif reasons and all([r == R['paid'] for r in reasons]) and len(reasons) == n:
        vars['final_outcome'] = P['outcomes']['paid']
        vars['final_reason'] = ''
        vars[P['rv']] = 'paid'
    else:
        others = [r for r in reasons if r != R['paid']]
        vars['final_outcome'] = P['outcomes']['other']
        vars['final_reason'] = others[0] if others else R['refused']
        vars[P['rv']] = 'other'
except Exception:
    vars[P['rv']] = 'error'
'''


def _eqs(var, mapping):
    return [g.eq(target, var, val, f"{var} is {val}") for val, target in mapping]


def build(api, spec, ladder_tpl=None):
    """Return {node_name: node}. `spec` as in the module docstring; `ladder_tpl` defaults to spec["ladder"]."""
    K = int(spec["slots"])
    tpl = copy.deepcopy(ladder_tpl or spec["ladder"])
    tools = {"promise": "create_promise", "note": "add_note", "transfer": "transfer_to_agent", **(spec.get("tools") or {})}
    closes = spec["closes"]
    reasons = dict(spec["reasons"])      # logical reason -> the value the bank's note tool takes
    outcomes = {"promise": closes["promise"]["outcome"], "paid": closes["paid"]["outcome"], "other": closes["other"]["outcome"]}
    queues = spec["queues"]              # logical situation -> queue value
    nodes = {}
    base_rules = list(spec.get("today", {}).get("rules") or [])

    # --- "can you pay all of them today?"
    t = spec["today"]
    today_spec = {"rules": base_rules, "facts": t.get("facts", ""), "record": "defer", "on_agreed": "all_yes",
                  "situations": {"paid": "enter_1", "dispute": "enter_1", "hardship": "hardship",
                                 "new_plan": "transfer_new_plan", "human": "human_check"},
                  "start": "today",
                  "steps": {"today": {"say": t["say"], "task": t["task"],
                                      "on": {"refuses": "enter_1", "too_much": "floor_mark"}}}}
    nodes.update(ladder.build(api, today_spec, [], prefix="m_", max_turns=10, turn_limit_target="enter_1"))
    nodes["all_yes"] = _code("all_yes", _ALL_YES, "close_error", _eqs("all_route", [("ok", "finish")]))
    nodes["floor_mark"] = _code("floor_mark", _FLOOR_MARK, "close_error", _eqs("floor_route", [("ok", "enter_1")]))

    # --- one ladder per product
    start, start_floor = tpl["start"], tpl.get("start_floor") or tpl["start"]
    for k in range(1, K + 1):
        lk = _sub(tpl, k)
        lk["record"] = "defer"
        lk["on_agreed"] = f"save_{k}"
        steps = lk["steps"]
        built = ladder.build(api, {kk: vv for kk, vv in lk.items() if kk != "start_floor"}, [], prefix=f"p{k}_", max_turns=12,
                             turn_limit_target=f"refused_{k}")
        for step, s in steps.items():
            node = built[f"p{k}_{step}"]
            allvar = f"p{k}_{step}_all"
            node["extraction_schema"].append(g.enum_field(
                allvar, ["yes", "no"],
                "yes ONLY if the customer says the date they agreed to is for ALL their products together (for example "
                "'Friday for all of them', 'I will pay everything on the 30th'). Otherwise no.", 0.7))
            for tr in node["transitions"]:
                if tr["target_node"] == f"save_{k}":
                    tr["target_node"] = f"save_{k}_{step}"
            off = s.get("offer") or {}
            nodes[f"save_{k}_{step}"] = _code(
                f"save_{k}_{step}", _SAVE, "close_error",
                _eqs("save_route", [("ok", f"enter_{k + 1}" if k < K else "finish")]),
                k=k, all_var=allvar, offer_date_var=off.get("date_var", ""), offer_amount_var=off.get("amount_var", ""))
        nodes.update(built)
        nxt = f"enter_{k + 1}" if k < K else "finish"
        nodes[f"enter_{k}"] = _code(
            f"enter_{k}", _ENTER, "close_error",
            _eqs("enter_route", [("ask", f"p{k}_{start}"), ("ask_floor", f"p{k}_{start_floor}"), ("auto", nxt), ("done", "finish")]), k=k)
        for why, nm in (("refused", f"refused_{k}"), ("paid", f"paid_{k}"), ("dispute", f"dispute_{k}")):
            nodes[nm] = _code(nm, _MARK, "close_error", _eqs("mark_route", [("ok", nxt)]), k=k, why=why, reasons=reasons)
            line = (spec.get("situations") or {}).get(why)
            if line:      # a sentence the brief requires when the customer says it (for "paid": payments take a business day to appear)
                nodes[nm]["on_enter"] = {"type": "tts", "text": line}

    # --- read-back and confirmation
    nodes["finish"] = _code("finish", _FINISH, "close_error",
                            _eqs("finish_route", [("readback", "m_readback"), ("record", "rg_1")]), readback=spec["readback"])
    rb_kinds = ["confirms", "changes", "other"]
    nodes["m_readback"] = g.conversation(
        "m_readback",
        "You have read back every agreed promise in one message and asked for one confirmation. The customer's identity is verified.\n"
        "- A clear yes is a confirmation. Do not call any tool; the system records the promises.\n"
        "- If they want to change a date or an amount, or drop a product, say nothing about recording: the system asks what to change.\n"
        "- Never say anything is recorded or booked.",
        [g.eq("rg_1", "rb_turn", "confirms", "confirmed"), g.eq("m_fix", "rb_turn", "changes", "wants a change")],
        extract=[g.enum_field("rb_turn", rb_kinds,
                              "Classify ONLY the customer's last message. confirms: a clear yes to the read-back. changes: they want a different date or amount, "
                              "want to drop a product, or say no. other: a question or anything else.")],
        on_enter={"type": "tts", "text": "{{readback}}"}, max_turns=6, max_turn_target="m_fix")
    nodes["m_fix"] = g.conversation(
        "m_fix",
        "The customer wants to change something in what you read back. The customer's identity is verified.\n"
        "Find out which product and what: a new date, a new amount, or dropping it. Do not compute dates yourself; just collect what they say. "
        "Product numbers follow the order of the read-back (1 is the first product read).",
        [g.any_eq("apply_fix", "fix_kind", ["change", "drop"], "a change was named"), g.eq("finish", "fix_kind", "none", "no change after all")],
        extract=[g.enum_field("fix_kind", ["change", "drop", "none", "unknown"],
                              "change: they name a new date or amount. drop: they no longer want to promise a product. none: they changed their mind and the read-back is fine. unknown: not yet clear.", 0.7),
                 g.enum_field("fix_slot", ["1", "2", "3", "4", "all", "unknown"],
                              "Which product, by its position in the read-back (1 = first product read). 'all' if they mean every product.", 0.7),
                 {"name": "fix_date", "type": "date", "description": "The new date, if they named one", "min_confidence": 0.6},
                 {"name": "fix_amount", "type": "float", "description": "The new amount, if they named one", "min_confidence": 0.6}],
        on_enter={"type": "llm", "prompt": "Ask what they would like to change."}, max_turns=6, max_turn_target="finish")
    nodes["apply_fix"] = _code("apply_fix", _APPLY_FIX, "close_error", _eqs("fix_route", [("ok", "finish")]), reasons=reasons)

    # --- record stage
    pt, nt = tools["promise"], tools["note"]
    for k in range(1, K + 1):
        nxt = f"rg_{k + 1}" if k < K else "final"
        nodes[f"rg_{k}"] = _code(f"rg_{k}", _GATE, "close_error",
                                  _eqs("gate_route", [("promise", f"rec_{k}"), ("note", f"note_{k}"), ("skip", nxt)]), k=k)
        nodes[f"rec_{k}"] = g.api_request(
            f"rec_{k}",
            api.pre_action(pt, {"product_id": "{{s%d_pid}}" % k, "amount": "{{amt_%d}}" % k, "date": "{{date_%d}}" % k}, retries=1),
            f"recfail_{k}", transitions=[g.is_true(f"recok_{k}", f"rec_{k}_response.data.ok", "recorded")])
        nodes[f"recok_{k}"] = _code(f"recok_{k}", _REC_OK, "close_error", _eqs("rec_route", [("ok", nxt)]), k=k)
        nodes[f"recfail_{k}"] = _code(f"recfail_{k}", _REC_FAIL, "close_error", _eqs("rec_route", [("failed", f"note_{k}")]), k=k, reasons=reasons)
        nodes[f"note_{k}"] = g.api_request(
            f"note_{k}", api.pre_action(nt, {"product_id": "{{s%d_pid}}" % k, "reason": "{{reason_%d}}" % k}, retries=2), nxt)
    nodes["final"] = _code("final", _FINAL, "close_error",
                           _eqs("final_route", [("promise", "close_promise"), ("paid", "close_paid"), ("other", "close_other")]),
                           reasons=reasons, outcomes=outcomes)

    # --- shared situations
    nodes["hardship_mark"] = _code("hardship_mark", _HARDSHIP_MARK, "close_error", _eqs("hs_route", [("ok", "finish")]), reasons=reasons)
    hs = spec.get("hardship") or {}
    nodes["hardship"] = g.conversation(
        "hardship",
        hs.get("task") or ("The customer's identity is verified. The customer mentioned illness, a death in the family or job loss. "
                           "Make NO persuasion attempt and offer no payment. If they themselves name a date or an amount, say you will take it; the system handles it."),
        [g.eq("transfer_hardship", "hs_turn", "accepts_transfer", "accepts transfer"),
         g.eq("hardship_mark", "hs_turn", "declines_transfer", "declines transfer")]
        + [g.and_eq(f"p{k}_{start}", [[("cur_slot", str(k)), ("hs_turn", "proposes")]], "names a payment") for k in range(1, K + 1)],
        extract=[g.enum_field("hs_turn", ["accepts_transfer", "declines_transfer", "proposes", "other"],
                              "Classify ONLY the customer's last message. accepts_transfer: yes to being connected with the support team. declines_transfer: no to being connected, "
                              "or they want to end the call. proposes: they name a payment date or amount. other: anything else.")],
        on_enter={"type": "llm", "prompt": hs.get("say") or "Say one short sentence of sympathy. Then ask whether they would like to be connected with our customer support team. Do not mention any payment."},
        max_turns=8, max_turn_target="hardship_mark")
    back = [g.and_eq(f"p{k}_{start}", [[("cur_slot", str(k)), ("hc_turn", "lets_you_help")]], "lets you help") for k in range(1, K + 1)]
    nodes["human_check"] = g.conversation(
        "human_check",
        "The customer asked for a human. You asked once whether you can help. If they want help from you, help with their question briefly.",
        [g.eq("transfer_human", "hc_turn", "insists", "insists on human")] + back + [g.eq("m_today", "hc_turn", "lets_you_help", "back to the start")],
        extract=[g.enum_field("hc_turn", ["insists", "lets_you_help", "other"],
                              "Classify ONLY the customer's last message. insists: they still want a human. lets_you_help: they accept that you help or go on with the conversation. other: anything else.")],
        on_enter={"type": "tts", "text": spec["human"]["ask_first"]}, max_turns=4, max_turn_target="transfer_human")

    # --- transfers and closes
    for key in ("new_plan", "hardship", "human"):
        c = closes[key]
        nodes[f"transfer_{key}"] = g.api_request(f"transfer_{key}", api.pre_action(tools["transfer"], {"queue": queues[key]}, retries=2), f"close_{key}")
        nodes[f"close_{key}"] = g.close(api, f"close_{key}", c["outcome"], c.get("reason", ""), c["farewell"])
    nodes["close_promise"] = g.close(api, "close_promise", outcomes["promise"], "", closes["promise"]["farewell"])
    nodes["close_paid"] = g.close(api, "close_paid", outcomes["paid"], "", closes["paid"]["farewell"])
    nodes["close_other"] = g.close_from_vars(api, "close_other", closes["other"]["farewell"])
    e = closes["error"]
    nodes["close_error"] = g.close(api, "close_error", e["outcome"], e.get("reason", ""), e["farewell"])
    _add_retries(nodes)
    return nodes


def entry():
    return "m_today"
