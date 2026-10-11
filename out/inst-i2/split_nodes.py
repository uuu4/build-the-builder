"""Rule 26 / 26a / 36: the two-instalment split. The kit does not build it; recording copies the kit's pattern
(two explicit tries per call, a separate failure close)."""
from builder.kit import graph as g
from builder.kit.pycode import with_params

SPLIT_BODY = """
try:
    cents = int(round(num(vars.get('s1_due')) * 100))
    h = (cents + 1) // 2
    rest = cents - h
    today = get_now().date()
    dl = datetime.date.fromisoformat(str(vars.get('s1_deadline'))[:10])
    def eow(base):
        d = base + datetime.timedelta(days=6 - base.weekday())
        while not isbiz(d) and d > base:
            d = d - ONE
        return d
    d1 = eow(today)
    if d1 <= today:
        d1 = eow(today + datetime.timedelta(days=7))
    if d1 > dl:
        d1 = dl
    d2 = dl
    if d2 <= d1:
        d2 = nextbiz(d1)
    a1 = '%.2f' % (h / 100.0)
    a2 = '%.2f' % (rest / 100.0)
    vars['split_a1'] = a1
    vars['split_a2'] = a2
    vars['split_d1'] = d1.isoformat()
    vars['split_d2'] = d2.isoformat()
    lab = str(vars.get('s1_label') or '')
    vars['split_line'] = ('I understand. I can offer to split the past-due amount of ' + money(cents / 100.0) + ' into two instalments: '
        + money(a1) + ' on ' + say(d1) + ', and ' + money(a2) + ' on ' + say(d2) + '. Would that work for you?')
    vars['split_rb'] = ('Let me read back what we agreed. For your ' + lab + ': a first instalment of ' + money(a1) + ' on ' + say(d1)
        + ', and a second instalment of ' + money(a2) + ' on ' + say(d2) + '. Do you confirm?')
    vars['r_split'] = 'ok'
except Exception:
    vars['r_split'] = 'error'
"""

SIT = [("paid", "paid_1"), ("dispute", "dispute_1"), ("hardship", "hardship"), ("new_plan", "transfer_new_plan"), ("human", "human_check")]
SIT_DESC = ("paid: they say they have ALREADY paid this past-due amount (saying they will pay is not this; chat is never this). "
            "dispute: the debt is not theirs, they never had the product, or it was closed or paid off. "
            "hardship: illness, a death in the family or job loss. new_plan: they ask for three or more parts, a new payment plan or lower instalments. "
            "human: they ask for a human. ")


