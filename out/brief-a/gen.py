import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.kit import front, graph as g, pycode, openapi
from builder.kit.lint import lint

HERE = pathlib.Path(__file__).parent
api = openapi.Api(str(ROOT / "tools/openapi.json"))
spec = json.load(open(HERE / "front.json"))
nodes = front.build(api, spec, after_verify="fetch_account")

BODY = r'''
def money(x):
    x = float(x)
    if abs(x - round(x)) < 0.001:
        return str(int(round(x)))
    return '%.2f' % x
def find_products():
    p = vars.get('products')
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = None
    if isinstance(p, dict) and isinstance(p.get('products'), list):
        p = p.get('products')
    if isinstance(p, list) and p:
        return p
    found = dict()
    for k in list(vars.keys()):
        m = re.search(r'products[.\[](\d+)\]?\.([a-z_0-9]+)$', str(k))
        if m:
            i = int(m.group(1))
            if i not in found:
                found[i] = dict()
            found[i][m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
try:
    prods = find_products()
    p = prods[0]
    dt = get_now()
    today = dt.date()
    ptype = str(p.get('type') or '')
    past_due = float(p.get('past_due'))
    days_late = int(float(p.get('days_late')))
    if ptype == 'credit_card':
        pname = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = float(p.get('minimum_payment'))
        fname = 'minimum payment'
    elif ptype == 'car_loan':
        pname = 'car loan'
        floor = float(p.get('instalment_amount'))
        fname = 'instalment amount'
    else:
        pname = 'personal loan'
        floor = float(p.get('instalment_amount'))
        fname = 'instalment amount'
    if days_late <= 7:
        band = 'early'
        deadline = nth_biz_after(today, 12)
        attempts = 1
    else:
        band = 'late'
        deadline = nth_biz_after(today, 7)
        attempts = 2
    fri = today + datetime.timedelta(days=4 - today.weekday())
    lb = fri
    while not isbiz(lb):
        lb = lb - ONE
    if lb <= today:
        lb = fri + datetime.timedelta(days=7)
        while not isbiz(lb):
            lb = lb - ONE
    if lb > deadline:
        lb = deadline
    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_name'] = pname
    vars['debt_line'] = ('Thank you, your identity is verified. I am calling from the collections team about a late payment on your ' + pname +
                         '. The past-due amount is ' + money(past_due) + ' and the payment is ' + str(days_late) + ' days late. Can you make this payment today?')
    f = []
    f.append('Today: ' + say(today) + ' (' + today.isoformat() + ').')
    f.append('Product: ' + pname + ' (product_id ' + vars['product_id'] + ').')
    f.append('Full past-due amount: ' + money(past_due) + '. Days late: ' + str(days_late) + '.')
    f.append('Floor (the ' + fname + '): ' + money(floor) + '. The lowest amount you may record.')
    f.append('Band: ' + band + '. DEADLINE (latest date you may record): ' + say(deadline) + ' (' + deadline.isoformat() + ').')
    f.append('Persuasion attempts allowed: ' + str(attempts) + '.')
    plan = ['PERSUASION PLAN (each flat refusal, non-answer or refused offer uses the next step):',
            'Attempt 1: the full past-due amount ' + money(past_due) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + say(lb) + ' (' + lb.isoformat() + ').']
    if attempts == 2:
        plan.append('Attempt 2: the floor ' + money(floor) + ' on the deadline ' + say(deadline) + ' (' + deadline.isoformat() + ').')
    else:
        plan.append('There is NO attempt 2.')
    plan.append('After that: stop. The call ends as refused.')
    f.extend(plan)
    vars['debt_facts'] = '\n'.join(f)
    cal = []
    end = max(deadline + datetime.timedelta(days=4), today + datetime.timedelta(days=21))
    d = today
    while d <= end:
        if d > deadline:
            kind = 'AFTER THE DEADLINE: not allowed, offer the deadline ' + deadline.isoformat()
        elif not isbiz(d):
            nb = nextbiz(d)
            why = 'bank holiday' if d.isoformat() in HOL else 'weekend'
            if nb > deadline:
                kind = why + ': not allowed, offer the deadline ' + deadline.isoformat()
            else:
                kind = why + ': not allowed, offer the next business day ' + say(nb) + ' (' + nb.isoformat() + ')'
        else:
            kind = 'allowed'
        tag = ''
        if d == today:
            tag = ' (today)'
        if d == deadline:
            tag = ' (DEADLINE)'
        cal.append(d.isoformat() + ' ' + say(d) + tag + ': ' + kind)
        d = d + ONE
    monday = today - datetime.timedelta(days=today.weekday())
    wk = []
    for i in range(7):
        t = monday + datetime.timedelta(days=i)
        n = t + datetime.timedelta(days=7)
        wk.append('"this ' + DAYS[i] + '" = ' + t.isoformat() + ('  (in the past)' if t < today else '') + ';  "next ' + DAYS[i] + '" = ' + n.isoformat())
    vars['calendar'] = '\n'.join(cal) + '\n\nWeekday words (today is ' + DAYS[today.weekday()] + '):\n' + '\n'.join(wk)
    vars['debt_state'] = 'ok'
except Exception as e:
    vars['debt_state'] = 'error'
    vars['debt_error'] = str(e)
'''

nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action("get_account", {}, retries=2), "prepare_debt",
                                       mapping=[("data.products", "products")])
nodes["prepare_debt"] = g.code("prepare_debt", pycode.with_params(BODY, spec["calendar"]), "negotiate",
                               [g.unset("close_error", "debt_state", "Code did not run"),
                                g.eq("close_error", "debt_state", "error", "Facts could not be computed")])

# closes
nodes["close_error"] = g.close(api, "close_error", "no_promise", "service_error",
                               "I am sorry, I cannot access your account details right now. Thank you for your time, goodbye.")
nodes["close_promise"] = g.close(api, "close_promise", "promise", "",
                                 "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, goodbye.")
nodes["close_service_error"] = g.close(api, "close_service_error", "no_promise", "service_error",
                                       "I am sorry, I could not record your promise. Thank you for your time, goodbye.")
nodes["close_paid"] = g.close(api, "close_paid", "paid", "",
                              "Thank you. Payments can take one business day to appear on your account. Thank you for your time, goodbye.")
nodes["close_dispute"] = g.close(api, "close_dispute", "no_promise", "dispute",
                                 "I understand, I have noted that. Thank you for your time, goodbye.")
nodes["close_refused"] = g.close(api, "close_refused", "no_promise", "refused", "I understand. Thank you for your time, goodbye.")
nodes["close_hardship"] = g.close(api, "close_hardship", "no_promise", "hardship", "I understand. Thank you for your time, take care, goodbye.")
nodes["close_restructuring"] = g.close(api, "close_restructuring", "transferred", "restructuring", "Thank you, I am transferring you now. Goodbye.")
nodes["close_support"] = g.close(api, "close_support", "transferred", "support", "Thank you, I am transferring you now. Goodbye.")
nodes["close_human_post"] = g.close(api, "close_human_post", "transferred", "human", "Thank you, I am transferring you to a colleague now. Goodbye.")
# deterministic transfers
for q, close in (("restructuring", "close_restructuring"), ("support", "close_support"), ("general", "close_human_post")):
    nodes["xfer_" + q] = g.api_request("xfer_" + q, api.pre_action("transfer_to_agent", {"queue": q}, retries=2), close)

promise_tool = api.tool(
    "create_promise",
    "Record the payment promise. CALL it only after you read back the product, amount and date and the customer gave a clear yes to \"Do you confirm?\". "
    "Use product_id {{product_id}}, the exact agreed amount as a number and the exact date as YYYY-MM-DD from the calendar. Once per product. "
    "If the result has ok false or an error, nothing was recorded: call it once more with the same values.",
    descriptions={"product_id": "The product_id from the facts.", "amount": "Agreed amount, a number.", "date": "Agreed date, YYYY-MM-DD."})

