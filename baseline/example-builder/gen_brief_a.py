"""Generates out/brief-a.workflow.json from Brief A. Run: python3 out/gen_brief_a.py"""
import json, pathlib

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
HDR = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, description, body_props, required, post=None, pre=None, retries=0):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body_props)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE + name},
                "method": {"type": "string", "default": "POST"},
                "headers": HDR,
                "body": {"type": "object", "properties": props, "required": required},
            }},
        },
    }
    if post: t["post_process_code"] = post
    if pre: t["pre_process_code"] = pre
    return t


def hook(body):
    """Wrap a post-hook body that works on d = result['data'] and may set d['what_to_do_next']."""
    lines = ["try:",
             "    if isinstance(result, dict):",
             "        result.pop('header', None)",
             "        d = result.get('data')",
             "        if not isinstance(d, dict):",
             "            d = dict()",
             "            result['data'] = d"]
    lines += ["        " + l for l in body.strip("\n").split("\n")]
    lines += ["except Exception:", "    pass", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- tools
VERIFY_POST = hook("""
ok = d.get('ok')
left = d.get('wrong_answers_left')
if d.get('all_verified') is True:
    d['what_to_do_next'] = 'Both answers are correct. The identity is verified.'
elif d.get('hint') == 'day_month_swapped':
    d['what_to_do_next'] = 'Day and month seem swapped. Ask the customer to say the date of birth again with the month as a word, for example 14 March 1988. This is not counted as a wrong answer.'
elif ok is False or ok == 'false':
    d['what_to_do_next'] = 'The answer could not be read. Ask the customer to say it again (a date of birth with the month as a word). It is not counted as a wrong answer.'
elif d.get('verified') is True:
    d['what_to_do_next'] = 'Correct. If that was the date of birth, now ask for the last four digits of the phone number on file.'
elif left is not None and str(left) == '0':
    d['what_to_do_next'] = 'Three wrong answers. The check has failed. Do not say anything about the account.'
else:
    d['what_to_do_next'] = 'That answer is wrong. Do not reveal the correct answer. Say it does not match and ask the same question once more.'
""")

verify_tool = api_tool(
    "verify_identity",
    "Check ONE security answer. CALL it every time the customer gives an answer to a security question, one call per answer. "
    "Before calling, convert a date of birth to YYYY-MM-DD; a date given only as numbers is day, then month, then year. "
    "After the result, always speak to the customer.",
    {
        "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                  "description": "Which question was answered: date_of_birth or phone_last4."},
        "answer": {"type": "string", "default": "{{answer}}",
                   "description": "date_of_birth as YYYY-MM-DD (day-month-year order when said as numbers). phone_last4 as exactly four digits."},
    },
    ["field", "answer"], post=VERIFY_POST)

PROMISE_POST = hook("""
ok = d.get('ok')
if ok is True or ok == 'true':
    d['what_to_do_next'] = 'The promise is recorded.'
else:
    n = 0
    try:
        n = int(vars.get('promise_fail_count') or 0)
    except Exception:
        n = 0
    n = n + 1
    try:
        vars['promise_fail_count'] = n
    except Exception:
        pass
    if n < 2:
        d['what_to_do_next'] = 'Recording FAILED. Nothing was recorded. Do not say it is recorded. Call create_promise again right now, once, with exactly the same values.'
    else:
        d['what_to_do_next'] = 'Recording FAILED again. Nothing was recorded. Tell the customer you could not record the promise.'
""")

promise_tool = api_tool(
    "create_promise",
    "Record the payment promise. CALL it only after you read back product, amount and date and the customer clearly said yes. "
    "If the result says it failed, call it once more with the same values. Never say the promise is recorded unless the result has ok true.",
    {
        "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account."},
        "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount, a number like 420.0"},
        "date": {"type": "string", "default": "{{date}}", "description": "The agreed payment date as YYYY-MM-DD."},
    },
    ["amount", "date"], post=PROMISE_POST)

