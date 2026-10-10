import json, os, sys
sys.path.insert(0, os.getcwd())
from builder.kit import front, ladder, graph as g, pycode
from builder.kit.openapi import Api
from builder.kit.lint import lint

D = "out/ours-brief-a/"
api = Api("/home/user/build-the-builder/tools/openapi.json")
spec = json.load(open(D + "front.json"))
lad = json.load(open(D + "ladder.json"))
nodes = front.build(api, spec, after_verify="fetch_account")

FACTS = r'''
try:
    def as_obj(x):
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception:
                pass
            try:
                import ast
                return ast.literal_eval(x)
            except Exception:
                return None
        return x
    raw = as_obj(vars.get('products'))
    if not raw:
        for key in ['get_account_response', 'account_data', 'get_account_result', 'response']:
            o = as_obj(vars.get(key))
            if isinstance(o, dict):
                o = o.get('data', o)
                o = as_obj(o)
                if isinstance(o, dict) and o.get('products'):
                    raw = as_obj(o.get('products'))
                    break
    if not raw:
        for k in list(vars.keys()):
            o = as_obj(vars.get(k))
            if isinstance(o, list) and o and isinstance(o[0], dict) and 'past_due' in o[0]:
                raw = o
                break
            if isinstance(o, dict):
                o2 = as_obj(o.get('data', o))
                if isinstance(o2, dict) and o2.get('products'):
                    raw = as_obj(o2.get('products'))
                    break
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = None
    if isinstance(raw, dict):
        raw = raw.get('products') or [raw]
    if not raw:
        flat = dict()
        for k in list(vars.keys()):
            m = re.match(r'^.*products(?:\.|\[)(\d+)\]?\.(\w+)$', str(k))
            if m:
                flat.setdefault(int(m.group(1)), dict())[m.group(2)] = vars[k]
        raw = [flat[i] for i in sorted(flat)]
    p = raw[0]
    def num(x):
        return float(str(x).replace(',', ''))
    def money(x):
        return ('%.2f' % x)
    typ = str(p.get('type'))
    if typ == 'credit_card':
        name = 'credit card ending ' + str(p.get('card_last4'))
        floor = num(p.get('minimum_payment'))
    elif typ == 'car_loan':
        name = 'car loan'
        floor = num(p.get('instalment_amount'))
    else:
        name = 'personal loan'
        floor = num(p.get('instalment_amount'))
    due = num(p.get('past_due'))
    late = int(num(p.get('days_late')))
    now = get_now()
    today = now.date()
    if late <= 7:
        band = 'early'
        deadline = nth_biz_after(today, 12)
    else:
        band = 'late'
        deadline = nth_biz_after(today, 7)
    def lastbiz_of_week(d):
        x = d + datetime.timedelta(days=4 - d.weekday())
        while not isbiz(x):
            x = x - ONE
        return x
    a1 = lastbiz_of_week(today)
    if a1 <= today:
        a1 = lastbiz_of_week(today + datetime.timedelta(days=7 - today.weekday()))
    vars['product_id'] = str(p.get('product_id'))
    vars['product_name'] = name
    vars['band'] = band
    vars['past_due_say'] = money(due)
    vars['floor_say'] = money(floor)
    vars['today_say'] = say(today)
    vars['today_iso'] = today.isoformat()
    vars['deadline_say'] = say(deadline)
    vars['deadline_iso'] = deadline.isoformat()
    vars['attempt1_say'] = say(a1)
    vars['attempt1_iso'] = a1.isoformat()
    vars['debt_line'] = ('Thank you. I am calling from the collections team about a late payment on your ' + name + '. The past-due amount is ' + money(due)
                         + ', and the payment is ' + str(late) + ' days late. Can you make this payment today?')
    vars['floor_line'] = ('I understand. The lowest amount I can record is ' + money(floor) + ', today, ' + say(today) + '. The rest stays overdue. Can you pay ' + money(floor) + ' today?')
    vars['floor_b_line'] = ('I understand. The lowest amount I can record is ' + money(floor) + ', on ' + say(a1) + '. The rest stays overdue. Can you pay ' + money(floor) + ' on ' + say(a1) + '?')
    vars['attempt1_full_line'] = ('I understand. Could you pay the full past-due amount of ' + money(due) + ' on ' + say(a1) + ' instead?')
    vars['attempt1_floor_line'] = ('I understand. Could you pay ' + money(floor) + ' on ' + say(a1) + ' instead? The rest stays overdue.')
    vars['attempt2_line'] = ('I understand. As a last option, could you pay ' + money(floor) + ' on ' + say(deadline) + '? The rest stays overdue.')
    rows = []
    d = today
    end = deadline + datetime.timedelta(days=21)
    while d <= end:
        if d > deadline:
            st = 'NOT allowed: after the deadline. Offer the deadline ' + say(deadline) + ' (' + deadline.isoformat() + ') instead.'
        elif not isbiz(d):
            nb = nextbiz(d)
            if nb > deadline:
                st = 'NOT allowed: not a business day. Offer the deadline ' + say(deadline) + ' (' + deadline.isoformat() + ') instead.'
            else:
                st = 'NOT allowed: weekend or bank holiday. Offer the next business day ' + say(nb) + ' (' + nb.isoformat() + ') instead.'
        else:
            st = 'allowed'
        rows.append('- ' + say(d) + ' (' + d.isoformat() + '): ' + st)
        d = d + ONE
    wk = []
    mon = today - datetime.timedelta(days=today.weekday())
    for i in range(7):
        t = mon + datetime.timedelta(days=i)
        n = t + datetime.timedelta(days=7)
        wk.append('- this ' + DAYS[i] + ' = ' + say(t) + '; next ' + DAYS[i] + ' = ' + say(n))
    vars['facts'] = ('Product: ' + name + ' (product_id ' + str(p.get('product_id')) + '). Past-due amount (full): ' + money(due) + '. Days late: ' + str(late) + '.\n'
                     + 'Floor (lowest amount that can be recorded): ' + money(floor) + '. Any amount from ' + money(floor) + ' to ' + money(due) + ', both included, is accepted.\n'
                     + 'Today: ' + say(today) + ' (' + today.isoformat() + '). Tomorrow: ' + say(today + ONE) + '.\n'
                     + 'Deadline (latest date that can be recorded): ' + say(deadline) + ' (' + deadline.isoformat() + ').\n'
                     + 'DATE TABLE (dates before today are not allowed):\n' + '\n'.join(rows) + '\nAny later date: NOT allowed, offer the deadline.\n'
                     + 'WEEKDAY TABLE:\n' + '\n'.join(wk))
    vars['facts_state'] = 'ok'
except Exception as e:
    vars['facts_state'] = 'error'
    vars['facts_error'] = str(e)
'''
src = pycode.with_params(FACTS, spec["calendar"])
nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action("get_account", {}, retries=2), "facts",
                                       mapping=[("data.products", "products"), ("data", "account_data")])