PROMISE_TRS = [g.is_true("close_promise", "create_promise_response.data.ok", "Promise recorded"),
               g.greater("close_service_error", "create_promise_failure_count", 1, "Promise failed twice")]

NEG_KINDS = {
    "proposes": "they propose or accept a date or an amount, or say yes to paying (today or another day), or change the date or amount",
    "confirms": "they say yes to the read-back question \"Do you confirm?\"",
    "refuses": "a flat no to paying, no date and no amount, or they refuse an offer",
    "too_much": "they say the full amount is too much",
    "already_paid": "they say they have ALREADY paid this past-due amount. Saying they WILL pay is NOT this. Talk about a wedding, a busy day or anything else is never this",
    "dispute": "they say this debt is not theirs, they never had this product, or the product was closed or paid off in the past",
    "hardship": "they mention illness, a death in the family, or losing their job",
    "new_plan": "they ask for a new payment plan, restructuring, or lower instalments",
    "human": "they ask to speak to a human or a person",
    "no_talk": "they say they do not want to talk",
    "question": "they ask a question",
    "chat": "anything else, small talk, the weather, their day",
}
neg_desc = "Classify ONLY the customer's last message. " + " ".join(f"{k}: {v}." for k, v in NEG_KINDS.items())

SYSTEM = ("You are Freya Bank's digital assistant on an outbound phone call. Speak English. One or two short sentences per turn. "
          "Address the customer as {{title}} {{last_name}}. Never offer a discount, a waiver, an instalment plan or any term not given to you. "
          "Never invent figures, dates or reasons; if you do not have information, say so. Never compute a date or amount yourself: use the facts and the calendar. "
          "After every tool result, speak or call the next tool. One tool per message. Do not say goodbye yourself; the call is closed for you. "
          "If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant. If asked whether this is a scam, say they can verify the call by phoning Freya Bank's customer service number.")

NEG_TASK = """The customer's identity is verified. You have already stated the debt and asked "Can you make this payment today?".

FACTS (computed, trust them):
{{debt_facts}}

CALENDAR (each date: allowed, or what to offer instead):
{{calendar}}

HOW TO GET A PROMISE
- A valid date is in the calendar marked allowed. A valid amount is from the floor up to the full past-due amount, both included.
- Yes to paying today: amount = full past-due amount, date = today.
- Never ask "how much can you pay?". You propose every amount, starting with the full past-due amount.
- A date or amount the customer proposes is never a refusal. Check it with the calendar:
  - Weekend or holiday: offer what the calendar says.
  - After the deadline: say the latest date you can record is the deadline, and offer it. If they refuse the deadline, that is a flat refusal.
  - Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
  - "next <weekday>" and "this <weekday>": use the weekday words table.
- Full amount too much: offer the floor ONCE and say the rest stays overdue. If they refuse the floor, that is a flat refusal.
- The floor offer ("<floor>, the rest stays overdue") is said at most ONCE in the whole call. After it, never pitch the floor again, except as attempt 2 on the deadline when the plan has one. If the customer answers the floor offer with a date or another amount, do not repeat the offer: check their date or amount and go straight to the read-back.
- An amount from the floor to the full amount: accept it. Below the floor: say it cannot be recorded and offer the floor once; if not accepted, flat refusal.
- Flat refusal, non-answer, or refused offer: use the next step of the PERSUASION PLAN in the facts, exactly as written. Never repeat an offer they already refused.
- If the plan is used up and they still refuse, or they said twice they do not want to talk: say only "I understand." (the call is then closed for you).

CONFIRMING
- When amount and date are agreed, read back the product, the amount and the date (weekday and date in words) and ask "Do you confirm?".
- Only after a clear yes, call create_promise. If they change the amount or date, check it again and read back again.
- If create_promise returns ok false or an error, nothing was recorded: call it once more with the same values. Never say the promise is recorded yourself.
- A recorded promise cannot be changed in this call; they can change it in the mobile app.

OTHER
- Request for a human: ask once "Before I transfer you, is there anything I can help you with myself?".
- Questions you cannot answer from the facts: say you do not have that information."""

