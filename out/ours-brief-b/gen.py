import json, os, sys
sys.path.insert(0, os.getcwd())
from builder.kit import front, graph as g, pycode
from builder.kit.openapi import Api
from builder.kit.lint import lint

OUT = "out/ours-brief-b"
api = Api("/home/user/build-the-builder/tools/openapi.json")
spec = json.load(open(f"{OUT}/front.json"))
nodes = front.build(api, spec, after_verify="fetch_account")

FACTS_BODY = r'''
try:
    prods = read_list('fetch_account', 'products')
    if not prods:
        raise Exception('no products')
    today = get_now().date()
    wd = today.weekday()
    def last_biz_of_week(d):
        x = d + datetime.timedelta(days=4 - d.weekday())
        while not isbiz(x) and x >= d - datetime.timedelta(days=d.weekday()):
            x = x - ONE
        return x
    lb = last_biz_of_week(today)
    if lb <= today:
        lb = last_biz_of_week(today + datetime.timedelta(days=7 - wd))
    names = []
    stmt = []
    facts = []
    maxdl = today
    for i, p in enumerate(prods):
        t = str(p.get('type') or '')
        if t == 'credit_card':
            nm = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = num(p.get('minimum_payment'))
        elif t == 'car_loan':
            nm = 'car loan'
            floor = num(p.get('instalment_amount'))
        else:
            nm = 'personal loan'
            floor = num(p.get('instalment_amount'))
        due = num(p.get('past_due'))
        dl_ = int(num(p.get('days_late')))
        late = dl_ >= 8
        dl = nth_biz_after(today, 7 if late else 12)
        if dl > maxdl:
            maxdl = dl
        names.append(nm)
        stmt.append('Your ' + nm + ' has a past-due amount of ' + money(due) + ' and is ' + str(dl_) + ' days late.')
        f = ('PRODUCT ' + str(i + 1) + ': ' + nm + ' (product_id ' + str(p.get('product_id')) + '). Past due: ' + money(due) + '. Days late: ' + str(dl_) +
             '. Band: ' + ('late' if late else 'early') + '. Floor (lowest amount allowed): ' + money(floor) +
             '. Deadline (latest promise date): ' + say(dl) + ' (' + dl.isoformat() + '). Persuasion attempts: ' + ('2' if late else '1') + '.\n'
             '  Attempt 1 (after a flat refusal): "Could you pay ' + money(due) + ' on ' + say(lb) + '?" (if the customer already said the full amount is too much, use the floor ' + money(floor) + ' instead of ' + money(due) + ').\n')
        if late:
            f += '  Attempt 2 (after attempt 1 is refused): "Could you pay at least ' + money(floor) + ' on ' + say(dl) + '? The rest would stay overdue."\n'
        else:
            f += '  No attempt 2: after attempt 1 is refused, this product is refused: call add_note with reason refused.\n'
        f += '  Too much: offer the floor ' + money(floor) + ' once and say the rest stays overdue. Amounts accepted: from ' + money(floor) + ' to ' + money(due) + ' included.\n'
        facts.append(f)
    rows = []
    d = today
    end = maxdl + datetime.timedelta(days=21)
    while d <= end:
        if isbiz(d):
            st = 'business day'
        else:
            st = 'NOT a business day (weekend or bank holiday): offer ' + say(nextbiz(d)) + ' (' + nextbiz(d).isoformat() + ') instead'
        rows.append('- ' + d.isoformat() + ' ' + say(d) + ': ' + st)
        d = d + ONE
    monday = today - datetime.timedelta(days=wd)
    wk = []
    for k in range(5):
        thisd = monday + datetime.timedelta(days=k)
        nextd = thisd + datetime.timedelta(days=7)
        wk.append('"this ' + DAYS[k] + '" = ' + say(thisd) + ('(in the past, not allowed)' if thisd < today else '') + '; "next ' + DAYS[k] + '" = ' + say(nextd))
    vars['debt_statement'] = 'Thank you, your identity is verified. I am calling from the collections team about late payments. ' + ' '.join(stmt) + ' Can you pay ' + ('all of them' if len(prods) > 1 else 'this') + ' today?'
    vars['account_facts'] = ('Today is ' + say(today) + ' (' + today.isoformat() + '). Products in order:\n' + '\n'.join(facts) +
                             '\nWEEKDAY WORDS: ' + '; '.join(wk) + '\nDATE TABLE (a promise date must also be on or before that product\'s deadline):\n' + '\n'.join(rows))
    vars['product_count'] = str(len(prods))
    vars['facts_state'] = 'ok'
except Exception as e:
    vars['facts_state'] = 'error'
    vars['facts_error'] = str(e)
'''
cal = spec["calendar"]
nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action("get_account", {}, retries=2), "facts",
                                       mapping=[("data.products", "products")])
