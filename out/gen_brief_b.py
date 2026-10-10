"""Generates out/brief-b.workflow.json from Brief A + Brief B (up to three products). Run: python3 out/gen_brief_b.py"""
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


# ---------------------------------------------------------------- per-product tracking (Brief B)
# pstatus: JSON dict product_id -> 'promise' or a note reason. Written by the hooks of create_promise and add_note.
TRACK = """
import json
def _load(k):
    s = vars.get(k)
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except Exception:
            s = None
    if not isinstance(s, dict):
        s = dict()
    return s
st = _load('pstatus')
fails = _load('pfails')
order = [x for x in str(vars.get('pid_order') or '').split(',') if x]
try:
    names = json.loads(vars.get('pnames_json') or '[]')
except Exception:
    names = []
def nm(pid):
    if pid in order and order.index(pid) < len(names):
        return names[order.index(pid)]
    return pid
def wrap_up():
    vars['pstatus'] = json.dumps(st)
    vars['pfails'] = json.dumps(fails)
    rem = [p for p in order if p not in st]
    lines = []
    for p in order:
        if st.get(p) == 'promise':
            lines.append(nm(p) + ' (' + p + '): promise RECORDED')
        elif p in st:
            lines.append(nm(p) + ' (' + p + '): note recorded, reason ' + str(st.get(p)))
        else:
            lines.append(nm(p) + ' (' + p + '): nothing recorded yet')
    vars['progress'] = '\\n'.join(lines)
    if order and not rem:
        vals = [st[p] for p in order]
        if 'promise' in vals:
            out, rsn = 'promise', ''
        elif all(v == 'paid' for v in vals):
            out, rsn = 'paid', ''
        else:
            out, rsn = 'no_promise', [v for v in vals if v != 'paid'][0]
        vars['outcome'] = out
        vars['reason'] = rsn
        vars['all_done'] = 'yes'
        d['all_done'] = 'yes'
    return rem
"""

CAPTURE_PRE = """try:
    b = config.get('body')
    if isinstance(b, dict):
        vars['last_pid'] = str(b.get('product_id') or '')
        vars['last_reason'] = str(b.get('reason') or '')
except Exception:
    pass
"""

PROMISE_POST = hook(TRACK + """
pid = str(vars.get('last_pid') or vars.get('create_promise_args.product_id') or '')
ok = d.get('ok')
if ok is True or ok == 'true':
    st[pid] = 'promise'
    rem = wrap_up()
    if rem:
        d['what_to_do_next'] = 'The promise for ' + nm(pid) + ' is recorded. Still open: ' + ', '.join(nm(p) + ' (' + p + ')' for p in rem) + '. Call create_promise for the next confirmed promise, or add_note for a product without a promise.'
    else:
        d['what_to_do_next'] = 'The promise is recorded. Every product is handled.'
else:
    n = int(fails.get(pid) or 0) + 1
    fails[pid] = n
    wrap_up()
    if n < 2:
        d['what_to_do_next'] = 'Recording FAILED for ' + nm(pid) + '. Nothing was recorded. Do not say it is recorded. Call create_promise again right now, once, with exactly the same values.'
    else:
        d['what_to_do_next'] = 'Recording FAILED again for ' + nm(pid) + '. Nothing was recorded for it. Tell the customer in one sentence that you could not record the promise for ' + nm(pid) + ', and call add_note for ' + pid + ' with reason service_error.'
""")

promise_tool = api_tool(
    "create_promise",
    "Record ONE payment promise for ONE product. CALL it only after you read back all agreed promises and the customer clearly said yes; then call it once per agreed product, one call per message. "
    "If the result says it failed, call it once more with the same values. Never say a promise is recorded unless the result says so.",
    {
        "product_id": {"type": "string", "default": "{{promise_product_id}}", "description": "product_id of the product, copied exactly from the PRODUCTS list (for example p1)."},
        "amount": {"type": "number", "default": "{{promise_amount}}", "description": "The agreed amount for this product, a number like 420.0"},
        "date": {"type": "string", "default": "{{promise_date}}", "description": "The agreed payment date for this product as YYYY-MM-DD."},
    },
    ["product_id", "amount", "date"], post=PROMISE_POST, pre=CAPTURE_PRE)