nodes["facts"] = g.code("facts", src, "neg_ask_today",
                        [g.eq("close_service_error", "facts_state", "error", "facts failed"),
                         g.unset("facts_again", "facts_state", "code did not run")])
nodes["facts_again"] = g.code("facts_again", src, "neg_ask_today",
                              [g.eq("close_service_error", "facts_state", "error", "facts failed"),
                               g.unset("close_service_error", "facts_state", "code did not run")])

BYE = " Thank you for your time, {{title}} {{last_name}}. Goodbye."
nodes["close_promise"] = g.close(api, "close_promise", "promise", "", "Your promise is recorded. You will receive a text message confirming this promise." + BYE)
nodes["close_service_error"] = g.close(api, "close_service_error", "no_promise", "service_error", "I am sorry, I could not record a promise right now." + BYE)
nodes["close_refused"] = g.close(api, "close_refused", "no_promise", "refused", "I understand." + BYE)
nodes["close_paid"] = g.close(api, "close_paid", "paid", "", "Thank you for letting me know. Payments can take one business day to appear." + BYE)
nodes["close_dispute"] = g.close(api, "close_dispute", "no_promise", "dispute", "I understand, I have noted that you do not recognise this debt." + BYE)
nodes["close_hardship"] = g.close(api, "close_hardship", "no_promise", "hardship", "I understand. Please take care." + BYE)
nodes["close_support"] = g.close(api, "close_support", "transferred", "support", "I am connecting you with our customer support team now." + BYE)
nodes["close_restructuring"] = g.close(api, "close_restructuring", "transferred", "restructuring", "I am connecting you with a colleague who can discuss this with you." + BYE)
nodes["close_human_b"] = g.close(api, "close_human_b", "transferred", "human", "I am transferring you to a colleague now." + BYE)
nodes["transfer_restructuring"] = g.api_request("transfer_restructuring", api.pre_action("transfer_to_agent", {"queue": "restructuring"}, retries=2), "close_restructuring")
nodes["transfer_general"] = g.api_request("transfer_general", api.pre_action("transfer_to_agent", {"queue": "general"}, retries=2), "close_human_b")
nodes["transfer_support"] = g.api_request("transfer_support", api.pre_action("transfer_to_agent", {"queue": "support"}, retries=2), "close_support")