TRANSFER_POST = hook("""
ok = d.get('ok')
if ok is True or ok == 'true':
    d['what_to_do_next'] = 'The transfer is set up.'
else:
    d['what_to_do_next'] = 'The transfer failed. Tell the customer you could not transfer them right now.'
""")


def transfer_tool(queues, desc):
    return api_tool(
        "transfer_to_agent", desc,
        {"queue": {"type": "string", "enum": queues, "default": "{{queue}}",
                   "description": "Team that takes over. One of: " + ", ".join(queues) + "."}},
        ["queue"], post=TRANSFER_POST)


TRANSFER_DESC_FULL = ("Hand the call to a person. CALL it: with queue restructuring as soon as the customer asks for a new payment plan or lower instalments; "
                      "with queue support when a customer who mentioned illness, a death in the family or job loss accepts to be connected with the support team; "
                      "with queue general when the customer insists on a human after you asked once whether you can help.")
TRANSFER_DESC_GENERAL = "Hand the call to a person. CALL it with queue general only when the customer insists on speaking to a human after you asked once whether you can help."

CALLBACK_POST = hook("""
ok = d.get('ok')
if ok is True or ok == 'true':
    d['what_to_do_next'] = 'The callback is booked.'
else:
    d['what_to_do_next'] = 'The callback could not be booked. Ask for another time inside the window.'
""")

callback_tool = api_tool(
    "schedule_callback",
    "Book a callback. CALL it as soon as the person gives a day and time that is inside the allowed callback window. Never call it for a time outside the window.",
    {
        "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD."},
        "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour."},
    },
    ["date", "time"], post=CALLBACK_POST)

CLOSE_PRE = """try:
    b = config.get('body')
    if isinstance(b, dict):
        if b.get('outcome') in ('promise', 'paid'):
            b.pop('reason', None)
        elif not b.get('reason'):
            b.pop('reason', None)
except Exception:
    pass
"""

close_tool = api_tool(
    "close_call",
    "Record how the call ended, from the conversation.",
    {
        "outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], "default": "{{outcome}}",
                    "description": "promise: a promise was recorded. paid: customer said they already paid. transferred: handed to a person. no_promise: verified, no promise. not_verified: identity not passed. not_reached: the customer was not reached."},
        "reason": {"type": "string", "default": "{{reason}}",
                   "description": "Empty for promise and paid. transferred: restructuring, human, support. no_promise: refused, hardship, dispute, service_error. not_verified: failed, declined. not_reached: callback, no_callback, wrong_number, deceased, unclear."},
    },
    ["outcome"], pre=CLOSE_PRE)
close_tool["config"]["alwaysRunsAt"] = ["end_of_call"]

# ---------------------------------------------------------------- code
COMMON = r"""import datetime
import json
import re
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def isbiz(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def say(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONS[d.month - 1] + ' ' + str(d.year)
def nextbiz(d):
    x = d + ONE
    while not isbiz(x):
        x = x + ONE
    return x
def nth_biz_after(d, n):
    x = d
    for i in range(n):
        x = nextbiz(x)
    return x
def get_now():
    s = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(s[:16])
    except Exception:
        return datetime.datetime.fromisoformat(s[:10] + 'T10:00')
"""

SETUP = COMMON + r"""
try:
    dt = get_now()
    today = dt.date()
    hhmm = dt.strftime('%H:%M')
    nb = nextbiz(today)
    vars['today_iso'] = today.isoformat()
    vars['today_say'] = say(today)
    vars['now_time'] = hhmm
    lines = []
    if hhmm < '19:00':
        start = '10:00' if hhmm < '10:00' else hhmm
        lines.append('- today, ' + say(today) + ' (' + today.isoformat() + '), at a time later than ' + hhmm + ' and no later than 19:00')
    lines.append('- the next business day, ' + say(nb) + ' (' + nb.isoformat() + '), from 10:00 to 19:00, both included')
    vars['callback_facts'] = 'Now is ' + say(today) + ', ' + hhmm + '. A callback can only be booked for:\n' + '\n'.join(lines) + '\nAny other day or time is outside the window. "Tomorrow" means ' + say(today + ONE) + '.'
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['today_iso'] = str(vars.get('now') or '')[:10]
    vars['today_say'] = vars['today_iso']
    vars['now_time'] = ''
    vars['callback_facts'] = 'Callback window: today after the current time or the next business day, 10:00 to 19:00.'
    vars['setup_state'] = 'error ' + str(e)
"""