NOTE_POST = hook(TRACK + """
pid = str(vars.get('last_pid') or vars.get('add_note_args.product_id') or '')
rsn = str(vars.get('last_reason') or vars.get('add_note_args.reason') or 'refused')
ok = d.get('ok')
if ok is True or ok == 'true':
    st[pid] = rsn
    rem = wrap_up()
    if rem:
        d['what_to_do_next'] = 'Note recorded for ' + nm(pid) + '. Still open: ' + ', '.join(nm(p) + ' (' + p + ')' for p in rem) + '. Continue with them.'
    else:
        d['what_to_do_next'] = 'Note recorded. Every product is handled.'
else:
    n = int(fails.get('note_' + pid) or 0) + 1
    fails['note_' + pid] = n
    if n >= 2:
        st[pid] = rsn
    rem = wrap_up()
    d['what_to_do_next'] = 'The note could not be saved. Call add_note once more with the same values.' if n < 2 else 'The note could not be saved. Continue.'
""")

note_tool = api_tool(
    "add_note",
    "Record why ONE product ends the call without a promise. CALL it only at the very end, after every product has been discussed and after all create_promise calls, once for each product without a recorded promise. "
    "NEVER call it when the call is being transferred to a person.",
    {
        "product_id": {"type": "string", "default": "{{note_product_id}}", "description": "product_id of the product, copied exactly from the PRODUCTS list (for example p2)."},
        "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{note_reason}}",
                   "description": "One of: refused, hardship, dispute, paid, service_error."},
    },
    ["product_id", "reason"], post=NOTE_POST, pre=CAPTURE_PRE)

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
    if not prods:
        raise ValueError('no products')
    dt = get_now()
    today = dt.date()
    fri = today + datetime.timedelta(days=4 - today.weekday())
    lb = fri
    while not isbiz(lb):
        lb = lb - ONE
    if lb <= today:
        lb = fri + datetime.timedelta(days=7)
        while not isbiz(lb):
            lb = lb - ONE
    pids = []
    names = []
    facts = []
    says = []
    deadlines = []
    for i, p in enumerate(prods):
        pid = str(p.get('product_id') or ('p' + str(i + 1)))
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
        pids.append(pid)
        names.append(pname)
        deadlines.append((deadline, pname))
        says.append('your ' + pname + ' has a past-due amount of ' + money(past_due) + ' and is ' + str(days_late) + ' days late.')
        f = []
        f.append('PRODUCT ' + str(i + 1) + ': ' + pname + ', product_id ' + pid)
        f.append('  Full past-due amount: ' + money(past_due) + '. Days late: ' + str(days_late) + '.')
        f.append('  Floor (the ' + fname + '): ' + money(floor) + '. The lowest amount you may record for this product.')
        f.append('  Band: ' + band + '. DEADLINE for this product (latest date you may record): ' + say(deadline) + ' (' + deadline.isoformat() + ').')
        f.append('  Persuasion attempts allowed for this product: ' + str(attempts) + '.')
        f.append('  Attempt 1: the full amount ' + money(past_due) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + say(lb) + ' (' + lb.isoformat() + ').')
        if attempts == 2:
            f.append('  Attempt 2: the floor ' + money(floor) + ' on the deadline ' + say(deadline) + ' (' + deadline.isoformat() + '). When attempt 2 is refused, this product is settled as refused: offer nothing more for it.')
        else:
            f.append('  There is NO attempt 2 for this product. When attempt 1 is refused, this product is settled as refused: offer nothing more for it, not even the floor.')
        facts.append('\n'.join(f))
    vars['pid_order'] = ','.join(pids)
    vars['pnames_json'] = json.dumps(names)
    vars['product_count'] = str(len(pids))
    vars['progress'] = '\n'.join(names[i] + ' (' + pids[i] + '): nothing recorded yet' for i in range(len(pids)))
    if len(prods) == 1:
        vars['debt_line'] = ('Thank you, your identity is verified. I am calling from the collections team about a late payment on your ' + names[0] + '. '
                             + 'The past-due amount is ' + money(float(prods[0].get('past_due'))) + ' and the payment is ' + str(int(float(prods[0].get('days_late')))) + ' days late. Can you make this payment today?')
        vars['today_question'] = 'Can you make this payment today?'
    else:
        body = ' '.join(s[0].upper() + s[1:] for s in says)
        vars['debt_line'] = ('Thank you, your identity is verified. I am calling from the collections team about late payments on ' + str(len(prods)) + ' of your products. '
                             + body + ' Can you pay all of them today?')
        vars['today_question'] = 'Can you pay all of them today?'
    vars['debt_facts'] = 'Today: ' + say(today) + ' (' + today.isoformat() + ').\n\n' + '\n\n'.join(facts)
    end = max(d0 for d0, n0 in deadlines) + datetime.timedelta(days=10)
    end = max(end, today + datetime.timedelta(days=21))
    def verdict(d, deadline):
        if d > deadline:
            return 'AFTER ITS DEADLINE: say the latest date you can record for it is ' + say(deadline) + ' and offer that (' + deadline.isoformat() + ')'
        if not isbiz(d):
            nb = nextbiz(d)
            why = 'bank holiday' if d.isoformat() in HOL else 'weekend'
            if nb > deadline:
                return why + ', and the next business day is after its deadline: offer its deadline ' + say(deadline) + ' (' + deadline.isoformat() + ')'
            return why + ', not allowed: offer the next business day ' + say(nb) + ' (' + nb.isoformat() + ')'
        return 'OK, record ' + d.isoformat()
    cal = []
    d = today
    while d <= end:
        head = d.isoformat() + ' ' + DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONS[d.month - 1] + (' (today)' if d == today else '')
        parts = []
        for k in range(len(names)):
            parts.append(names[k] + ': ' + verdict(d, deadlines[k][0]))
        cal.append(head + ' -> ' + ' | '.join(parts))
        d = d + ONE
    later = []
    for k in range(len(names)):
        later.append(names[k] + ': after its deadline, offer ' + say(deadlines[k][0]) + ' (' + deadlines[k][0].isoformat() + ')')
    cal.append('Any date after ' + end.isoformat() + ' -> ' + ' | '.join(later))
    cal.append('Any date before today -> not allowed.')
    monday = today - datetime.timedelta(days=today.weekday())
    wk = []
    for i in range(7):
        t = monday + datetime.timedelta(days=i)
        n = t + datetime.timedelta(days=7)
        wk.append('"this ' + DAYS[i] + '" = ' + t.isoformat() + ('  (in the past)' if t < today else '') + ';  "next ' + DAYS[i] + '" = ' + n.isoformat())
    vars['calendar'] = '\n'.join(cal) + '\n\nWeekday words:\n' + '\n'.join(wk)
    vars['pstatus'] = json.dumps(dict())
    vars['pfails'] = json.dumps(dict())
    vars['debt_state'] = 'ok'
