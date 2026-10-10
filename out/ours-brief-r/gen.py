import json, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from builder.kit import front, ladder, graph as g, pycode
from builder.kit.openapi import Api

HERE = os.path.dirname(os.path.abspath(__file__))
api = Api(os.path.join(ROOT, "tools", "openapi.json"))
spec = json.load(open(os.path.join(HERE, "front.json")))
lad = json.load(open(os.path.join(HERE, "ladder.json")))

nodes = front.build(api, spec, after_verify="fetch_account")

BYE = " Thank you for your time, goodbye."
nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action("get_account", {}, retries=2), "facts_code",
                                       mapping=[("data.products", "products")])

FACTS = r'''
try:
    prods = read_list('fetch_account', 'products')
    if not prods:
        raise Exception('no products')
    p = prods[0]
    today = get_now().date()
    typ = str(p.get('type') or '')
    if typ == 'credit_card':
        pname = 'credit card ending ' + ' '.join(list(str(p.get('card_last4') or '')))
        floor = num(p.get('minimum_payment'))
        fname = 'minimum payment'
    elif typ == 'car_loan':
        pname = 'car loan'
        floor = num(p.get('instalment_amount'))
        fname = 'instalment amount'
    else:
        pname = 'personal loan'
        floor = num(p.get('instalment_amount'))
        fname = 'instalment amount'
    full = num(p.get('past_due'))
    days = int(num(p.get('days_late')))
    if days <= 10:
        band = 'standard'
        latest = nth_biz_after(today, 10)
    else:
        band = 'priority'
        latest = nth_biz_after(today, 6)
    rem = full - floor
    # attempt 1 date: last business day of the current week, or of next week if today is that day (or later)
    fri = today + datetime.timedelta(days=4 - today.weekday())
    d = fri
    while not isbiz(d) and d > today:
        d = d - ONE
    if d <= today:
        fri2 = fri + datetime.timedelta(days=7)
        d = fri2
        while not isbiz(d):
            d = d - ONE
    if d > latest:
        d = latest
    a1 = d
    vars['band'] = band
    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_say'] = pname
    vars['full_say'] = money(full)
    vars['floor_say'] = money(floor)
    vars['full_iso_amount'] = money(full)
    vars['latest_say'] = say(latest)
    vars['a1_say'] = say(a1)
    vars['debt_line'] = ('Thank you. I am calling from the arrears team about an overdue payment on your ' + pname + '. The overdue amount is ' + money(full)
                         + ' and it is ' + str(days) + ' days overdue. Are you able to pay this amount today?')
    vars['floor_line'] = ('The lowest amount we can record is the ' + fname + ' of ' + money(floor) + '. The remaining ' + money(rem)
                          + ' would stay overdue. Could you pay ' + money(floor) + '?')
    vars['a1_full_line'] = 'Could you pay the full amount of ' + money(full) + ' on ' + say(a1) + '?'
    vars['a1_date_line'] = 'Could you make that payment on ' + say(a1) + '?'
    vars['a2_floor_line'] = ('The latest date I can record is ' + say(latest) + '. Could you pay the ' + fname + ' of ' + money(floor) + ' on ' + say(latest)
                             + '? The remaining ' + money(rem) + ' would stay overdue.')
    vars['a2_date_line'] = 'The latest date I can record is ' + say(latest) + '. Could you make that payment on ' + say(latest) + '?'
    rows = []
    x = today
    end = latest + datetime.timedelta(days=10)
    while x <= end:
        if x > latest:
            r = 'NOT allowed, after the latest date: say the latest date that can be recorded is ' + say(latest) + ' (' + latest.isoformat() + ') and offer it'
        elif not isbiz(x):
            nb = nextbiz(x)
            if nb > latest:
                nb = latest
            r = 'NOT allowed (' + ('bank holiday' if x.isoformat() in HOL else 'weekend') + '): offer ' + say(nb) + ' (' + nb.isoformat() + ') instead'
        else:
            r = 'allowed'
        rows.append('- ' + say(x) + ' (' + x.isoformat() + '): ' + r)
        x = x + ONE
    wk = today - datetime.timedelta(days=today.weekday())
    this_fri = wk + datetime.timedelta(days=4)
    next_fri = this_fri + datetime.timedelta(days=7)
    vars['facts'] = ('Today is ' + say(today) + ' (' + today.isoformat() + '). Tomorrow is ' + say(today + ONE) + '.\n'
                     + 'Product: ' + pname + ' (product_id ' + str(p.get('product_id') or '') + ').\n'
                     + 'Full overdue amount: ' + money(full) + '. Days overdue: ' + str(days) + '.\n'
                     + 'Floor (lowest amount that can be recorded, the ' + fname + '): ' + money(floor) + '. If the floor is paid, ' + money(rem) + ' stays overdue.\n'
                     + 'Latest arrangement date: ' + say(latest) + ' (' + latest.isoformat() + ').\n'
                     + '"This Friday" is ' + say(this_fri) + ' (' + this_fri.isoformat() + '). "Next Friday" is ' + say(next_fri) + ' (' + next_fri.isoformat() + ').\n'
                     + 'For create_promise use product_id ' + str(p.get('product_id') or '') + ', the agreed amount as a number and the date as YYYY-MM-DD.\n'
                     + 'DATE TABLE:\n' + '\n'.join(rows))
    vars['facts_state'] = 'ok'
except Exception as e:
    vars['facts_state'] = 'error'
    vars['facts_error'] = str(e)
'''
src = pycode.with_params(FACTS, spec["calendar"])
nodes["facts_code"] = g.code("facts_code", src, "neg_today", [g.eq("close_error_acct", "facts_state", "error", "Facts failed"),
                                                             g.unset("close_error_acct", "facts_state", "Facts did not run")])