PREPARE = COMMON + r"""
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
    if isinstance(p, list) and p:
        return p
    a = vars.get('account_json')
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            a = None
    if isinstance(a, dict) and isinstance(a.get('products'), list) and a.get('products'):
        return a.get('products')
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
        fri2 = fri + datetime.timedelta(days=7)
        lb = fri2
        while not isbiz(lb):
            lb = lb - ONE
    vars['product_id'] = str(p.get('product_id') or 'p1')
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
    f.append('Attempt 1 date (last business day of the week): ' + say(lb) + ' (' + lb.isoformat() + ').')
    if attempts == 2:
        f.append('Attempt 2: the floor ' + money(floor) + ' on the deadline ' + say(deadline) + ' (' + deadline.isoformat() + ').')
    else:
        f.append('There is NO attempt 2 in this band.')
    vars['debt_facts'] = '\n'.join(f)
    cal = []
    end = max(deadline + datetime.timedelta(days=4), today + datetime.timedelta(days=21))
    d = today
    while d <= end:
        if d.isoformat() in HOL:
            kind = 'BANK HOLIDAY, not allowed'
        elif d.weekday() >= 5:
            kind = 'weekend, not allowed'
        else:
            kind = 'business day'
        if d > deadline:
            kind = 'AFTER THE DEADLINE, not allowed'
        tag = ''
        if d == today:
            tag = ' (today)'
        if d == deadline:
            tag = ' (DEADLINE)'
        cal.append(d.isoformat() + ' ' + DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONS[d.month - 1] + tag + ': ' + kind)
        d = d + ONE
    monday = today - datetime.timedelta(days=today.weekday())
    wk = []
    for i in range(7):
        t = monday + datetime.timedelta(days=i)
        n = t + datetime.timedelta(days=7)
        wk.append('"this ' + DAYS[i] + '" = ' + t.isoformat() + ('  (in the past)' if t < today else '') + ';  "next ' + DAYS[i] + '" = ' + n.isoformat())
    vars['calendar'] = '\n'.join(cal) + '\n\nWeekday words:\n' + '\n'.join(wk)
    vars['debt_state'] = 'ok'
except Exception as e:
    vars['debt_state'] = 'unknown'
    vars['debt_line'] = ''
    vars['debt_facts'] = ''
    vars['calendar'] = ''
    vars['debt_error'] = str(e)
"""

for c in (SETUP, PREPARE):
    assert "{{" not in c and "}}" not in c


def code_node(name, code, nxt, extra_transitions=()):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": list(extra_transitions) + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}],
    }


# ---------------------------------------------------------------- closing
CLOSES = {
    "close_promise": ("promise", "", "You will receive a text message confirming this promise. Thank you for your time, goodbye."),
    "close_paid": ("paid", "", "Thank you for letting me know. Payments can take one business day to appear, so I will not take a promise today. Thank you for your time, goodbye."),
    "close_restructuring": ("transferred", "restructuring", "I am transferring you now to a colleague who can look at your options. Thank you, goodbye."),
    "close_human": ("transferred", "human", "I am transferring you now to a colleague. Thank you, goodbye."),
    "close_support": ("transferred", "support", "I am transferring you now to our customer support team. Thank you, goodbye."),
    "close_refused": ("no_promise", "refused", "I understand. Thank you for your time, goodbye."),
    "close_hardship": ("no_promise", "hardship", "I understand. Thank you for your time, and take care. Goodbye."),
    "close_dispute": ("no_promise", "dispute", "I understand, thank you for telling me. Thank you for your time, goodbye."),
    "close_service_error": ("no_promise", "service_error", "I am sorry, because of a technical problem I could not record your promise. Thank you for your time, goodbye."),
    "close_failed": ("not_verified", "failed", "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. Thank you, goodbye."),
    "close_declined": ("not_verified", "declined", "I understand. Without the security questions I cannot continue. You can reach us through the Freya Bank mobile app or at a branch. Thank you, goodbye."),
    "close_callback": ("not_reached", "callback", "Thank you, we will call back then. Goodbye."),
    "close_no_callback": ("not_reached", "no_callback", "Thank you for your time. Goodbye."),
    "close_wrong_number": ("not_reached", "wrong_number", "I apologise for the inconvenience. Thank you, goodbye."),
    "close_deceased": ("not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye."),
    "close_unclear": ("not_reached", "unclear", "Thank you for your time. Goodbye."),
}