def build(api, fspec, mspec):
    nodes = {}
    src = with_params(SPLIT_BODY, {"holidays": fspec["calendar"]["holidays"], "weekend_days": fspec["calendar"]["weekend_days"]})
    nodes["split_calc"] = g.code("split_calc", src, "p1_floor_b", [g.eq("split_offer", "r_split", "ok", "split computed")])
    nodes["split_offer"] = g.conversation(
        "split_offer",
        "The customer's identity is verified. They said the full past-due amount is too much. In your last message you offered to split the "
        "past-due amount into two instalments: {{split_a1}} on {{split_d1}} and {{split_a2}} on {{split_d2}}. Never compute other amounts or dates. "
        "Answer questions briefly from these facts. Do not read anything back and never say anything was recorded. Make no other offer. "
        "After every tool result speak; do not say goodbye yourself.",
        [g.eq("split_rb", "split_turn", "accepts", "accepts split"),
         g.any_eq("p1_attempt1_floor", "split_turn", ["refuses", "too_much"], "refuses split")]
        + [g.eq(t, "split_turn", k, k) for k, t in SIT],
        extract=[g.enum_field("split_turn", ["accepts", "refuses", "too_much", "paid", "dispute", "hardship", "new_plan", "human", "question", "chat"],
                              "Classify ONLY the customer's last message. accepts: yes to the two instalments. refuses: no to the split, or no real answer. "
                              "too_much: the instalments are still too much. " + SIT_DESC + "question: they ask a question. chat: anything else.")],
        on_enter={"type": "tts", "text": "{{split_line}}"}, max_turns=8, max_turn_target="p1_attempt1_floor")
    nodes["split_rb"] = g.conversation(
        "split_rb",
        "You read back the two instalments and asked 'Do you confirm?'. Do not call any tool; the system records them. Never say anything was recorded. "
        "If they ask to change something, say these are the instalments you can offer. Do not say goodbye yourself.",
        [g.eq("split_rec1", "splitrb_turn", "confirms", "confirms"),
         g.eq("p1_attempt1_floor", "splitrb_turn", "refuses", "refuses")]
        + [g.eq(t, "splitrb_turn", k, k) for k, t in SIT],
        extract=[g.enum_field("splitrb_turn", ["confirms", "refuses", "paid", "dispute", "hardship", "new_plan", "human", "other"],
                              "Classify ONLY the customer's last message. confirms: a clear yes to the read-back. refuses: no, they do not want the split. "
                              + SIT_DESC + "other: anything else.")],
        on_enter={"type": "tts", "text": "{{split_rb}}"}, max_turns=5, max_turn_target="p1_attempt1_floor")
    pt = mspec["tools"]["promise"]
    okf = api.ok_field(pt)

    def inst(n):
        return {"product_id": "{{s1_pid}}", "amount": "{{split_a%d}}" % n, "date": "{{split_d%d}}" % n, "instalment": n}
    nodes["split_rec1"] = g.api_request("split_rec1", api.pre_action(pt, inst(1), retries=0), "split_rec1b",
                                        transitions=[g.is_true("split_rec2", f"split_rec1_response.data.{okf}", "recorded")])
    nodes["split_rec1b"] = g.api_request("split_rec1b", api.pre_action(pt, inst(1), retries=0), "close_split_err",
                                         transitions=[g.is_true("split_rec2", f"split_rec1b_response.data.{okf}", "recorded on second try")])
    nodes["split_rec2"] = g.api_request("split_rec2", api.pre_action(pt, inst(2), retries=0), "split_rec2b",
                                        transitions=[g.is_true("close_split_ok", f"split_rec2_response.data.{okf}", "recorded")])
    nodes["split_rec2b"] = g.api_request("split_rec2b", api.pre_action(pt, inst(2), retries=0), "close_split_half",
                                         transitions=[g.is_true("close_split_ok", f"split_rec2b_response.data.{okf}", "recorded on second try")])
    pc = mspec["closes"]["promise"]["outcome"]
    nodes["close_split_ok"] = g.close(api, "close_split_ok", pc, "",
        "Both instalments are recorded. You will receive a text message confirming this promise. Thank you for your time, {{title}} {{last_name}}. Goodbye.")
    nodes["close_split_half"] = g.close(api, "close_split_half", pc, "",
        "Your first instalment is recorded, but I could not record the second instalment. You will receive a text message confirming this promise. "
        "Thank you for your time, {{title}} {{last_name}}. Goodbye.")
    e = mspec["closes"]["error"]
    nodes["close_split_err"] = g.close(api, "close_split_err", e["outcome"], e.get("reason", ""),
        "I am sorry, I could not record the promise. Thank you for your time, {{title}} {{last_name}}. Goodbye.")
    return nodes


def wire(nodes):
    """'Too much' before the first offer (enter_1 -> the floor start) goes to the split first (rule 26)."""
    for nm in list(nodes):
        if nm.startswith("enter_1"):
            for tr in nodes[nm].get("transitions", []):
                if tr["target_node"] in ("p1_attempt1_floor", "p1_attempt1_floor_q"):
                    tr["target_node"] = "split_calc"
    # the question-first copy of the floor start is no longer an entry: drop it when nothing points at it
    used = {t["target_node"] for n in nodes.values() for t in n.get("transitions", [])}
    if "p1_attempt1_floor_q" not in used:
        nodes.pop("p1_attempt1_floor_q", None)