promise = api.tool("create_promise",
                   "Record the payment arrangement. CALL only after the read-back and a clear yes from the customer. Use product_id from the facts, "
                   "the exact agreed amount and the exact ISO date from the date table. Once per call; if the result is not ok, call it once more.",
                   descriptions={"product_id": "product_id from the facts", "amount": "agreed amount as a number", "date": "agreed date as YYYY-MM-DD"})

# closes
def close(name, outcome, reason, farewell):
    nodes[name] = g.close(api, name, outcome, reason, farewell, "end")

close("close_ptp", "promise", "", "Your arrangement is recorded. You will receive a text message confirming this arrangement." + BYE)
close("close_paid", "paid", "", "Thank you for letting me know. Payments can take up to two business days to show." + BYE)
close("close_dispute", "no_promise", "disputed", "I understand, I have noted what you said." + BYE)
close("close_refusal", "no_promise", "refusal", "I understand." + BYE)
close("close_error", "no_promise", "system_error", "I am sorry, the arrangement could not be recorded." + BYE)
close("close_error_acct", "no_promise", "system_error", "I am sorry, I do not have that information available right now." + BYE)
close("close_welfare", "transferred", "welfare", "I am transferring you to our customer welfare team now." + BYE)
close("close_hardship", "no_promise", "financial_difficulty", "I understand. Take care." + BYE)
close("close_restructure", "transferred", "restructure", "I am transferring you to a colleague who can help with that." + BYE)
close("close_agent", "transferred", "agent_request", "I am transferring you to a colleague now." + BYE)

nodes["restructure"] = g.api_request("restructure", api.pre_action("transfer_to_agent", {"queue": "restructuring"}, retries=2), "close_restructure")
nodes["to_agent"] = g.api_request("to_agent", api.pre_action("transfer_to_agent", {"queue": "general"}, retries=2), "close_agent")
nodes["to_welfare"] = g.api_request("to_welfare", api.pre_action("transfer_to_agent", {"queue": "support"}, retries=2), "close_welfare")