nodes = {}
for name, (outcome, reason, farewell) in CLOSES.items():
    code = "vars['outcome'] = %r\nvars['reason'] = %r\nvars['farewell'] = %r\n" % (outcome, reason, farewell)
    nodes[name] = code_node(name, code, "end")

nodes["end"] = {
    "name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
    "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call", "parameters": {
        "type": "object", "properties": {"message_mode": {"type": "string", "default": "custom"},
                                         "spoken_message": {"type": "string", "default": "{{farewell}}"}}}}},
}


# ---------------------------------------------------------------- transition helpers
def is_true(var):
    return [{"variable": var, "operator": "equals", "operand": "true"}, {"variable": var, "operator": "equals", "operand": "True"}]


def on_true(target, var, desc):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": is_true(var)}}


def eq(target, var, val, desc):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}}


def intent(target, desc):
    return {"target_node": target, "description": desc, "condition": {"operator": "matches_intent", "description": desc}}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True, "condition": {"operator": "matches_intent", "description": desc}}


def transfer_tr(queue, target):
    return {"target_node": target, "description": "Transfer to " + queue + " done", "condition": {"logic": "or", "conditions": [
        {"logic": "and", "conditions": [{"variable": "transfer_to_agent_response.data.ok", "operator": "equals", "operand": ok},
                                        {"variable": "transfer_to_agent_args.queue", "operator": "equals", "operand": queue}]}
        for ok in ("true", "True")]}}


PROMISE_TRS = [
    on_true("close_promise", "create_promise_response.data.ok", "The promise was recorded"),
    {"target_node": "close_service_error", "description": "Recording the promise failed twice", "condition": {"logic": "or", "conditions": [
        {"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 1},
        {"variable": "promise_fail_count", "operator": "greater_than", "operand": 1}]}},
]
TRANSFER_TRS = [transfer_tr("restructuring", "close_restructuring"), transfer_tr("support", "close_support"), transfer_tr("general", "close_human")]

# ---------------------------------------------------------------- prompts
SYSTEM = """You are the digital assistant of Freya Bank, on an outbound phone call. Speak English. One or two short sentences per turn. Address the customer as {{title}} {{last_name}}.
Rules for the whole call:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If asked something the information you have does not answer: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any other term.
- Never ask the customer how much they can pay. You propose every amount.
- If a rule tells you to use a tool, call the tool. Call at most one tool per message. After every tool result, speak to the customer or call the next tool; never leave a turn empty.
- Never say that something is recorded, booked or transferred unless a tool result says it succeeded.
- Do not say goodbye yourself; the call ends with a closing line spoken by the system."""

PRE_VERIFY = ("Identity is NOT verified yet. Do not say why you are calling. Do not use the words collections, debt, payment, overdue, loan, card or any amount. "
              "If asked what the call is about, say you can explain only after the security check.")

OPENING_EXTRACT = [{
    "name": "who_answered", "type": "string", "min_confidence": 0.6,
    "enum_values": ["customer", "someone_else", "wrong_number", "deceased", "unclear"],
    "description": ("Classify the LAST thing the person on the phone said, in answer to 'Am I speaking with <the customer>?'. "
                    "customer: a clear confirmation: yes, that's me, speaking, or they say the customer's own name as theirs. "
                    "someone_else: they say they are not the customer (a relative, a partner, a colleague), or the customer is not there or not available. "
                    "wrong_number: they say this number does not belong to the customer or they do not know the customer. "
                    "deceased: they say the customer has died. "
                    "unclear: anything else, such as hello, go ahead, who is this, what is this about, or another question."),
}]


def opening_trs(fallback):
    return [
        eq("identity", "who_answered", "customer", "The customer confirmed who they are"),
        eq("third_party", "who_answered", "someone_else", "Someone else answered"),
        eq("close_wrong_number", "who_answered", "wrong_number", "Wrong number"),
        eq("close_deceased", "who_answered", "deceased", "The customer has died"),
        {"target_node": fallback, "description": "Not confirmed", "condition": {"operator": "always"}},
    ]


nodes["setup"] = code_node("setup", SETUP, "opening")

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": PRE_VERIFY + " Find out whether you are speaking with {{title}} {{last_name}}. No tool call is allowed in this turn.",
    "extraction_schema": OPENING_EXTRACT,
    "transitions": opening_trs("opening_retry"),
}