except Exception as e:
    vars['debt_state'] = 'unknown'
    vars['debt_line'] = ''
    vars['debt_facts'] = ''
    vars['calendar'] = ''
    vars['progress'] = ''
    vars['debt_error'] = str(e)
"""

# Recomputes the outcome from the per-product state and picks the farewell.
FINISH = r"""import json
try:
    st = vars.get('pstatus')
    if isinstance(st, str):
        try:
            st = json.loads(st)
        except Exception:
            st = None
    if not isinstance(st, dict):
        st = dict()
    order = [x for x in str(vars.get('pid_order') or '').split(',') if x]
    vals = [st.get(p) for p in order if p in st]
    if 'promise' in vals:
        out, rsn = 'promise', ''
    elif order and len(vals) == len(order) and all(v == 'paid' for v in vals):
        out, rsn = 'paid', ''
    elif vals:
        nonpaid = [v for v in vals if v != 'paid']
        out, rsn = 'no_promise', (nonpaid[0] if nonpaid else 'refused')
    else:
        out, rsn = 'no_promise', 'refused'
    vars['outcome'] = out
    vars['reason'] = rsn
    if out == 'promise':
        fw = 'You will receive a text message confirming this promise. Thank you for your time, goodbye.'
    elif out == 'paid':
        fw = 'Thank you for letting me know. Thank you for your time, goodbye.'
    elif rsn == 'service_error':
        fw = 'I am sorry for the technical problem. Thank you for your time, goodbye.'
    elif rsn == 'hardship':
        fw = 'Thank you for your time, and take care. Goodbye.'
    else:
        fw = 'Thank you for your time, goodbye.'
    vars['farewell'] = fw