common = front.common_answers(spec)
nodes["human_ask"] = g.conversation(
    "human_ask",
    "The customer's identity is verified. They asked for a person.\nFACTS:\n{{facts}}\n" + common +
    "\nDo not call any tool. Do not make a new offer in this step.",
    [g.eq("to_agent", "human_turn", "insists", "Insists on a person"),
     g.eq("neg_again", "human_turn", "accepts_help", "Lets the agent help")],
    extract=[g.enum_field("human_turn", ["insists", "accepts_help", "other"],
                          "Classify ONLY the customer's last message, an answer to whether the assistant can help first. insists: they still want a person, or say no. "
                          "accepts_help: they agree the assistant can help, or go on talking about paying. other: anything else.")],
    on_enter={"type": "tts", "text": spec["human"]["ask_first"]},
    max_turns=4, max_turn_target="to_agent")

nodes["hardship"] = g.conversation(
    "hardship",
    "The customer's identity is verified. They mentioned illness, a bereavement or the loss of a job. No persuasion at all.\nFACTS:\n{{facts}}\n" + common +
    "\nYou offered to connect them with the customer welfare team. If they name a date or an amount themselves, take the arrangement under the date table and the floor: "
    "read back '<product>, <amount>, on <date>. Can you confirm?' and only after a clear yes call create_promise. If its result is not ok, nothing was recorded; never say it was. "
    "Do not say goodbye yourself.",
    [g.is_true("close_ptp", "create_promise_response.data.ok", "Recorded"),
     g.greater("close_error", "create_promise_failure_count", 1, "Recording failed twice"),
     g.eq("to_welfare", "hs_turn", "accepts_transfer", "Accepts welfare transfer"),
     g.eq("close_hardship", "hs_turn", "declines", "Declines")],
    tools=[promise],
    extract=[g.enum_field("hs_turn", ["accepts_transfer", "declines", "proposes", "other"],
                          "Classify ONLY the customer's last message. accepts_transfer: yes to being connected with the welfare team. "
                          "declines: no to the transfer, without naming a date or amount to pay. proposes: they name a date or amount to pay, or confirm a read-back. other: anything else.")],
    on_enter={"type": "llm", "prompt": "Say one sentence of sympathy, then offer to connect them with the customer welfare team. No tool call. Do not mention payment."},
    max_turns=8, max_turn_target="close_hardship")

steps = ladder.build(api, lad, tools=[promise], max_turns=10, turn_limit_target="close_refusal")
errs = ladder.check(lad, list(nodes))
assert not errs, errs
nodes.update(steps)

SYSTEM = ("You are Northwind Bank's automated assistant on an outbound phone call. Speak English, short and polite sentences. "
          "After every tool result, speak or call the next tool. One tool per message. Do not say goodbye yourself; the call is ended for you. "
          "Never invent figures, dates or terms; if you do not have some information, say you do not have that information. "
          "Never say an arrangement is recorded unless create_promise returned ok true. Never compute a date or an amount yourself: use the facts.")
wf = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes,
      "test_variables": {"customer_id": "c_test", "first_name": "Dana", "last_name": "Smith", "title": "Ms", "now": "2026-10-14T11:00"}}
out = os.path.join(HERE, "workflow.json")
json.dump(wf, open(out, "w"), indent=1)
print("wrote", out, len(nodes), "nodes")

# local check of the facts code
v = pycode.run_locally(src, {"now": "2026-10-16T11:00", "fetch_account_response.data.products.0.type": "credit_card",
                             "fetch_account_response.data.products.0.card_last4": "4821", "fetch_account_response.data.products.0.past_due": "420.0",
                             "fetch_account_response.data.products.0.days_late": "16", "fetch_account_response.data.products.0.minimum_payment": "126.0",
                             "fetch_account_response.data.products.0.product_id": "p1"})
print(v.get("facts_state"), v.get("facts_error"))
print(v.get("debt_line")); print(v.get("a1_full_line")); print(v.get("a2_floor_line")); print(v.get("facts")[:900])