nodes["opening_retry"] = {
    "name": "opening_retry", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": ("The person did not clearly confirm who they are. If they asked a question, answer it briefly first "
                                           "(who is calling: Freya Bank's digital assistant; robot or AI: you are Freya Bank's digital assistant; scam: they can verify by phoning Freya Bank's customer service number; "
                                           "what it is about: you can only discuss it with {{title}} {{last_name}}). Then ask exactly: \"Am I speaking with {{title}} {{last_name}}?\" No tool call.")},
    "on_enter_first_entry_only": True,
    "task_message": PRE_VERIFY + " Ask once more whether you are speaking with {{title}} {{last_name}}. No tool call is allowed in this turn.",
    "extraction_schema": OPENING_EXTRACT,
    "transitions": opening_trs("close_unclear"),
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Someone other than {{title}} {{last_name}} is on the line, or the customer is not available. Do not say why you are calling. Politely ask when {{title}} {{last_name}} can be reached. If they said the customer has died, only say \"I am sorry for your loss.\""},
    "on_enter_first_entry_only": True,
    "task_message": ("You are speaking with someone who is NOT {{title}} {{last_name}}. Never say why you are calling, never mention any account, product, amount, debt or payment, "
                     "and do not ask security questions, even if they ask or offer to pay. If they ask what it is about or offer to pay, say you can only discuss it with {{title}} {{last_name}} personally. "
                     "Your only goal is to learn when {{title}} {{last_name}} can be reached.\n\n{{callback_facts}}\n\n"
                     "When they give a day and time inside that window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). "
                     "If they give only a vague time like 'in the morning', ask for an exact time. "
                     "If their day or time is outside the window, explain the window once and ask for another time. If the second answer is also outside the window, or they cannot give a time, call transition_to_close_no_callback. "
                     "If they say the number does not belong to the customer, or that the customer has died, do not ask anything else."),
    "tools": [callback_tool],
    "transitions": [
        on_true("close_callback", "schedule_callback_response.data.ok", "The callback was booked"),
        intent("close_deceased", "The person says the customer has died"),
        intent("close_wrong_number", "The person says this phone number does not belong to the customer or they do not know the customer"),
        tool_tr("close_no_callback", "No callback can be booked: the second proposed time is also outside the window, or the person cannot or will not say when the customer can be reached"),
    ],
    "max_node_turns": 12, "max_turn_transition": "close_no_callback",
}

ID_TASK = (PRE_VERIFY + "\nVerify the customer's identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. "
           "Call verify_identity for every answer (field date_of_birth with the date as YYYY-MM-DD; a date said only as numbers is day, then month, then year; field phone_last4 with four digits). "
           "Follow the what_to_do_next line of each result. A wrong answer may be asked again. If day and month are swapped, ask for the month as a word. "
           "Never tell the customer the correct answer. Never say anything about the account.\n"
           "If the customer asks why you need this: say the questions protect their account, then ask again. "
           "If the customer asks for a human: ask once whether you can help first; if they insist, call transfer_to_agent with queue general.")