def neg_trs(var, hardship_target="hardship"):
    return PROMISE_TRS + [
        g.eq("close_paid", var, "already_paid", "Already paid"),
        g.eq("close_dispute", var, "dispute", "Dispute"),
        g.eq(hardship_target, var, "hardship", "Hardship"),
        g.eq("xfer_restructuring", var, "new_plan", "New plan requested"),
    ]

nodes["negotiate"] = g.conversation(
    "negotiate", NEG_TASK,
    neg_trs("neg_turn") + [
        g.eq("human_check", "neg_turn", "human", "Asked for a human"),
        g.intent("close_refused", "The customer refused the LAST step of the persuasion plan in the facts (all allowed attempts used up), or said for the second time that they do not want to talk"),
    ],
    tools=[promise_tool], extract=[g.enum_field("neg_turn", list(NEG_KINDS), neg_desc)],
    on_enter={"type": "tts", "text": "{{debt_line}}"}, max_turns=30, max_turn_target="close_refused")

nodes["human_check"] = g.conversation(
    "human_check", NEG_TASK,
    neg_trs("hc_turn") + [g.eq("xfer_general", "hc_turn", "human", "Insists on a human")] + [
        g.intent("close_refused", "The customer refused the LAST step of the persuasion plan, or said for the second time that they do not want to talk")],
    tools=[promise_tool], extract=[g.enum_field("hc_turn", list(NEG_KINDS), neg_desc)],
    on_enter={"type": "llm", "prompt": "Ask exactly: \"Before I transfer you, is there anything I can help you with myself?\" No tool call."},
    max_turns=20, max_turn_target="close_refused")

HARD_KINDS = {"accepts": "they accept being connected with the customer support team",
              "declines": "they decline being connected, or say they cannot pay",
              "proposes": "they themselves name a date or an amount for paying, or say yes to a read-back",
              "new_plan": "they ask for a new payment plan or lower instalments",
              "other": "anything else"}
nodes["hardship"] = g.conversation(
    "hardship",
    "The customer mentioned illness, a death in the family or job loss. Make NO persuasion attempt and do not ask for any payment. "
    "You offered to connect them with the customer support team.\n"
    "Only if the customer themself names a date or an amount: check it against the facts and calendar (allowed date, amount from the floor to the full amount), "
    "read back product, amount and date, ask \"Do you confirm?\", and after a clear yes call create_promise (once more if it fails).\n\n"
    "FACTS:\n{{debt_facts}}\n\nCALENDAR:\n{{calendar}}",
    PROMISE_TRS + [g.eq("xfer_support", "hs_turn", "accepts", "Accepts support"),
                   g.eq("close_hardship", "hs_turn", "declines", "Declines support"),
                   g.eq("xfer_restructuring", "hs_turn", "new_plan", "New plan")],
    tools=[promise_tool], extract=[g.enum_field("hs_turn", list(HARD_KINDS), "Classify ONLY the customer's last message. " + " ".join(f"{k}: {v}." for k, v in HARD_KINDS.items()))],
    on_enter={"type": "llm", "prompt": "Say ONE short sentence of sympathy. Then offer to connect them with the customer support team and ask if they would like that. Do not ask for any payment. No tool call."},
    max_turns=12, max_turn_target="close_hardship")

workflow = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {}, "tools": [],
            "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
errs = lint(workflow, api)
if errs:
    print("\n".join(errs)); sys.exit(1)
(HERE / "workflow.json").write_text(json.dumps(workflow, indent=1))
print("wrote", len(nodes), "nodes")