promise_tool = api.tool("create_promise",
    "Record the payment promise. CALL only after you read back product, amount and date and the customer said a clear yes to 'Do you confirm?'. "
    "Once per product. Use the exact ISO date and amount from the facts. If the result is not ok true, nothing was recorded; never say it was.",
    descriptions={"product_id": "Use {{product_id}} exactly.", "amount": "The agreed amount as a number.", "date": "The agreed date as YYYY-MM-DD."})

lnodes = ladder.build(api, lad, [promise_tool], prefix="neg_", max_turns=12, turn_limit_target="close_refused")
errs = ladder.check(lad, list(nodes) + ["hardship", "human_check"])
assert not errs, errs
nodes.update(lnodes)

hk = ["accepts_transfer", "declines_transfer", "proposes", "other"]
nodes["hardship"] = g.conversation("hardship",
    "The customer's identity is verified. The customer mentioned illness, a death in the family or job loss. Make NO persuasion attempt and offer no payment.\n"
    "FACTS:\n{{facts}}\n"
    "If the customer themselves names a date or an amount for a payment, check it against the facts (date table, floor to full amount), read back product, amount and date, ask \"Do you confirm?\" and after a clear yes call create_promise. Otherwise do not talk about payment.",
    [g.is_true("close_promise", "create_promise_response.data.ok", "recorded"),
     g.greater("close_service_error", "create_promise_failure_count", 1, "failed twice"),
     g.eq("transfer_support", "hs_turn", "accepts_transfer", "accepts transfer"),
     g.eq("close_hardship", "hs_turn", "declines_transfer", "declines transfer")],
    tools=[promise_tool],
    extract=[g.enum_field("hs_turn", hk, "Classify ONLY the customer's last message. accepts_transfer: yes to being connected with the support team. "
             "declines_transfer: no to being connected, or they want to end the call. proposes: they name a payment date or amount. other: anything else.")],
    on_enter={"type": "llm", "prompt": "Say one short sentence of sympathy. Then ask whether they would like to be connected with our customer support team. Do not mention any payment."},
    max_turns=8, max_turn_target="close_hardship")
nodes["human_check"] = g.conversation("human_check",
    "The customer asked for a human. You asked once whether you can help. If they want help from you, help with their question briefly.",
    [g.eq("transfer_general", "hc_turn", "insists", "insists on human"),
     g.eq("neg_ask_today", "hc_turn", "lets_you_help", "lets you help")],
    extract=[g.enum_field("hc_turn", ["insists", "lets_you_help", "other"], "Classify ONLY the customer's last message. insists: they still want a human. lets_you_help: they accept that you help or go on with the conversation. other: anything else.")],
    on_enter={"type": "tts", "text": spec["human"]["ask_first"]}, max_turns=4, max_turn_target="transfer_general")

SYS = ("You are Freya Bank's digital assistant on an outbound phone call with {{title}} {{last_name}}. Speak English, short sentences, polite. "
       "Address the customer as {{title}} {{last_name}}. After every tool result, speak or call the next tool. One tool per message. "
       "Never say goodbye yourself and never end the call: the system does that. Never invent figures, dates or terms. Never compute a date or amount yourself: use the facts. "
       "Never say anything was recorded or booked unless the tool result said ok true.")
wf = {"initial_node": "setup", "system_prompt": SYS, "nodes": nodes,
      "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
problems = lint(wf, api)
print("lint:", problems)
json.dump(wf, open(D + "workflow.json", "w"), indent=1)
print(len(nodes), "nodes")