ID_TRS = [
    on_true("fetch_account", "verify_identity_response.data.all_verified", "Both security answers verified"),
    eq("close_failed", "verify_identity_response.data.wrong_answers_left", "0", "Three wrong answers"),
] + [transfer_tr("general", "close_human")]

REFUSE_ID = ("The customer refuses to answer the security question, does not want to talk, or asks what the call is about / why the bank is calling instead of answering. "
             "Giving an answer, even a wrong one, is NOT this. Asking to repeat the question is NOT this.")

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Thank the customer. If they asked a question, answer it briefly without saying why you are calling. Say you need to ask two short security questions, and ask for their date of birth. No tool call yet."},
    "on_enter_first_entry_only": True,
    "task_message": ID_TASK,
    "tools": [verify_tool, transfer_tool(["general"], TRANSFER_DESC_GENERAL)],
    "transitions": ID_TRS + [intent("identity_explain", REFUSE_ID)],
    "max_node_turns": 20, "max_turn_transition": "close_declined",
}

nodes["identity_explain"] = {
    "name": "identity_explain", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Explain once, in one sentence, that these security questions protect their account and that you can only explain the reason for the call after them. Then ask the security question that is still open (date of birth first, then the last four digits of the phone number). No tool call yet."},
    "on_enter_first_entry_only": True,
    "task_message": ID_TASK,
    "tools": [verify_tool, transfer_tool(["general"], TRANSFER_DESC_GENERAL)],
    "transitions": ID_TRS + [intent("close_declined", REFUSE_ID)],
    "max_node_turns": 20, "max_turn_transition": "close_declined",
}

nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare_debt",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
    "pre_actions": [dict(api_tool("get_account", "Get the late products.", {}, [],
                                  post="try:\n    import json\n    if isinstance(result, dict):\n        result.pop('header', None)\n        vars['account_json'] = json.dumps(result.get('data'))\nexcept Exception:\n    pass\n", retries=2))],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [{"target_node": "prepare_debt", "description": "always", "condition": {"operator": "always"}}],
}

nodes["prepare_debt"] = code_node("prepare_debt", PREPARE, "negotiate", [
    eq("close_service_error", "debt_state", "unknown", "The account could not be read")])

NEG_EXTRACT = [
    {"name": "special", "type": "string", "min_confidence": 0.7, "enum_values": ["none", "already_paid", "dispute"],
     "description": ("already_paid: the customer says they have ALREADY paid this past-due amount (e.g. paid it today in the app). Saying they will pay is NOT this. "
                     "dispute: the customer says this debt is not theirs, they never had this product, or the product was closed or paid off in the past. "
                     "none: anything else.")},
    {"name": "hardship", "type": "string", "min_confidence": 0.7, "enum_values": ["no", "yes"],
     "description": "yes only if the customer says they or a family member are ill, someone in their family died, or they lost their job. Otherwise no."},
]