nodes["facts"] = g.code("facts", pycode.with_params(FACTS_BODY, cal), "close_error",
                        [g.eq("negotiate", "facts_state", "ok", "facts ready")])

promise_tool = api.tool("create_promise",
    "Record one payment promise. Call ONLY after you read back all promises and the customer said a clear yes. Once per product, one tool per message, "
    "with the product_id from the facts, the exact amount and the ISO date (YYYY-MM-DD), never after that product's deadline (DATE CAP). If ok is not true, nothing was recorded; try that product once more; "
    "if it fails again call add_note for it with reason service_error.",
    descriptions={"product_id": "product_id from the facts", "amount": "agreed amount as a number", "date": "agreed date YYYY-MM-DD"})
note_tool = api.tool("add_note",
    "Note a product that gets no promise, with its product_id and a reason: refused, hardship, dispute, paid or service_error. Once per product. NEVER on a call that is transferred.",
    model_fields=("product_id", "reason", "text"))
transfer_tool = api.tool("transfer_to_agent",
    "Transfer the call. queue restructuring: the customer asks for a new payment plan or lower instalments. queue support: a customer in hardship (illness, death in the family, job loss) accepts the offer to be connected with customer support. "
    "queue general: the customer insists on a human after you asked once whether you can help. Never add notes before or after a transfer.",
    model_fields=("queue",))

TASK = """The customer's identity is verified. You already stated every product and asked whether they can pay all of them today.

FACTS (computed, trust them; never compute a date or an amount yourself):
{{account_facts}}

HOW TO RUN THE CALL:
- If the customer can pay all today: the promise date is today for each product, full past-due amounts.
- If not: go through the products one by one in the order above. Do not ask about today again. For each product, start at attempt 1 only after a flat refusal or non-answer.
- A date or amount the customer proposes is never a refusal. Check it: a date must be today or later, a business day per the DATE TABLE, and not after that product's deadline. Weekend/holiday before the deadline: offer the next business day. After the deadline: say the latest date you can record is the deadline and offer it; refusing it is a flat refusal. Vague period ("next week", "when my salary comes"): ask once for the exact day; if still none, propose the deadline.
- If the customer names one date for everything and it is after one product's deadline, use that product's deadline for that product and say so in the read-back; the others keep the named date.
- Amounts: ask for the full past-due amount first. Never ask "how much can you pay?". An amount from the floor to the full amount is accepted. Below the floor: say it cannot be recorded and offer the floor once. Too much: offer the floor once, say the rest stays overdue.
- Persuasion attempts are per product and are exactly the attempt lines in the facts. A flat refusal uses one attempt. Never repeat an offer already refused. When a product's attempts are used up, call add_note for it with reason refused and move to the next product.
- Already paid (this past-due amount): say payments can take one business day to appear, call add_note with reason paid for that product, continue with the others.
- Not mine / never had it / closed or paid off long ago: do not argue, call add_note with reason dispute for that product, continue with the others.
- Illness, death in the family or job loss: one short sentence of sympathy, no persuasion; offer to connect them with the customer support team. Accept: call transfer_to_agent with queue support. Decline: call add_note with reason hardship for each remaining product without a promise. If they name a date or amount themselves, handle it as a promise.
- New payment plan or lower instalments: do not describe a plan; call transfer_to_agent with queue restructuring (agreed promises not yet recorded are dropped).
- Wants a human: ask once whether you can help first; if they insist, call transfer_to_agent with queue general.
- Says twice they do not want to talk: note every product without a promise with reason refused.
- Never offer a discount, waiver, instalment plan or anything not here. Never invent figures.
- "Is this a scam?": they can verify the call by phoning Freya Bank's customer service number. Robot/AI: you are Freya Bank's digital assistant.
- When every product has an agreed amount and date or is settled otherwise, read ALL agreed promises back together in one message (product, amount, date) and ask "Do you confirm?". If they change something, check it and read back again. After a clear yes, call create_promise once per agreed product, one tool per message.
- Never say a promise is recorded before create_promise returned ok true. If a product's create_promise fails twice, say you could not record it and call add_note with reason service_error for it.
- A recorded promise cannot be changed in this call; they can change it in the mobile app.
- After every tool result, speak or call the next tool. One tool per message. Do not say goodbye yourself: when everything is done, just say you are finishing up."""