except Exception:
    vars['farewell'] = 'Thank you for your time, goodbye.'
"""

for c in (SETUP, PREPARE, FINISH, TRACK):
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



# ---------------------------------------------------------------- closing (fixed outcomes; per-product outcomes go through finish)
CLOSES = {
    "close_restructuring": ("transferred", "restructuring", "I am transferring you now to a colleague who can look at your options. Thank you, goodbye."),
    "close_human": ("transferred", "human", "I am transferring you now to a colleague. Thank you, goodbye."),
    "close_support": ("transferred", "support", "I am transferring you now to our customer support team. Thank you, goodbye."),
    "close_service_error": ("no_promise", "service_error", "I am sorry, because of a technical problem I cannot continue this call. Thank you for your time, goodbye."),
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



ALL_DONE_TR = {"target_node": "finish", "description": "Every product has a recorded promise or a note", "condition": {"logic": "or", "conditions": [
    {"variable": "all_done", "operator": "equals", "operand": "yes"},
    {"variable": "add_note_response.data.all_done", "operator": "equals", "operand": "yes"},
    {"variable": "create_promise_response.data.all_done", "operator": "equals", "operand": "yes"}]}}
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
    {"name": "hardship", "type": "string", "min_confidence": 0.7, "enum_values": ["no", "yes"],
     "description": "yes only if the customer says they or a family member are ill, someone in their family died, or they lost their job. Otherwise no."},
]

RECORDING = """CONFIRMING (once, after EVERY product is settled)
- Read back ALL agreed promises together in one message: for each, the product, the amount and the date in words (weekday and date). If a product gets its own deadline instead of the date the customer named, say so. Then ask "Do you confirm?" once for all of them.
- If they change a date or an amount, check it again against that product's rules and read everything back again.
- If no product has an agreed promise, there is nothing to read back.

RECORDING (only after a clear yes to the read-back, or when no promise was agreed)
- Call create_promise once per agreed product, one call per message, with the product_id from the PRODUCTS list, the amount as a number and the date as YYYY-MM-DD. Follow the what_to_do_next line of each result.
- If one create_promise fails, call it once more with the same values. If it fails again, tell the customer you could not record the promise for that product and call add_note for it with reason service_error. Promises already recorded stay.
- After all create_promise calls, call add_note once for EVERY product that has no recorded promise, with its reason: refused, hardship, dispute, paid or service_error. Never call add_note earlier than this, and never when the call is transferred.
- Never say a promise is recorded yourself before a result says so. Do not say goodbye: the system closes the call when every product is handled."""

NEG_TASK = """The customer's identity is verified. You have already stated every late product and asked "{{today_question}}".

PRODUCTS (computed, trust them; this is the order to use):
{{debt_facts}}

DATE TABLE (computed, trust it). Each line gives a date and, for EACH product, exactly what to do with that date. Deadlines differ between products. Whenever the customer names a date, find that date's line and follow it for each product. Never compare dates yourself:
{{calendar}}

ALREADY RECORDED IN THE BANK SYSTEM:
{{progress}}