NEG_TASK = """The customer's identity is verified. You have already stated the debt and asked "Can you make this payment today?".

FACTS (computed, trust them):
{{debt_facts}}

CALENDAR (only dates marked business day and not after the deadline are allowed):
{{calendar}}

HOW TO GET A PROMISE
- A valid promise date is today or later, a business day, and not after the deadline. A valid amount is from the floor up to the full past-due amount, both included.
- Yes to paying today: amount = full past-due amount, date = today.
- A date or amount the customer proposes is never a refusal. Check it:
  - Weekend or bank holiday not after the deadline: offer the next business day.
  - After the deadline: say the latest date you can record is the deadline, and offer it. If they refuse the deadline, treat it as a flat refusal.
  - Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
  - "next <weekday>" = that weekday in the following calendar week; "this <weekday>" = the one in the current week. Use the weekday table.
- Amounts: ask for the full past-due amount first. If the customer says the full amount is too much, offer the floor ONCE and say the rest stays overdue. If they refuse the floor, that is a flat refusal. An amount the customer proposes from the floor to the full amount: accept it. Below the floor: say it cannot be recorded and offer the floor once; if not accepted, flat refusal.
- Flat refusal (a no to paying today with no date and no amount, a non-answer, or a refused offer) uses ONE persuasion attempt:
  - Attempt 1: propose the full past-due amount (or the floor if they already said the full amount is too much) on the attempt 1 date.
  - Attempt 2 (only if 2 attempts are allowed): propose the floor on the deadline.
  - When the allowed attempts are used and they still refuse, stop: call transition_to_close_refused. Never repeat an offer they already refused.
- Customer says twice they do not want to talk: call transition_to_close_refused.

CONFIRMING
- When amount and date are agreed, read back the product, the amount and the date (say the weekday and date in words) and ask "Do you confirm?".
- Only after a clear yes, call create_promise with product_id, the amount as a number and the date as YYYY-MM-DD. If they change the amount or date, check it again and read back again.
- If create_promise fails, call it once more with the same values. Never say the promise is recorded yourself.

OTHER
- New payment plan or lower instalments requested: do not describe any plan; say you will transfer them to a colleague and call transfer_to_agent with queue restructuring.
- Request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- Questions you cannot answer from the facts: say you do not have that information."""

nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "{{debt_line}}"},
    "on_enter_first_entry_only": True,
    "task_message": NEG_TASK,
    "extraction_schema": NEG_EXTRACT,
    "tools": [promise_tool, transfer_tool(["restructuring", "general"], TRANSFER_DESC_FULL.replace("with queue support when a customer who mentioned illness, a death in the family or job loss accepts to be connected with the support team; ", ""))],
    "transitions": PROMISE_TRS + TRANSFER_TRS + [
        eq("close_paid", "special", "already_paid", "The customer says they already paid"),
        eq("close_dispute", "special", "dispute", "The customer disputes the debt"),
        eq("hardship", "hardship", "yes", "The customer mentions illness, a death in the family or job loss"),
        tool_tr("close_refused", "All allowed persuasion attempts are used and the customer still refuses, or the customer said twice they do not want to talk"),
    ],
    "max_node_turns": 30, "max_turn_transition": "close_refused",
}

nodes["hardship"] = {
    "name": "hardship", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Say ONE short sentence of sympathy. If they asked for a discount or waiver, say you cannot offer that. Then offer to connect them with the customer support team, and ask if they would like that. Do not ask for any payment. No tool call yet."},
    "on_enter_first_entry_only": True,
    "task_message": ("The customer mentioned illness, a death in the family or job loss. Make NO persuasion attempt and do not ask for any payment. Never offer a discount, waiver or plan.\n"
                     "You offered to connect them with the customer support team. If they accept, call transfer_to_agent with queue support. "
                     "If they ask for a new payment plan or lower instalments, call transfer_to_agent with queue restructuring.\n"
                     "Only if the customer themself names a date or an amount for paying: check it against these facts (date a business day from today to the deadline, amount from the floor to the full amount), read back product, amount and date, ask \"Do you confirm?\", and after a clear yes call create_promise. If it fails, call it once more.\n\n"
                     "FACTS:\n{{debt_facts}}\n\nCALENDAR:\n{{calendar}}"),
    "tools": [transfer_tool(["support", "restructuring", "general"], TRANSFER_DESC_FULL), promise_tool],
    "transitions": PROMISE_TRS + TRANSFER_TRS + [
        intent("close_hardship", "The customer declines to be connected with the support team, or says they cannot pay and wants to end the call"),
    ],
    "max_node_turns": 15, "max_turn_transition": "close_hardship",
}

workflow = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "tools": [close_tool],
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

out = pathlib.Path(__file__).parent / "brief-a.workflow.json"
out.write_text(json.dumps(workflow, indent=1))
print("wrote", out, len(nodes), "nodes")