kinds_desc = ("Has the whole call finished its business? 'yes' only when create_promise has ALREADY been called and returned ok for every confirmed product, and every other product has an add_note call. A customer saying 'yes, I confirm' is NOT yes: the tools still have to run. "
              "or the customer asked twice not to talk and the notes are done. Otherwise 'no'.")
outcome_desc = ("The close outcome per the bank: 'promise' if at least one create_promise returned ok true. Otherwise: 'paid' if every product was noted paid; "
                "otherwise the reason of the first product (in facts order) whose note is not paid: 'refused', 'hardship', 'dispute' or 'service_error'.")
neg_trs = []
for q, c in (("restructuring", "close_restructuring"), ("support", "close_support"), ("general", "close_human")):
    neg_trs.append(g.and_eq(c, [[("transfer_to_agent_response.data.ok", v), ("transfer_to_agent_args.queue", q)] for v in ("true", "True")], f"transferred {q}"))
for k in ("promise", "paid", "refused", "hardship", "dispute", "service_error"):
    if k == "promise":
        neg_trs.append(g.and_eq("close_promise", [[("call_done", "yes"), ("final_kind", k), ("create_promise_response.data.ok", v)] for v in ("true", "True")], "done: promise recorded"))
    else:
        neg_trs.append(g.and_eq("close_" + k, [[("call_done", "yes"), ("final_kind", k)]], f"done: {k}"))

nodes["negotiate"] = g.conversation(
    "negotiate", TASK, neg_trs, tools=[promise_tool, note_tool, transfer_tool],
    extract=[g.enum_field("call_done", ["no", "yes"], kinds_desc, 0.7),
             g.enum_field("final_kind", ["promise", "paid", "refused", "hardship", "dispute", "service_error"], outcome_desc, 0.6)],
    on_enter={"type": "tts", "text": "{{debt_statement}}"}, max_turns=40, max_turn_target="close_refused")

BYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."
nodes["close_promise"] = g.close(api, "close_promise", "promise", "", "You will receive a text message confirming this promise. " + BYE)
nodes["close_paid"] = g.close(api, "close_paid", "paid", "", "Payments can take one business day to appear. " + BYE)
for r in ("refused", "hardship", "dispute", "service_error"):
    nodes["close_" + r] = g.close(api, "close_" + r, "no_promise", r, BYE)
nodes["close_restructuring"] = g.close(api, "close_restructuring", "transferred", "restructuring", "Thank you, I am transferring you now. Goodbye.")
nodes["close_support"] = g.close(api, "close_support", "transferred", "support", "Thank you, I am transferring you to our customer support team now. Goodbye.")
nodes["close_error"] = g.close(api, "close_error", "no_promise", "service_error", "I am sorry, I cannot access the account details right now. We will contact you again. Thank you, goodbye.")

wf = {"initial_node": "setup",
      "system_prompt": "You are Freya Bank's digital assistant on an outbound phone call. Speak English, short sentences, polite. Address the customer as {{title}} {{last_name}}. "
                       "After every tool result speak or call the next tool. One tool per message. Do not say goodbye yourself. Never invent figures, dates or terms.",
      "nodes": nodes}
errs = lint(wf, api)
json.dump(wf, open(f"{OUT}/workflow.json", "w"), indent=1)
print("lint:", errs or "clean", len(nodes), "nodes")