HOW TO WORK THROUGH THE PRODUCTS
- If the customer says yes to paying today: the full past-due amount of every product, date today. Go to CONFIRMING.
- Otherwise go through the products one at a time, in the order of the PRODUCTS list. Do not ask about today again. Each product starts at its own attempt 1, and persuasion attempts are counted per product. Settle one product (an agreed amount and date, or a final no) before you move to the next.
- If the customer names one date for everything, apply it to every product, using the DATE TABLE line of that date for each product: a product marked OK keeps the named date; a product marked AFTER ITS DEADLINE gets its own deadline instead (tell the customer). Each product that now has an amount and a date is settled.
- A date the customer names counts for the product(s) it is meant for; do not then propose attempt 1 for that product.
- A date or an amount the customer proposes is never a refusal. Check it:
  - Look the date up in the DATE TABLE and do what its line says for that product (OK, offer the next business day, or offer the product's deadline). If they refuse a deadline offered because their date was too late, treat it as a flat refusal.
  - Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
  - "next <weekday>" = that weekday in the following calendar week; "this <weekday>" = the one in the current week. Use the weekday table.
- Amounts: you always propose the full past-due amount first. Never ask how much they can pay. A plain no is a flat refusal, not "too much". Only if the customer says the full amount is too much, offer that product's floor ONCE and say the rest stays overdue; from then on every offer for that product uses the floor. If they refuse the floor, that is a flat refusal. An amount the customer proposes from the floor up to the full amount: accept it. Below the floor: say it cannot be recorded and offer the floor once; if not accepted, flat refusal.
- Flat refusal (a no with no date and no amount, a non-answer, or a refused offer) uses ONE persuasion attempt of that product. A product gets at most as many offers after the first no as its 'Persuasion attempts allowed', counting every offer you make for it:
  - Attempt 1: as written for the product (full amount, or the floor if they already said the full amount is too much, on the attempt 1 date).
  - Attempt 2, only for a product that allows 2 attempts: the floor on that product's deadline.
  - When the product's attempts are used and they still refuse, the product is settled as "refused". Never repeat an offer they already refused. Move to the next product.
- The customer says they ALREADY paid a product: say payments can take one business day to appear; no promise for it; it is settled as "paid". Continue with the next product.
- The customer says a product is not theirs, they never had it, or it was closed or paid off in the past: do not argue, no promise for it; it is settled as "dispute". Continue with the next product.
- The customer says twice that they do not want to talk: every product without an agreed promise is settled as "refused". Go to CONFIRMING.

""" + RECORDING + """

OTHER
- New payment plan or lower instalments requested: do not describe any plan and record nothing more; say you will transfer them to a colleague and call transfer_to_agent with queue restructuring. No add_note.
- Request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general. No add_note.
- Never offer a discount, a waiver, a plan or any other term. Questions you cannot answer from these facts: say you do not have that information."""

TRANSFER_DESC_NEG = ("Hand the call to a person. CALL it: with queue restructuring as soon as the customer asks for a new payment plan or lower instalments; "
                     "with queue general when the customer insists on a human after you asked once whether you can help. Never call add_note around a transfer.")

nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "{{debt_line}}"},
    "on_enter_first_entry_only": True,
    "task_message": NEG_TASK,
    "extraction_schema": NEG_EXTRACT,
    "tools": [promise_tool, note_tool, transfer_tool(["restructuring", "general"], TRANSFER_DESC_NEG)],
    "transitions": [ALL_DONE_TR] + TRANSFER_TRS + [
        eq("hardship", "hardship", "yes", "The customer mentions illness, a death in the family or job loss"),
    ],
    "max_node_turns": 40, "max_turn_transition": "finish",
}

nodes["hardship"] = {
    "name": "hardship", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Say ONE short sentence of sympathy. If they asked for a discount or waiver, say you cannot offer that. Then offer to connect them with the customer support team and ask if they would like that. Do not ask for any payment. No tool call yet."},
    "on_enter_first_entry_only": True,
    "task_message": ("The customer mentioned illness, a death in the family or job loss. Make NO persuasion attempt on any product and do not ask for any payment. Never offer a discount, waiver or plan.\n"
                     "You offered to connect them with the customer support team. If they accept, call transfer_to_agent with queue support (no add_note, nothing more recorded). "
                     "If they ask for a new payment plan or lower instalments, call transfer_to_agent with queue restructuring (no add_note).\n"
                     "If they decline the support team: promises the customer already agreed earlier in this call, or a date or amount the customer names themself now (checked against that product's rules), go through CONFIRMING and RECORDING below. "
                     "Every other product without a promise gets add_note with reason hardship, except products already settled as paid or dispute, which keep that reason.\n\n"
                     + RECORDING + "\n\nPRODUCTS:\n{{debt_facts}}\n\nDATE TABLE (for each date, what to do per product; never compare dates yourself):\n{{calendar}}\n\nALREADY RECORDED IN THE BANK SYSTEM:\n{{progress}}"),
    "tools": [transfer_tool(["support", "restructuring", "general"], TRANSFER_DESC_FULL + " Never call add_note around a transfer."), promise_tool, note_tool],
    "transitions": [ALL_DONE_TR] + TRANSFER_TRS,
    "max_node_turns": 20, "max_turn_transition": "finish",
}

nodes["finish"] = code_node("finish", FINISH, "end")

workflow = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "tools": [close_tool],
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

out = pathlib.Path(__file__).parent / "brief-b.workflow.json"
out.write_text(json.dumps(workflow, indent=1))
print("wrote", out, len(nodes), "nodes")
