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
the date was moved to the deadline), mov_<k> ('1' when a weekend day or holiday was moved to the next business day),
reason_<k>, rec_ok_<k>. Shared: cur_slot, carry_date, floor_first, fix_count.

Dates the customer says are extracted as text and resolved in code against `today` (the call's `now`), never by the
platform's `date` extraction: that one resolves "today" and "tomorrow" against the real clock (PUB-01, PUB-12).
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
               "adjusted": " (the latest date I can record for it)", "moved": " (the day you named is not a business day, ...)", "sep": "; ",
               "ask": " Do you confirm?"},
  "next_weekday": "following_week" | "nearest",     optional: what "next Friday" means in the brief (default following_week)
  "max_fixes": 3,        optional: changes to the read-back before the call ends without a promise
  "hardship": {"say": "...", "task": "..."},          optional, defaults below
  "human": {"ask_first": "..."},
  "reasons": {"refused": "<note reason>", "hardship": "...", "dispute": "...", "paid": "...", "service_error": "..."},
  "close_reasons": {"refused": "<close code>", ...},   optional: when the brief's close codes are not the note values, the close
                         code for each logical reason; the notes keep "reasons" (values of the note tool's enum)
  "queues": {"new_plan": "<queue value>", "hardship": "...", "human": "..."},
  "closes": {"promise": {"outcome": "...", "farewell": "..."}, "paid": {"outcome": "...", "farewell": "..."},
             "other": {"outcome": "...", "farewell": "..."},    the reason comes from the notes (first one that is not "paid")
             "new_plan": {"outcome": "...", "reason": "...", "farewell": "..."}, "hardship": {...}, "human": {...},
             "error": {"outcome": "...", "reason": "...", "farewell": "..."}},
  "situations": {"paid": "sentence spoken when the customer says a product is paid", "dispute": "..."},   optional
  "notes": true,         optional. false when the brief takes no notes (a product without a promise is only closed on)
  "tools": {"promise": "create_promise", "note": "add_note", "transfer": "transfer_to_agent"}   optional, names in the tool API file
  "fields": {"product": "product_id", "amount": "amount", "date": "date", "reason": "reason", "queue": "queue"}   optional, their request fields
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

# The customer's date, in their words, turned into a date here and not by the platform's extraction: a `date`
# extraction resolves "today" and "tomorrow" against the real clock, not against the call's `now` (PUB-01, PUB-12).
# Vague periods ("next week", "end of the month") give None: the ladder step asks for the exact day.
_WHEN = r'''
WDS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MON_RE = '(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*'
UNITS = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
ORDS = 'zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth'.split()
TENS = dict(twenty=20, thirty=30)
TENTHS = dict(twentieth=20, thirtieth=30)
def day_today():
    try:
        return datetime.date.fromisoformat(str(vars.get('today') or '')[:10])
    except Exception:
        return get_now().date()
def bizday(d):
    hol = [x for x in str(vars.get('holiday_list') or '').split(',') if x]
    wk = [int(x) for x in str(vars.get('weekend_list') or '5,6').split(',') if x.strip().isdigit()]
    return d.weekday() not in wk and d.isoformat() not in hol
def words_to_digits(t):
    toks = t.split()
    out = []
    i = 0
    while i < len(toks):
        w = toks[i]
        nx = toks[i + 1] if i + 1 < len(toks) else ''
        if w in TENS and nx in ORDS[1:10]:
            out.append(str(TENS[w] + ORDS.index(nx)) + 'th')
            i = i + 2
            continue
        if w in TENS and nx in UNITS[1:10]:
            out.append(str(TENS[w] + UNITS.index(nx)))
            i = i + 2
            continue
        if w in TENS:
            out.append(str(TENS[w]))
        elif w in TENTHS:
            out.append(str(TENTHS[w]) + 'th')
        elif w in ORDS[1:]:
            out.append(str(ORDS.index(w)) + 'th')
        elif w in UNITS[1:]:
            out.append(str(UNITS.index(w)))
        else:
            out.append(w)
        i = i + 1
    return ' '.join(out)
def make_day(y, m, d):
    try:
        return datetime.date(y, m, d)
    except Exception:
        return None
def ahead(m, d, y, today):
    x = make_day(y if y else today.year, m, d)
    if x is not None and not y and x < today:
        x = make_day(today.year + 1, m, d)
    return x
def resolve_when(raw):
    t = str(raw or '').strip().lower()
    if t == '':
        return None
    # "the 15th, sorry, I mean the 16th": the part after the last correction wins when it holds a date
    parts = re.split(r'\b(?:sorry|i mean|i meant|actually|correction|rather|no wait)\b', t)
    if len(parts) > 1 and parts[-1].strip() != '':
        last = resolve_one(parts[-1])
        if last is not None:
            return last
    return resolve_one(t)
def resolve_one(t):
    today = day_today()
    mo = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
    if mo:
        return make_day(int(mo.group(1)), int(mo.group(2)), int(mo.group(3)))
    t = ' ' + words_to_digits(re.sub(r'[^a-z0-9/. ]', ' ', t.replace('-', ' '))) + ' '
    mo = re.search(r' (\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))? ', t)
    if mo:
        y = int(mo.group(3)) if mo.group(3) else 0
        if 0 < y < 100:
            y = 2000 + y
        return ahead(int(mo.group(2)), int(mo.group(1)), y, today)
    mo = re.search(r' (\d{1,2})(?:st|nd|rd|th)?(?: of)? ' + MON_RE + r'(?: (\d{4}))? ', t)
    if mo:
        return ahead(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(mo.group(2)) + 1, int(mo.group(1)), int(mo.group(3) or 0), today)
    mo = re.search(' ' + MON_RE + r' (?:the )?(\d{1,2})(?:st|nd|rd|th)?(?: (\d{4}))? ', t)
    if mo:
        return ahead(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(mo.group(1)) + 1, int(mo.group(2)), int(mo.group(3) or 0), today)
    if ' day after tomorrow ' in t:
        return today + datetime.timedelta(days=2)
    if ' tomorrow ' in t:
        return today + datetime.timedelta(days=1)
    if ' today ' in t or ' tonight ' in t:
        return today
    mo = re.search(r' (?:the |on )?(\d{1,2})(?:st|nd|rd|th) ', t)      # before weekday names: 'Monday the 26th' is the 26th
    if mo:
        n = int(mo.group(1))
        x = make_day(today.year, today.month, n)
        if x is None or x < today:
            y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
            x = make_day(y, m, n)
        return x
    mo = re.search(r' in (\d{1,2}) days? ', t)
    if mo:
        return today + datetime.timedelta(days=int(mo.group(1)))
    mo = re.search(r' (next |this |coming )?(' + '|'.join(WDS) + ') ', t)
    if mo:
        wd = WDS.index(mo.group(2))
        mon = today - datetime.timedelta(days=today.weekday())
        q = (mo.group(1) or '').strip()
        if ' week after next ' in t:             # "the week after next", then "Monday"
            return mon + datetime.timedelta(days=14 + wd)
        if ' next week ' in t and q == '':
            return mon + datetime.timedelta(days=7 + wd)
        if q == 'next' and P.get('next_weekday', 'following_week') == 'following_week':
            return mon + datetime.timedelta(days=7 + wd)
        if q == 'this':
            x = mon + datetime.timedelta(days=wd)
            return x if x >= today else None
        x = today + datetime.timedelta(days=(wd - today.weekday()) % 7)
        if q in ('next', 'coming') and x == today:
            x = x + datetime.timedelta(days=7)
        return x
    return None
def settle(k, d):
    # The date for product k: a past date is no date; a weekend day or a bank holiday moves to the next business day
    # (mov_k = 1); a date after the product's deadline moves to the deadline (adj_k = 1). Returns the ISO date or ''.
    today = day_today()
    if d is None or d < today:
        return ''
    mov = ''
    while not bizday(d):
        d = d + datetime.timedelta(days=1)
        mov = '1'
    s = d.isoformat()
    dl = str(vars.get('s%d_deadline' % k) or '')
    adj = ''
    if dl != '' and s > dl:
        s = dl
        adj = '1'
        mov = ''
    vars['date_%d' % k] = s
    vars['adj_%d' % k] = adj
    vars['mov_%d' % k] = mov
    return s
'''

_ENTER = r'''
try:
    k = P['k']
    n = int(num(vars.get('product_count')))
    vars['cur_slot'] = str(k)
    cd = str(vars.get('carry_date') or '')
    pw = str(vars.get('m_today_when_%d' % k) or '')
    pa = num(vars.get('m_today_amount_%d' % k), 0.0)
    vars['m_today_when_%d' % k] = ''
    vars['m_today_amount_%d' % k] = 0
    due = num(vars.get('s%d_due' % k), 0.0)
    if pa <= 0 or pa > due:
        pa = due
    if k > n:
        vars[P['rv']] = 'done'
    elif pw != '' and pa >= num(vars.get('s%d_floor' % k), 0.0) and settle(k, resolve_when(pw)) != '':
        vars['st_%d' % k] = 'agreed'                 # named for this product in the first answer ("the card tomorrow")
        vars['amt_%d' % k] = money(pa)
        vars[P['rv']] = 'auto'
    elif cd != '' and settle(k, resolve_when(cd)) != '':
        vars['st_%d' % k] = 'agreed'
        vars['amt_%d' % k] = money(vars.get('s%d_due' % k))
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
class Back(Exception):
    pass
try:
    k = P['k']
    said = resolve_when(vars.get('agreed_date'))
    if P.get('require_date') and (said is None or said < day_today()):
        raise Back()                         # a proposal without a day: back to the step, the model asks for it
    d = settle(k, said)
    if d == '' and P['offer_date_var'] != '':
        d = settle(k, resolve_when(vars.get(P['offer_date_var'])))
    if d == '':
        d = settle(k, resolve_when(vars.get('s%d_deadline' % k)))
        vars['adj_%d' % k] = '1'
    a = num(vars.get('agreed_amount'), 0.0)
    if a <= 0 and P['offer_amount_var'] != '':
        a = num(vars.get(P['offer_amount_var']), 0.0)
    due = num(vars.get('s%d_due' % k))
    if a <= 0 or a > due:
        a = due
    fl = num(vars.get('s%d_floor' % k), 0.0)
    if a < fl:                               # below the floor cannot be recorded: the offer on the table, else the floor
        oa = num(vars.get(P['offer_amount_var']), 0.0) if P['offer_amount_var'] != '' else 0.0
        a = oa if fl <= oa <= due else fl    # ("six hundred and thirty seven" to an offer of 637.50; a stray "3")
    vars['st_%d' % k] = 'agreed'
    vars['amt_%d' % k] = money(a)
    if str(vars.get(P['all_var']) or '') == 'yes':
        vars['carry_date'] = said.isoformat() if said is not None else d
    vars['agreed_date'] = ''
    vars['agreed_amount'] = 0          # a float variable: the platform ignores '' (stale 220 on the next product, PUB-11)
    vars[P['rv']] = 'ok'
except Back:
    vars[P['rv']] = 'back'
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
    said = str(vars.get('agreed_date') or '')
    if said == '':                           # "the thirtieth" landed in m_today_when_1 only (PUB-13 pieces)
        for k in range(1, n + 1):
            w = str(vars.get('m_today_when_%d' % k) or '')
            if w != '':
                said = w
                break
    vt = str(vars.get('vague_text') or '')
    d0 = resolve_when((vt + ' ' + said) if vt != '' else said)
    if d0 is None and str(vars.get(P['turn_var']) or '') == 'accepts':
        d0 = day_today()                     # yes to "can you pay all of this today?"
    vars['agreed_date'] = ''
    vars['agreed_amount'] = 0          # a float variable: the platform ignores '' (stale 220 on the next product, PUB-11)
    proposed = str(vars.get(P['turn_var']) or '') == 'proposes'
    if (d0 is None or d0 < day_today()) and proposed:
        vc = int(num(vars.get('vague_count'), 0.0)) + 1
        vars['vague_count'] = str(vc)
        if vc <= 1:
            vars['vague_text'] = said
            vars[P['rv']] = 'ask'                # back to the first step: the model asks once for the exact day
        else:
            # still no day read: the product ladders make their offers. Agreeing every product on its deadline here
            # recorded deadlines when only the extraction had missed a day the customer said (PUB-07, PUB-11)
            vars[P['rv']] = 'unclear'
    elif d0 is None or d0 < day_today():
        vars[P['rv']] = 'unclear'            # no day yet: the product ladders ask
    else:
        for k in range(1, n + 1):
            settle(k, d0)
            vars['st_%d' % k] = 'agreed'
            vars['amt_%d' % k] = money(vars.get('s%d_due' % k))
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
        elif str(vars.get('mov_%d' % k) or '') == '1':
            item = item + R.get('moved', ' (the day you named is not a business day, so this is the next business day)')
        parts.append(item)
    rc = int(num(vars.get('rb_count'), 0.0)) + 1
    vars['rb_count'] = str(rc)
    if parts and rc > P['max_readbacks']:    # read back again and again without a yes: no promise, notes, close
        for k in range(1, n + 1):
            if str(vars.get('st_%d' % k) or '') == 'agreed':
                vars['st_%d' % k] = 'noted'
                vars['reason_%d' % k] = P['refused_reason']
        parts = []
    q = str(vars.get('asked_q') or '')
    vars['asked_q'] = ''
    if parts:
        vars['readback'] = R['intro'] + R['sep'].join(parts) + '.' + R['ask']
        vars[P['rv']] = 'readback_q' if q == 'yes' else 'readback'
    else:
        vars['readback'] = ''
        vars[P['rv']] = 'record'
except Exception:
    vars[P['rv']] = 'error'
'''

_APPLY_FIX = r'''
try:
    n = int(num(vars.get('product_count')))
    fc = int(num(vars.get('fix_count'), 0.0)) + 1
    vars['fix_count'] = str(fc)
    kind = str(vars.get('fix_kind') or '')
    slot = str(vars.get('fix_slot') or '')
    targets = list(range(1, n + 1)) if slot == 'all' else [int(slot)] if slot.isdigit() else []
    agreed = [k for k in range(1, n + 1) if str(vars.get('st_%d' % k) or '') == 'agreed']
    if not targets and len(agreed) == 1:
        targets = agreed                     # one product read back: the change is for it
    for k in targets:
        if k < 1 or k > n or str(vars.get('st_%d' % k) or '') != 'agreed':
            continue
        if kind == 'drop':
            vars['st_%d' % k] = 'noted'
            vars['reason_%d' % k] = P['reasons']['refused']
            continue
        due = num(vars.get('s%d_due' % k))
        settle(k, resolve_when(vars.get('fix_date')))
        fa = num(vars.get('fix_amount'), 0.0)
        if fa >= num(vars.get('s%d_floor' % k), 0.0) and fa > 0 and fa <= due:
            vars['amt_%d' % k] = money(fa)
    vars['fix_kind'] = ''
    vars['fix_slot'] = ''
    vars['fix_date'] = ''
    vars['fix_amount'] = 0
    vars[P['rv']] = 'stuck' if fc > P['max_fixes'] else 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_STUCK = r'''
try:
    n = int(num(vars.get('product_count')))
    for k in range(1, n + 1):
        if str(vars.get('st_%d' % k) or '') == 'agreed':
            vars['st_%d' % k] = 'noted'
            vars['reason_%d' % k] = P['reasons']['refused']
    vars[P['rv']] = 'ok'
except Exception:
    vars[P['rv']] = 'error'
'''

_GATE = r'''
k = P['k']
st = str(vars.get('st_%d' % k) or '')
if st == 'agreed':
    vars[P['rv']] = 'promise'
elif st == 'noted' and P['notes'] and str(vars.get('reason_%d' % k) or '') != '':
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
        r0 = others[0] if others else R['refused']
        vars['final_reason'] = P['close_reason_of'].get(r0, r0)      # the brief's close code when it differs from the note value
        vars[P['rv']] = 'other'
except Exception:
    vars[P['rv']] = 'error'
'''


_ASKED_Q = g.enum_field("asked_q", ["yes", "no"],
                        "yes if the customer's last message asks you a question (are you a robot, is this a scam, why, which account), "
                        "with or without an answer in the same message. Otherwise no.", 0.5)


def _eqs(var, mapping):
    return [g.eq(target, var, val, f"{var} is {val}") for val, target in mapping]


def build(api, spec, ladder_tpl=None):
    """Return {node_name: node}. `spec` as in the module docstring; `ladder_tpl` defaults to spec["ladder"]."""
    K = int(spec["slots"])
    tpl = copy.deepcopy(ladder_tpl or spec["ladder"])
    tools = {"promise": "create_promise", "note": "add_note", "transfer": "transfer_to_agent", **(spec.get("tools") or {})}
    # request fields of those tools, by what they mean (names as in the tool API file)
    F = {"product": "product_id", "amount": "amount", "date": "date", "reason": "reason", "queue": "queue", **(spec.get("fields") or {})}
    closes = spec["closes"]
    reasons = dict(spec["reasons"])      # logical reason -> the value the bank's note tool takes
    # a brief whose close codes are not the note values (the note tool's enum says refused, the close table says declined):
    # logical reason -> close code. The notes keep the note values; only close_call gets these.
    close_reason_of = {reasons[k]: v for k, v in (spec.get("close_reasons") or {}).items() if k in reasons}
    outcomes = {"promise": closes["promise"]["outcome"], "paid": closes["paid"]["outcome"], "other": closes["other"]["outcome"]}
    queues = spec["queues"]              # logical situation -> queue value
    nodes = {}
    nw = spec.get("next_weekday", "following_week")    # "next Friday": "following_week" (the Friday of next week) or "nearest"
    base_rules = list(spec.get("today", {}).get("rules") or [])

    # --- "can you pay all of them today?"
    t = spec["today"]
    today_spec = {"rules": base_rules, "facts": t.get("facts", ""), "record": "defer", "on_agreed": "all_yes",
                  "situations": {"paid": "enter_1", "dispute": "enter_1", "hardship": "hardship",
                                 "new_plan": "transfer_new_plan", "human": "human_check"},
                  "start": "today",
                  "steps": {"today": {"say": t["say"], "task": t["task"],
                                      "on": {"refuses": "enter_1", "too_much": "floor_mark"}}}}
    nodes.update(ladder.build(api, today_spec, [], prefix="m_", max_turns=16, turn_limit_target="enter_1"))
    # "yes" and "all of it on the 30th" agree every product at once; anything about only some products goes to the
    # product ladders at once, so the model never bargains for one product in this step (PUB-12, PUB-13)
    mt = nodes["m_today"]
    mt["extraction_schema"].append(g.enum_field("m_today_scope", ["all", "some", "unclear"],
        "Which products the customer's last message is about. all: every product that was read out, or no product is "
        "singled out (a plain 'yes', 'I can pay it all', 'both on the 30th', 'everything on Friday'). some: they name "
        "only some products, or treat the products differently ('the card tomorrow, not the loans'). unclear: they do "
        "not talk about paying.", 0.6))
    turn = "m_today_turn"
    mt["extraction_schema"].append(_ASKED_Q)
    agreed = [i for i, tr in enumerate(mt["transitions"]) if tr["target_node"] == "all_yes"][0]
    mt["transitions"][agreed:agreed + 1] = [
        g.and_eq("all_yes", [[(turn, kd), (sc, sv)] for kd in ("accepts", "proposes") for sc, sv in (("m_today_scope", "all"), ("product_count", "1"))],
                 "agrees or proposes for every product"),
        g.any_eq("enter_1", turn, ["accepts", "proposes"], "talks about some products: one product at a time")]
    if K > 1:      # a date (and amount) the first answer gives for one product; enter_<k> agrees that product on it
        for k in range(1, K + 1):
            nth = ["first", "second", "third", "fourth", "fifth"][k - 1] if k <= 5 else f"number {k}"
            mt["extraction_schema"] += [
                {"name": f"m_today_when_{k}", "type": "string", "min_confidence": 0.3, "description":
                 f"The payment date the customer named for the {nth} product read out in the statement, in their own words "
                 "(for example 'tomorrow', 'Friday', 'the 30th'). Empty if they named no date for that product, or if their "
                 "date is for every product. When they correct themselves, give the corrected day."},
                {"name": f"m_today_amount_{k}", "type": "float", "min_confidence": 0.4, "description":
                 f"The amount the customer said they will pay for the {nth} product read out, if they named one for it."}]
    nodes["all_yes"] = _code("all_yes", _WHEN + _ALL_YES, "close_error",
                             _eqs("all_route", [("ok", "finish"), ("unclear", "enter_1"), ("ask", "m_today")]),
                             turn_var=turn, next_weekday=nw)
    nodes["floor_mark"] = _code("floor_mark", _FLOOR_MARK, "close_error", _eqs("floor_route", [("ok", "enter_1")]))

    # --- one ladder per product
    start, start_floor = tpl["start"], tpl.get("start_floor") or tpl["start"]
    for k in range(1, K + 1):
        lk = _sub(tpl, k)
        lk["record"] = "defer"
        lk["on_agreed"] = f"save_{k}"
        steps = lk["steps"]
        built = ladder.build(api, {kk: vv for kk, vv in lk.items() if kk != "start_floor"}, [], prefix=f"p{k}_", max_turns=18,
                             turn_limit_target=f"refused_{k}")
        for step, s in steps.items():
            node = built[f"p{k}_{step}"]
            node["extraction_schema"].append(_ASKED_Q)
            allvar = f"p{k}_{step}_all"
            node["extraction_schema"].append(g.enum_field(
                allvar, ["yes", "no"],
                "yes ONLY if the customer says the date they agreed to is for ALL their products together (for example "
                "'Friday for all of them', 'I will pay everything on the 30th'). Otherwise no.", 0.7))
            for tr in node["transitions"]:
                if tr["target_node"] == f"save_{k}":
                    tr["target_node"] = f"save_{k}_{step}"
            off = s.get("offer") or {}
            # a proposal inside the rules is an agreement: "both on the thirtieth of October" was answered "That is fine"
            # and never recorded, then the step ran out of turns (PUB-13 talkative). Code checks the day; none -> back
            turn = f"p{k}_{step}_turn"
            node["transitions"].insert(1, g.eq(f"prop_{k}_{step}", turn, "proposes", "proposes a day (and amount)"))
            nodes[f"prop_{k}_{step}"] = _code(
                f"prop_{k}_{step}", _WHEN + _SAVE, "close_error",
                _eqs("prop_route", [("ok", f"enter_{k + 1}" if k < K else "finish"), ("back", f"p{k}_{step}")]),
                k=k, all_var=allvar, offer_date_var=off.get("date_var", ""), offer_amount_var=off.get("amount_var", ""), next_weekday=nw,
                require_date=True)
            nodes[f"save_{k}_{step}"] = _code(
                f"save_{k}_{step}", _WHEN + _SAVE, "close_error",
                _eqs("save_route", [("ok", f"enter_{k + 1}" if k < K else "finish")]),
                k=k, all_var=allvar, offer_date_var=off.get("date_var", ""), offer_amount_var=off.get("amount_var", ""), next_weekday=nw)
        nodes.update(built)
        nxt = f"enter_{k + 1}" if k < K else "finish"
        nodes[f"enter_{k}"] = _code(
            f"enter_{k}", _WHEN + _ENTER, "close_error",
            _eqs("enter_route", [("ask", f"p{k}_{start}"), ("ask_floor", f"p{k}_{start_floor}"), ("auto", nxt), ("done", "finish")]), k=k,
            next_weekday=nw)
        for why, nm in (("refused", f"refused_{k}"), ("paid", f"paid_{k}"), ("dispute", f"dispute_{k}")):
            nodes[nm] = _code(nm, _MARK, "close_error", _eqs("mark_route", [("ok", nxt)]), k=k, why=why, reasons=reasons)
            line = (spec.get("situations") or {}).get(why)
            if line:      # a sentence the brief requires when the customer says it (for "paid": payments take a business day to appear)
                nodes[nm]["on_enter"] = {"type": "tts", "text": line}

    # --- read-back and confirmation
    nodes["finish"] = _code("finish", _FINISH, "close_error",
                            _eqs("finish_route", [("readback", "m_readback"), ("readback_q", "m_readback_q"), ("record", "rg_1")]),
                            readback=spec["readback"], max_readbacks=int(spec.get("max_fixes", 3)) + 2, refused_reason=reasons["refused"])
    rb_kinds = ["confirms", "changes", "other"]
    rb_rules = ("\n\nRULES OF THE CALL:\n" + "\n".join("- " + r for r in base_rules)) if base_rules else ""
    fix_fields = [g.enum_field("fix_kind", ["change", "drop", "none", "unknown"],
                               "change: they name a new date or amount, in this message or by saying yes to a date or amount you repeated. "
                               "drop: they no longer want to promise a product. none: the read-back is fine after all. unknown: not yet clear.", 0.6),
                  g.enum_field("fix_slot", ["1", "2", "3", "4", "all", "unknown"],
                               "Which product, by its position in the read-back (1 = first product read). 'all' if they mean every product.", 0.6),
                  {"name": "fix_date", "type": "string", "description": "The new date, if they named one, in the customer's own words "
                   "(for example 'tomorrow', 'this Friday', 'the 30th', '30 October', 'Monday the 26th'). Copy the words; do not turn them into a date. "
                   "When they correct themselves, give the corrected day.", "min_confidence": 0.3},
                  {"name": "fix_amount", "type": "float", "description": "The new amount, if they named one.", "min_confidence": 0.4}]
    rb_task = ("You have read back every agreed promise in one message and asked for one confirmation. The customer's identity is verified.\n"
               "- A clear yes is a confirmation. Do not call any tool; the system records the promises.\n"
               "- If they want to change a date or an amount, or drop a product, say nothing about recording: the system applies the change.\n"
               "- If they ask a question (for example whether you are a robot), answer it in one sentence, then ask again whether they confirm.\n"
               "- Never make an offer, never name a new date or amount yourself, never say anything is recorded, booked or noted." + rb_rules)
    # "Am I talking to a robot? Yes, I confirm." (R PUB-04): the question is answered before anything is recorded
    rb_trs = [g.and_eq("m_answer", [[("rb_turn", "confirms"), ("asked_q", "yes")]], "confirms and asks something"),
              g.eq("rg_1", "rb_turn", "confirms", "confirmed"),
              # the change named in the same message ("No, Monday the twenty sixth") is applied at once (live run, PUB-07)
              g.and_eq("apply_fix", [[("rb_turn", "changes"), ("fix_kind", "change")], [("rb_turn", "changes"), ("fix_kind", "drop")]],
                       "names the change"),
              g.eq("m_fix", "rb_turn", "changes", "wants a change")]
    rb_extract = [g.enum_field("rb_turn", rb_kinds,
                               "Classify ONLY the customer's last message. confirms: a clear yes to the read-back. changes: they want a different date or amount, "
                               "want to drop a product, or say no. other: a question or anything else.")] + fix_fields + [_ASKED_Q]
    # "Are you a robot? I can pay on..." at the read-back (PUB-04 corrects): the next read-back answers it first
    # a fixed line: an llm entry was seen to invent an offer and to say "recorded" before anything was recorded (PUB-12)
    nodes["m_readback"] = g.conversation("m_readback", rb_task, rb_trs, extract=rb_extract,
                                         on_enter={"type": "tts", "text": "{{readback}}"}, first_entry_only=False, max_turns=6, max_turn_target="m_fix")
    nodes["m_answer"] = g.conversation(
        "m_answer", rb_task, rb_trs[1:], extract=rb_extract,
        on_enter={"type": "llm", "prompt": "Answer the customer's question in one sentence, following the rules of the call. Make no offer and "
                  "say nothing is recorded yet. Then ask: \"Shall I go ahead and record it?\""},
        first_entry_only=False, max_turns=4, max_turn_target="m_fix")
    # only when the agreeing message also asked something ("...the 6th. Am I talking to a robot?", PUB-04)
    nodes["m_readback_q"] = g.conversation(
        "m_readback_q", rb_task, rb_trs, extract=rb_extract,
        on_enter={"type": "llm", "prompt": "Answer the customer's question in one sentence, following the rules of the call. Make no offer. "
                  "Then say this read-back exactly as written, every word, amount and date, and nothing after it: {{readback}}"},
        first_entry_only=False, max_turns=6, max_turn_target="m_fix")
    nodes["m_fix"] = g.conversation(
        "m_fix",
        "The customer wants to change something in what you read back. The customer's identity is verified.\n"
        "Ask only which product and what: a new date, a new amount, or dropping it. Do not repeat the change back and do not ask them to confirm it: "
        "the system applies it and reads everything back. Do not compute dates yourself. Never say anything is recorded, booked or noted. "
        "Product numbers follow the order of the read-back (1 is the first product read)." + rb_rules,
        [g.any_eq("apply_fix", "fix_kind", ["change", "drop"], "a change was named"), g.eq("finish", "fix_kind", "none", "no change after all")],
        extract=fix_fields + [_ASKED_Q],
        on_enter={"type": "llm", "prompt": "Ask what they would like to change. Do not name any date or amount yourself."},
        first_entry_only=False, max_turns=6, max_turn_target="finish")
    # a read-back the customer keeps rejecting ends without a promise rather than in a loop to the turn limit (PUB-12)
    nodes["apply_fix"] = _code("apply_fix", _WHEN + _APPLY_FIX, "close_error", _eqs("fix_route", [("ok", "finish"), ("stuck", "fix_stuck")]),
                               reasons=reasons, max_fixes=int(spec.get("max_fixes", 3)), next_weekday=nw)
    nodes["fix_stuck"] = _code("fix_stuck", _STUCK, "close_error", _eqs("stuck_route", [("ok", "finish")]), reasons=reasons)

    # --- record stage
    pt, nt = tools["promise"], tools["note"]
    for k in range(1, K + 1):
        nxt = f"rg_{k + 1}" if k < K else "final"
        nodes[f"rg_{k}"] = _code(f"rg_{k}", _GATE, "close_error",
                                  _eqs("gate_route", [("promise", f"rec_{k}"), ("note", f"note_{k}"), ("skip", nxt)]), k=k,
                                  notes=bool(spec.get("notes", True)))
        body = {F["product"]: "{{s%d_pid}}" % k, F["amount"]: "{{amt_%d}}" % k, F["date"]: "{{date_%d}}" % k}
        ok = api.ok_field(pt)
        # two explicit tries: a failure answered with ok false is not an HTTP error, so a retry setting on the call would not fire
        nodes[f"rec_{k}"] = g.api_request(
            f"rec_{k}", api.pre_action(pt, body, retries=0), f"rec2_{k}",
            transitions=[g.is_true(f"recok_{k}", f"rec_{k}_response.data.{ok}", "recorded")])
        nodes[f"rec2_{k}"] = g.api_request(
            f"rec2_{k}", api.pre_action(pt, body, retries=0), f"recfail_{k}",
            transitions=[g.is_true(f"recok_{k}", f"rec2_{k}_response.data.{ok}", "recorded on the second try")])
        nodes[f"recok_{k}"] = _code(f"recok_{k}", _REC_OK, "close_error", _eqs("rec_route", [("ok", nxt)]), k=k)
        nodes[f"recfail_{k}"] = _code(f"recfail_{k}", _REC_FAIL, "close_error", _eqs("rec_route", [("failed", f"note_{k}" if spec.get("notes", True) else nxt)]), k=k, reasons=reasons)
        nodes[f"note_{k}"] = g.api_request(
            f"note_{k}", api.pre_action(nt, {F["product"]: "{{s%d_pid}}" % k, F["reason"]: "{{reason_%d}}" % k}, retries=2), nxt)
    nodes["final"] = _code("final", _FINAL, "close_error",
                           _eqs("final_route", [("promise", "close_promise"), ("paid", "close_paid"), ("other", "close_other")]),
                           reasons=reasons, outcomes=outcomes, close_reason_of=close_reason_of)

    # --- shared situations
    nodes["hardship_mark"] = _code("hardship_mark", _HARDSHIP_MARK, "close_error", _eqs("hs_route", [("ok", "finish")]), reasons=reasons)
    hs = spec.get("hardship") or {}
    nodes["hardship"] = g.conversation(
        "hardship",
        (hs.get("task") or ("The customer's identity is verified. The customer mentioned illness, a death in the family or job loss. "
                            "Make NO persuasion attempt and offer no payment. If they themselves name a date or an amount, say you will take it; the system handles it."))
        # style "talkative", 11 October: the support team was offered four times while the customer chatted
        + "\nYou offered the connection to the support team once, in your first message here, with one sentence of sympathy. Never offer it again "
          "and never say anything sympathetic again (no 'sorry', no 'I understand how hard'): if they talk about something else, reply in a few "
          "neutral words and wait for their answer.",
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
        nodes[f"transfer_{key}"] = g.api_request(f"transfer_{key}", api.pre_action(tools["transfer"], {F["queue"]: queues[key]}, retries=2), f"close_{key}")
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
