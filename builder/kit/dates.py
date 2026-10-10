"""Date and amount rules as Freya code nodes. Standard library only.

Two builders return the Python source of a Freya `code_exec` snippet:

    build_facts_code(params) -> str   run once, after the account is loaded
    build_check_code(params) -> str   run every time the customer proposed a date, an amount or a callback time

Nothing here knows a brief. Every date, holiday, band, deadline rule, field name and window comes in
through `params`. The arithmetic is done in the snippet, so the model is given finished facts as text
(docs/tools-and-code.md, "Code nodes and code_exec").

Snippet rules (checked with assert_code_safe, and the tests execute the shipped source itself):
- no double brace anywhere, also not in the text the snippet writes
- never raises: one try/except around the work, fallback values for every output variable
- routing flags are strings
- imports only json, re, datetime
- everything lives inside one function that takes `vars`, so it also runs when the sandbox executes
  with separate globals and locals

params (everything optional except `bands`):

    now_var               name of the variable holding the current time, ISO, default "now"
    products_var          variable holding the products, default "accounts". Read defensively: a list of
                          dicts, a JSON string of a list, then each name in products_fallback_vars the
                          same two ways, then flattened keys "<name>.<index>.<field>"
    products_fallback_vars  default ["get_account_response.data.products"]
    fields                {"id", "type", "past_due", "days_late"}: names of those keys in a product dict,
                          defaults product_id, type, past_due, days_late
    weekend               Python weekday numbers (Monday is 0), default [5, 6]
    holidays              ["YYYY-MM-DD", ...]
    bands                 [{"name": str, "days_late_min": int|null, "days_late_max": int|null,
                            "deadline": one of
                                {"kind": "business_days", "n": int}     Nth business day after today
                                {"kind": "calendar_days", "n": int, "roll": "back"|"forward"|"none"}
                                {"kind": "end_of_month"}                last business day of this month
                            "attempts": int|null}]
                          the first band that contains the product's days_late wins. A deadline is never
                          before today.
    floor_field_by_type   {"<product type>": "<key of the floor amount in the product dict>"}
    product_label         {"<product type>": "text, may contain <key> of the product dict"}
                          default: the type with spaces
    named_dates           [{"name": str, "kind": "today" | "next_business_day" | "nth_business_day"
                                            | "last_business_day_this_week" | "last_business_day_next_week",
                            "n": int, "if_today_use_next_week": bool}]
                          a last business day that is today (flag set) or already past moves to next week
    callback              {"days": ["today", "next_business_day"], "from": "HH:MM", "to": "HH:MM",
                           "after_now": bool} or null. Both ends are included. With after_now, today
                          starts one minute after the current time. null: callback_check is always 'none'
    calendar_days         the calendar in date_facts covers today and this many days after it, default 21

    order_by              null (the order the account returned, default) or {"field": "past_due" | "days_late",
                          "descending": true}: the order products are discussed in. Slots, the joined lines and
                          s<k>_* follow it; each slot still carries its own product id (s<k>_pid)
    slots                 0 (default) or the largest number of products a customer can have. With slots the
                          snippet also writes, for k = 1 .. slots, in the order the account returned the products
                          (empty strings past the last product): s<k>_pid, s<k>_type, s<k>_label, s<k>_due,
                          s<k>_floor, s<k>_days_late, s<k>_band, s<k>_attempts, s<k>_deadline_text,
                          s<k>_deadline (ISO). Graphs index products by position, not by id.
    lines                 {"<name>": "template"}: per product the variable s<k>_line_<name>. In a template
                          <label> <due> <floor> <days_late> <band> <attempts> <deadline> <deadline_iso> <pid> <type>
                          stand for that product, and <NAME> / <NAME_iso> for a named date (spoken / ISO).
    joined_lines          {"<variable>": "<line name>"} or {"<variable>": {"line": "<line name>", "prefix": "...",
                          "suffix": "...", "suffix_one": "..."}}: the lines of all products, in order, joined by a
                          space, with the prefix before and the suffix after (suffix_one when there is one product)

Only for the check snippet:

    date_var "proposed_date", amount_var "proposed_amount", product_var "current_product",
    callback_date_var "callback_date", callback_time_var "callback_time"

Variables the facts snippet writes (all strings, all always written):

    today (ISO), today_text, now_time (HH:MM)
    per product, with <pid> the product id: band_<pid>, deadline_<pid> (ISO), deadline_text_<pid>,
        floor_<pid> (2 decimals), attempts_<pid>
    per named date: <name> (ISO), <name>_text
    product_count, product_ids (comma separated)
    date_facts   plain-English block for the dialogue model: today, the business-day rule and holidays,
                 one line per product, named dates, callback windows, and a calendar with weekday,
                 business day / weekend / bank holiday, and this week / next week / later (weeks run
                 Monday to Sunday)
    facts_state  'ok' or 'error', facts_error  the reason, empty when ok

Variables the check snippet writes (all strings, all always written):

    date_check            ok | none | invalid | past | not_business_day | after_deadline
    date_check_next       ISO of the first business day on or after the proposed date, set for ok and
                          not_business_day, empty otherwise
    date_check_deadline   ISO deadline of the product, empty when its days_late fit no band
    amount_check          ok | none | invalid | below_floor | above_full
    callback_check        ok | none | invalid | outside_window
    check_text            one to three plain sentences with exact dates, for the dialogue model
    check_product         the product id the check used (the one in product_var, else the first)
    check_state           'ok' or 'error', check_error  the reason, empty when ok
    On error the three checks are 'none' and check_text tells the model not to judge.
"""
import copy
import json
import datetime
import re
import textwrap



def _no_braces(text):
    # Freya leaves a literal double brace in code and the snippet crashes, so none may appear.
    while "{{" in text or "}}" in text:
        text = text.replace("{{", "{ {").replace("}}", "} }")
    return text


def _sanitize(obj):
    if isinstance(obj, str):
        return _no_braces(obj)
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {_no_braces(str(k)): _sanitize(v) for k, v in obj.items()}
    return obj


def code_literal(obj):
    """A Python string literal holding obj as JSON, safe to put inside a Freya code snippet (read it with json.loads)."""
    lit = repr(_no_braces(json.dumps(_sanitize(obj), ensure_ascii=True, separators=(", ", ": "))))
    assert "{{" not in lit and "}}" not in lit
    return lit


def assert_code_safe(code, where="code"):
    if "{{" in code or "}}" in code:
        raise ValueError(where + ": contains a double brace, Freya would leave it unresolved")
    compile(code, where, "exec")

DEFAULT_FIELDS = {"id": "product_id", "type": "type", "past_due": "past_due", "days_late": "days_late"}
DEADLINE_KINDS = ("business_days", "calendar_days", "end_of_month")
ROLLS = ("back", "forward", "none")
NAMED_KINDS = ("today", "next_business_day", "nth_business_day",
               "last_business_day_this_week", "last_business_day_next_week")
CALLBACK_DAYS = ("today", "next_business_day")
FACTS_OUTPUTS = ("today", "today_text", "now_time", "product_count", "product_ids", "date_facts",
                 "facts_state", "facts_error", "holiday_list", "weekend_list")
CHECK_OUTPUTS = ("date_check", "date_check_next", "date_check_deadline", "amount_check", "callback_check",
                 "check_text", "check_product", "check_state", "check_error")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


# ---------------------------------------------------------------- parameters

def _need(cond, message):
    if not cond:
        raise ValueError("dates params: " + message)


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _clock(text, where):
    m = CLOCK_RE.match(str(text).strip())
    _need(m and int(m.group(1)) < 24 and int(m.group(2)) < 60, where + " must be HH:MM")
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


def normalize_params(params):
    """Fill defaults and validate. Raises ValueError with the reason, so a typo shows at build time."""
    _need(isinstance(params, dict), "params must be a dict")
    p = copy.deepcopy(params)
    p.setdefault("now_var", "now")
    p.setdefault("products_var", "accounts")
    p.setdefault("products_fallback_vars", ["get_account_response.data.products"])
    p["fields"] = dict(DEFAULT_FIELDS, **(p.get("fields") or {}))
    p.setdefault("weekend", [5, 6])
    p.setdefault("holidays", [])
    p["floor_field_by_type"] = dict(p.get("floor_field_by_type") or {})
    p["product_label"] = dict(p.get("product_label") or {})
    p["named_dates"] = list(p.get("named_dates") or [])
    p.setdefault("callback", None)
    p.setdefault("calendar_days", 21)
    p.setdefault("date_var", "proposed_date")
    p.setdefault("amount_var", "proposed_amount")
    p.setdefault("product_var", "current_product")
    p.setdefault("callback_date_var", "callback_date")
    p.setdefault("callback_time_var", "callback_time")

    for key in ("now_var", "products_var", "date_var", "amount_var", "product_var",
                "callback_date_var", "callback_time_var"):
        _need(isinstance(p[key], str) and p[key].strip(), key + " must be a non-empty string")
    _need(isinstance(p["products_fallback_vars"], list)
          and all(isinstance(x, str) and x for x in p["products_fallback_vars"]),
          "products_fallback_vars must be a list of names")
    _need(all(isinstance(v, str) and v for v in p["fields"].values()), "fields values must be names")

    _need(isinstance(p["weekend"], list) and all(_is_int(w) and 0 <= w <= 6 for w in p["weekend"]),
          "weekend must be a list of weekday numbers 0 to 6")
    _need(len(set(p["weekend"])) < 7, "weekend cannot cover all seven days")
    _need(isinstance(p["holidays"], list), "holidays must be a list")
    for h in p["holidays"]:
        m = DATE_RE.match(str(h))
        _need(m, "holiday %r is not YYYY-MM-DD" % (h,))
        try:
            datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            _need(False, "holiday %r is not a real date" % (h,))

    bands = p.get("bands")
    _need(isinstance(bands, list) and bands, "bands is required and must be a non-empty list")
    for i, b in enumerate(bands):
        where = "bands[%d]" % i
        _need(isinstance(b, dict) and isinstance(b.get("name"), str) and b["name"], where + " needs a name")
        for k in ("days_late_min", "days_late_max"):
            _need(b.get(k) is None or _is_int(b[k]), where + "." + k + " must be an int or null")
        _need(b.get("attempts") is None or _is_int(b["attempts"]), where + ".attempts must be an int or null")
        d = b.get("deadline")
        _need(isinstance(d, dict) and d.get("kind") in DEADLINE_KINDS,
              where + ".deadline.kind must be one of " + ", ".join(DEADLINE_KINDS))
        if d["kind"] in ("business_days", "calendar_days"):
            _need(_is_int(d.get("n")) and 0 <= d["n"] <= 1000, where + ".deadline.n must be an int from 0 to 1000")
        if d["kind"] == "calendar_days":
            d["roll"] = d.get("roll", "back")
            _need(d["roll"] in ROLLS, where + ".deadline.roll must be one of " + ", ".join(ROLLS))

    _need(isinstance(p["floor_field_by_type"], dict), "floor_field_by_type must be a dict")
    _need(isinstance(p["product_label"], dict), "product_label must be a dict")

    taken = set(FACTS_OUTPUTS) | set(CHECK_OUTPUTS)
    for i, nd in enumerate(p["named_dates"]):
        where = "named_dates[%d]" % i
        _need(isinstance(nd, dict) and NAME_RE.match(str(nd.get("name", ""))), where + " needs a plain name")
        _need(nd.get("kind") in NAMED_KINDS, where + ".kind must be one of " + ", ".join(NAMED_KINDS))
        if nd["kind"] == "nth_business_day":
            _need(_is_int(nd.get("n")) and 0 <= nd["n"] <= 1000, where + ".n must be an int from 0 to 1000")
        for key in (nd["name"], nd["name"] + "_text"):
            _need(key not in taken, where + " name clashes with another variable: " + key)
            taken.add(key)

    cb = p["callback"]
    if cb is not None:
        _need(isinstance(cb, dict), "callback must be a dict or null")
        days = cb.get("days")
        _need(isinstance(days, list) and days and all(x in CALLBACK_DAYS for x in days),
              "callback.days must be a list of " + ", ".join(CALLBACK_DAYS))
        cb = dict(cb)
        cb["from"] = _clock(cb.get("from"), "callback.from")
        cb["to"] = _clock(cb.get("to"), "callback.to")
        cb["after_now"] = bool(cb.get("after_now", True))
        p["callback"] = cb
    _need(_is_int(p["calendar_days"]) and 1 <= p["calendar_days"] <= 120, "calendar_days must be an int from 1 to 120")

    ob = p.get("order_by")
    p["order_by"] = None if not ob else {"field": ob.get("field"), "descending": bool(ob.get("descending", True))}
    _need(p["order_by"] is None or p["order_by"]["field"] in ("past_due", "days_late"), "order_by.field must be past_due or days_late")
    p.setdefault("slots", 0)
    p["lines"] = dict(p.get("lines") or {})
    p["joined_lines"] = dict(p.get("joined_lines") or {})
    _need(_is_int(p["slots"]) and 0 <= p["slots"] <= 8, "slots must be an int from 0 to 8")
    for name, tpl in p["lines"].items():
        _need(NAME_RE.match(str(name)) and isinstance(tpl, str), "lines needs plain names and text templates")
    for out_var, spec in list(p["joined_lines"].items()):
        if isinstance(spec, str):
            spec = {"line": spec}
        spec = dict(spec)
        spec.setdefault("prefix", "")
        spec.setdefault("suffix", "")
        spec.setdefault("suffix_one", spec["suffix"])
        p["joined_lines"][out_var] = spec
        _need(NAME_RE.match(str(out_var)) and out_var not in taken, "joined_lines name clashes: " + str(out_var))
        _need(spec.get("line") in p["lines"], "joined_lines refers to unknown line " + str(spec.get("line")))
        taken.add(out_var)
    if p["lines"] or p["joined_lines"]:
        _need(p["slots"] > 0, "lines need slots")
    return p


# ---------------------------------------------------------------- shared snippet source
# Plain text, no braces doubled. Indented four spaces into the function body when assembled.

_HELPERS = r"""
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MO = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
F = P['fields']

def clean(s):
    s = str(s)
    while ('{' + '{') in s or ('}' + '}') in s:
        s = s.replace('{' + '{', '{ ' + '{').replace('}' + '}', '} ' + '}')
    return s

def blank(x):
    if x is None:
        return True
    if isinstance(x, (int, float)):
        return False
    s = str(x).strip().lower()
    return s in ('', 'none', 'null', 'nan', 'n/a', 'unknown', 'undefined') or ('{' + '{') in s

def num(x):
    if x is None or isinstance(x, (bool, dict, list, tuple)):
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    else:
        s = re.sub(r'[^0-9.,\-]', '', str(x))
        if ',' in s and '.' in s:
            s = s.replace(',', '')
        elif ',' in s:
            if re.match(r'^-?\d{1,3}(,\d{3})+$', s):
                s = s.replace(',', '')
            elif re.match(r'^-?\d+,\d{1,2}$', s):
                s = s.replace(',', '.')
            else:
                s = s.replace(',', '')
        try:
            v = float(s)
        except Exception:
            return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return v

def to_int(x):
    v = num(x)
    if v is None:
        return None
    return int(round(v))

def money(x):
    if x is None:
        return 'not known'
    return '%.2f' % x

def parse_date(s):
    m = re.match(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)', str(s))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None

def parse_clock(s):
    m = re.search(r'(?:^|[T\s])(\d{1,2}):(\d{2})(?!\d)(?:\s*([AaPp])\.?[Mm]\.?)?', str(s))
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2))
    if m.group(3):
        if h < 1 or h > 12:
            return None
        h = h % 12
        if m.group(3).lower() == 'p':
            h = h + 12
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi

def iso(d):
    return d.isoformat()

def dtext(d):
    return '%s %d %s %d' % (WD[d.weekday()], d.day, MO[d.month - 1], d.year)

def hhmm(m):
    return '%02d:%02d' % (m // 60, m % 60)

weekend = set()
for w in P['weekend']:
    weekend.add(int(w))
hol = set()
for h in P['holidays']:
    hd = parse_date(h)
    if hd is not None:
        hol.add(hd)

def is_bd(d):
    return d.weekday() not in weekend and d not in hol

def bd_on_or_after(d):
    x = d
    for i in range(800):
        if is_bd(x):
            return x
        x = x + ONE
    raise ValueError('no business day found')

def bd_on_or_before(d):
    x = d
    for i in range(800):
        if is_bd(x):
            return x
        x = x - ONE
    raise ValueError('no business day found')

def next_bd_after(d):
    return bd_on_or_after(d + ONE)

def add_bd(d, n):
    x = d
    for i in range(int(n)):
        x = next_bd_after(x)
    return x

def monday(d):
    return d - datetime.timedelta(days=d.weekday())

def last_bd_of_week(d):
    return bd_on_or_before(monday(d) + datetime.timedelta(days=6))

def week_tag(d, today):
    diff = (monday(d) - monday(today)).days
    if diff < 0:
        return 'earlier'
    if diff == 0:
        return 'this week'
    if diff == 7:
        return 'next week'
    return 'later'

def day_kind(d):
    if d.weekday() in weekend:
        return 'weekend'
    if d in hol:
        return 'bank holiday'
    return 'business day'

def read_now():
    raw = vars.get(P['now_var'])
    if blank(raw):
        raise ValueError('the variable ' + P['now_var'] + ' is missing')
    d = parse_date(raw)
    if d is None:
        raise ValueError('the variable ' + P['now_var'] + ' is not an ISO date')
    return d, parse_clock(raw)

def deadline_for(band, today):
    dl = band.get('deadline') or dict()
    kind = dl.get('kind')
    d = None
    if kind == 'business_days':
        d = add_bd(today, dl.get('n', 0))
    elif kind == 'calendar_days':
        d = today + datetime.timedelta(days=int(dl.get('n', 0)))
        roll = dl.get('roll', 'back')
        if roll == 'forward':
            d = bd_on_or_after(d)
        elif roll == 'back':
            d = bd_on_or_before(d)
    elif kind == 'end_of_month':
        first_next = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        d = bd_on_or_before(first_next - ONE)
    if d is not None and d < today:
        d = bd_on_or_after(today)
    return d

def find_band(days_late):
    if days_late is None:
        return None
    for b in P['bands']:
        lo = b.get('days_late_min')
        hi = b.get('days_late_max')
        if (lo is None or days_late >= lo) and (hi is None or days_late <= hi):
            return b
    return None

def rows_from(v):
    if isinstance(v, str):
        t = v.strip()
        if t == '':
            return None
        try:
            v = json.loads(t)
        except Exception:
            try:
                v = json.loads(t.replace("'", '"').replace('None', 'null').replace('True', 'true').replace('False', 'false'))
            except Exception:
                return None
    if isinstance(v, dict):
        if 'products' in v:
            return rows_from(v.get('products'))
        if F['id'] in v:
            v = [v]
    if isinstance(v, (list, tuple)):
        rows = [x for x in v if isinstance(x, dict)]
        if rows:
            return rows
    return None

def flat_rows(prefix):
    pat = re.compile('^' + re.escape(prefix) + r'\.(\d+)\.(\w+)$')
    try:
        keys = list(vars.keys())
    except Exception:
        keys = list(vars)
    rows = dict()
    for k in keys:
        m = pat.match(str(k))
        if m:
            idx = int(m.group(1))
            if idx not in rows:
                rows[idx] = dict()
            rows[idx][m.group(2)] = vars.get(k)
    return [rows[i] for i in sorted(rows.keys())]

def load_products():
    names = [P['products_var']] + list(P['products_fallback_vars'])
    for n in names:
        rows = rows_from(vars.get(n))
        if rows:
            return rows
    for n in list(P['products_fallback_vars']) + [P['products_var']]:
        rows = flat_rows(n)
        if rows:
            return rows
    return []

def label_for(p, ptype):
    tpl = P['product_label'].get(ptype)
    if not tpl:
        tpl = ptype.replace('_', ' ') if ptype else 'product'
    out = str(tpl)
    for k in list(p.keys()):
        out = out.replace('<' + str(k) + '>', str(p.get(k)))
    out = re.sub(r'\s*<\w+>', '', out)
    return re.sub(r'\s+', ' ', out).strip()

def facts_for(p, i, today):
    f = dict()
    pid = p.get(F['id'])
    pid = '' if pid is None else str(pid).strip()
    if pid == '':
        pid = 'p' + str(i + 1)
    f['pid'] = pid
    f['key'] = re.sub(r'\W', '_', pid)
    ptype = p.get(F['type'])
    ptype = '' if ptype is None else str(ptype).strip()
    f['type'] = ptype
    f['past_due'] = num(p.get(F['past_due']))
    f['days_late'] = to_int(p.get(F['days_late']))
    band = find_band(f['days_late'])
    f['band'] = '' if band is None else str(band.get('name'))
    f['deadline'] = None if band is None else deadline_for(band, today)
    f['attempts'] = None if band is None else band.get('attempts')
    ffield = P['floor_field_by_type'].get(ptype, '')
    f['floor_field'] = ffield
    f['floor'] = num(p.get(ffield)) if ffield else None
    f['label'] = label_for(p, ptype)
    return f

def all_facts(today):
    rows = load_products()
    res = []
    used = set()
    for i in range(len(rows)):
        f = facts_for(rows[i], i, today)
        if f['key'] in used:
            f['pid'] = f['pid'] + '_' + str(i + 1)
            f['key'] = f['key'] + '_' + str(i + 1)
        used.add(f['key'])
        res.append(f)
    ob = P.get('order_by')
    if ob:
        res = sorted(res, key=lambda f: -(f[ob['field']] or 0) if ob['descending'] else (f[ob['field']] or 0))
    return res

def named_date(nd, today):
    kind = nd.get('kind')
    if kind == 'today':
        return today
    if kind == 'next_business_day':
        return next_bd_after(today)
    if kind == 'nth_business_day':
        return add_bd(today, nd.get('n', 1))
    nextweek = today + datetime.timedelta(days=7)
    if kind == 'last_business_day_next_week':
        return last_bd_of_week(nextweek)
    if kind == 'last_business_day_this_week':
        d = last_bd_of_week(today)
        if d < today or (d == today and nd.get('if_today_use_next_week')):
            d = last_bd_of_week(nextweek)
        return d
    raise ValueError('unknown named date kind ' + str(kind))

def callback_slots(today, now_min):
    cb = P.get('callback')
    slots = []
    if not cb:
        return slots
    start = parse_clock(cb.get('from'))
    end = parse_clock(cb.get('to'))
    for name in cb.get('days') or []:
        if name == 'today':
            d = today
        elif name == 'next_business_day':
            d = next_bd_after(today)
        else:
            continue
        lo = start
        if cb.get('after_now') and d == today and now_min is not None:
            lo = max(start, now_min + 1)
        slots.append((name, d, lo, end))
    return slots

def window_text(slots):
    parts = []
    for s in slots:
        if s[2] <= s[3]:
            parts.append('%s from %s to %s' % (dtext(s[1]), hhmm(s[2]), hhmm(s[3])))
    if not parts:
        return 'no callback time is available'
    return ' or '.join(parts)
"""


_FACTS_BODY = r"""
def facts_text(today, now_min, fl, nds):
    L = []
    when = 'Today is %s (%s).' % (dtext(today), iso(today))
    if now_min is not None:
        when = when + ' The time now is %s.' % hhmm(now_min)
    L.append(when)
    bdays = [WD[i] for i in range(7) if i not in weekend]
    wdays = [WD[i] for i in range(7) if i in weekend]
    L.append('Business days are %s. %s not business days.' % (', '.join(bdays), (', '.join(wdays) + ' and bank holidays are') if wdays else 'Bank holidays are'))
    L.append('Counting business days starts with the day after today: day 1 is the first business day after today.')
    hs = sorted([h for h in hol if h >= today])
    if hs:
        L.append('Bank holidays from today on: ' + ', '.join(['%s (%s)' % (dtext(h), iso(h)) for h in hs]) + '.')
    else:
        L.append('There are no bank holidays from today on.')
    L.append('Weeks run Monday to Sunday.')
    L.append('')
    if fl:
        L.append('Products (%d):' % len(fl))
    else:
        L.append('Products: no account has been loaded in this call. Do not state any product, amount or deadline.')
    for f in fl:
        dlabel = F['days_late'].replace('_', ' ').capitalize()
        t = '- %s: %s. Past due %s. %s: %s.' % (f['pid'], f['label'], money(f['past_due']), dlabel, 'not known' if f['days_late'] is None else str(f['days_late']))
        if f['band']:
            t = t + ' Band: %s.' % f['band']
        else:
            t = t + ' No band fits this product.'
        if f['deadline'] is not None:
            t = t + ' Deadline: %s (%s), the latest date you can record.' % (dtext(f['deadline']), iso(f['deadline']))
        else:
            t = t + ' Deadline: not known.'
        if f['floor'] is not None:
            t = t + ' Floor: %s (field %s).' % (money(f['floor']), f['floor_field'])
        else:
            t = t + ' Floor: not known.'
        if f['attempts'] is not None:
            t = t + ' Attempts: %s.' % f['attempts']
        L.append(t)
    if nds:
        L.append('')
        L.append('Named dates:')
        for nd, d in nds:
            kind = str(nd.get('kind')).replace('_', ' ')
            if nd.get('kind') == 'nth_business_day':
                kind = 'business day number %s after today' % nd.get('n')
            if nd.get('if_today_use_next_week'):
                kind = kind + ', moved to next week when it is today'
            L.append('- %s: %s (%s) [%s]' % (nd.get('name'), dtext(d), iso(d), kind))
    slots = callback_slots(today, now_min)
    if slots:
        cb = P['callback']
        L.append('')
        L.append('Callback windows (both ends included%s):' % (', later than now for today' if cb.get('after_now') else ''))
        for s in slots:
            if s[2] <= s[3]:
                L.append('- %s (%s), %s: from %s to %s' % (dtext(s[1]), iso(s[1]), s[0].replace('_', ' '), hhmm(s[2]), hhmm(s[3])))
            else:
                L.append('- %s (%s), %s: no time left' % (dtext(s[1]), iso(s[1]), s[0].replace('_', ' ')))
    L.append('')
    L.append('Calendar, one line per day (date, weekday: kind of day, week):')
    for i in range(int(P['calendar_days']) + 1):
        d = today + datetime.timedelta(days=i)
        L.append('%s %s: %s, %s%s' % (iso(d), WD[d.weekday()], day_kind(d), week_tag(d, today), ', today' if i == 0 else ''))
    return '\n'.join(L)

out = dict()
st = dict()
try:
    today, now_min = read_now()
    st['today'] = today
    st['now_min'] = now_min
    fl = all_facts(today)
    st['keys'] = [f['key'] for f in fl]
    out['today'] = iso(today)
    out['today_text'] = dtext(today)
    out['now_time'] = '' if now_min is None else hhmm(now_min)
    for f in fl:
        k = f['key']
        dl = f['deadline']
        out['band_' + k] = f['band']
        out['deadline_' + k] = '' if dl is None else iso(dl)
        out['deadline_text_' + k] = '' if dl is None else dtext(dl)
        out['floor_' + k] = '' if f['floor'] is None else '%.2f' % f['floor']
        out['attempts_' + k] = '' if f['attempts'] is None else str(f['attempts'])
    nds = []
    for nd in P['named_dates']:
        d = named_date(nd, today)
        out[nd['name']] = iso(d)
        out[nd['name'] + '_text'] = dtext(d)
        nds.append((nd, d))
    out['product_count'] = str(len(fl))
    out['product_ids'] = ','.join([f['pid'] for f in fl])
    nvals = dict()
    for nd, d in nds:
        nvals[nd['name']] = dtext(d)
        nvals[nd['name'] + '_iso'] = iso(d)
    for i in range(int(P['slots'])):
        pre = 's' + str(i + 1) + '_'
        vals = dict()
        if i < len(fl):
            f = fl[i]
            dl = f['deadline']
            vals = dict(pid=f['pid'], type=f['type'], label=f['label'], due=money(f['past_due']),
                        floor='' if f['floor'] is None else money(f['floor']), days_late=str(f['days_late']),
                        band=f['band'], attempts='' if f['attempts'] is None else str(f['attempts']),
                        deadline='' if dl is None else dtext(dl), deadline_iso='' if dl is None else iso(dl))
        else:
            for key in ('pid', 'type', 'label', 'due', 'floor', 'days_late', 'band', 'attempts', 'deadline', 'deadline_iso'):
                vals[key] = ''
        for key in vals:
            out[pre + ('deadline_text' if key == 'deadline' else 'deadline' if key == 'deadline_iso' else key)] = vals[key]
        for lname in P['lines']:
            txt = ''
            if i < len(fl):
                txt = P['lines'][lname]
                for key in vals:
                    txt = txt.replace('<' + key + '>', vals[key])
                for key in nvals:
                    txt = txt.replace('<' + key + '>', nvals[key])
            out[pre + 'line_' + lname] = txt
    for ovar in P['joined_lines']:
        js = P['joined_lines'][ovar]
        cnt = min(int(P['slots']), len(fl))
        body = ' '.join([out['s' + str(i + 1) + '_line_' + js['line']] for i in range(cnt)])
        out[ovar] = js['prefix'] + body + (js['suffix_one'] if cnt == 1 else js['suffix'])
    out['date_facts'] = facts_text(today, now_min, fl, nds)
    out['holiday_list'] = ','.join(sorted([iso(h) for h in hol]))       # for later code nodes (multi.py) that check a date
    out['weekend_list'] = ','.join([str(w) for w in sorted(weekend)])
    out['facts_state'] = 'ok'
    out['facts_error'] = ''
except Exception as e:
    reason = clean(type(e).__name__ + ': ' + str(e))
    out = dict()
    td = st.get('today')
    nm = st.get('now_min')
    out['today'] = '' if td is None else iso(td)
    out['today_text'] = '' if td is None else dtext(td)
    out['now_time'] = '' if nm is None else hhmm(nm)
    old_ids = [x for x in str(vars.get('product_ids') or '').split(',') if x]
    for k in st.get('keys', []) + [re.sub(r'\W', '_', x) for x in old_ids]:
        for pre in ('band_', 'deadline_', 'deadline_text_', 'floor_', 'attempts_'):
            out[pre + k] = ''
    for nd in P['named_dates']:
        out[nd['name']] = ''
        out[nd['name'] + '_text'] = ''
    out['product_count'] = '0'
    out['product_ids'] = ''
    out['date_facts'] = 'The date facts could not be computed (' + reason + '). Do not state any date, weekday or deadline as a fact. Tell the customer that you cannot confirm dates right now.'
    out['facts_state'] = 'error'
    out['facts_error'] = reason
for k in list(out.keys()):
    v = out[k]
    vars[k] = clean(v) if isinstance(v, str) else v
"""


_CHECK_BODY = r"""
def check_date(f, today, raw):
    if blank(raw):
        return 'none', '', ''
    d = parse_date(raw)
    if d is None:
        return 'invalid', '', 'The proposed date could not be read as a calendar date. Ask the customer for the exact day.'
    dt = dtext(d)
    dl = f['deadline']
    latest = None if dl is None else bd_on_or_before(dl)
    if d < today:
        return 'past', '', '%s is in the past. Today is %s. The earliest date you can record is %s.' % (dt, dtext(today), dtext(bd_on_or_after(today)))
    if dl is not None and d > dl:
        return 'after_deadline', '', '%s is after the deadline. The latest date you can record is %s.' % (dt, dtext(latest))
    if not is_bd(d):
        nxt = bd_on_or_after(d)
        why = 'a weekend day' if d.weekday() in weekend else 'a bank holiday'
        if dl is not None and nxt > dl:
            return 'after_deadline', '', '%s is %s, not a business day, and the next business day (%s) is after the deadline. The latest date you can record is %s.' % (dt, why, dtext(nxt), dtext(latest))
        t = '%s is %s, not a business day. The next business day is %s' % (dt, why, dtext(nxt))
        if dl is not None:
            t = t + ', which is inside the deadline (%s).' % dtext(dl)
        else:
            t = t + '.'
        return 'not_business_day', iso(nxt), t
    if dl is not None:
        return 'ok', iso(d), '%s is a business day and is not after the deadline (%s).' % (dt, dtext(dl))
    return 'ok', iso(d), '%s is a business day.' % dt

def check_amount(f, raw):
    if blank(raw):
        return 'none', ''
    a = num(raw)
    if a is None or a <= 0:
        return 'invalid', 'The proposed amount could not be read as a positive number. Ask the customer for an amount.'
    fl = f['floor']
    full = f['past_due']
    fname = f['floor_field'].replace('_', ' ')
    if fl is not None and a < fl - 0.005:
        return 'below_floor', 'The amount %s is below the floor of %s (%s), so it cannot be recorded. The floor is the lowest amount you can record.' % (money(a), money(fl), fname)
    if full is not None and a > full + 0.005:
        return 'above_full', 'The amount %s is more than the full past-due amount of %s, so it cannot be recorded. The most you can record is %s.' % (money(a), money(full), money(full))
    return 'ok', 'The amount %s can be recorded.' % money(a)

def check_callback(today, now_min, rd, rt):
    if not P.get('callback'):
        return 'none', ''
    if blank(rd) and blank(rt):
        return 'none', ''
    d = None if blank(rd) else parse_date(rd)
    if d is None and not blank(rt):
        d = parse_date(rt)
    tm = None if blank(rt) else parse_clock(rt)
    if tm is None and not blank(rd):
        tm = parse_clock(rd)
    if d is None or tm is None:
        return 'invalid', 'The callback day or time could not be read. Ask the customer for a day and a time of day.'
    slots = callback_slots(today, now_min)
    mine = '%s at %s' % (dtext(d), hhmm(tm))
    for s in slots:
        if s[1] == d and s[2] <= tm <= s[3]:
            return 'ok', 'A callback on %s is inside the allowed window.' % mine
    return 'outside_window', 'A callback on %s is outside the allowed window. A callback can be set for %s.' % (mine, window_text(slots))

out = dict()
try:
    today, now_min = read_now()
    fl = all_facts(today)
    if not fl:
        raise ValueError('no products found')
    cur = fl[0]
    want = vars.get(P['product_var'])
    if not blank(want):
        w = str(want).strip().lower()
        for f in fl:
            if f['pid'].lower() == w or f['key'].lower() == w:
                cur = f
                break
    ds, dnext, dtxt = check_date(cur, today, vars.get(P['date_var']))
    am, atxt = check_amount(cur, vars.get(P['amount_var']))
    cs, ctxt = check_callback(today, now_min, vars.get(P['callback_date_var']), vars.get(P['callback_time_var']))
    texts = [t for t in (dtxt, atxt, ctxt) if t]
    out['date_check'] = ds
    out['date_check_next'] = dnext
    out['date_check_deadline'] = '' if cur['deadline'] is None else iso(cur['deadline'])
    out['amount_check'] = am
    out['callback_check'] = cs
    out['check_text'] = ' '.join(texts) if texts else 'Nothing was proposed, so there is nothing to check.'
    out['check_product'] = cur['pid']
    out['check_state'] = 'ok'
    out['check_error'] = ''
except Exception as e:
    reason = clean(type(e).__name__ + ': ' + str(e))
    out = dict()
    out['date_check'] = 'none'
    out['date_check_next'] = ''
    out['date_check_deadline'] = ''
    out['amount_check'] = 'none'
    out['callback_check'] = 'none'
    out['check_text'] = 'The check could not be run (' + reason + '). Do not tell the customer whether the date, the amount or the callback time is allowed. Say that you cannot confirm it right now.'
    out['check_product'] = ''
    out['check_state'] = 'error'
    out['check_error'] = reason
for k in list(out.keys()):
    v = out[k]
    vars[k] = clean(v) if isinstance(v, str) else v
"""


def _assemble(params, body, fallback_keys, where):
    p = normalize_params(params)
    head = "import json\nimport re\nimport datetime\nP = json.loads(%s)\n" % code_literal(p)
    inner = head + _HELPERS + body
    fallback = "\n".join("vars[%r] = %r" % (k, v) for k, v in fallback_keys)
    code = ("def _run(vars):\n" + textwrap.indent(inner, "    ") + "\n"
            "try:\n    _run(vars)\nexcept Exception:\n" + textwrap.indent(fallback, "    ") + "\n")
    assert_code_safe(code, where)
    return code


def build_facts_code(params):
    """Python source of the code node that computes the date facts once, after the account is loaded."""
    fallback = [("facts_state", "error"), ("facts_error", "unexpected failure"),
                ("date_facts", "The date facts could not be computed. Do not state any date, weekday or "
                               "deadline as a fact. Tell the customer that you cannot confirm dates right now.")]
    return _assemble(params, _FACTS_BODY, fallback, "dates.facts")


def build_check_code(params):
    """Python source of the code node that checks what the customer proposed against the rules."""
    fallback = [("date_check", "none"), ("amount_check", "none"), ("callback_check", "none"),
                ("check_state", "error"), ("check_error", "unexpected failure"),
                ("check_text", "The check could not be run. Do not tell the customer whether the date, the "
                               "amount or the callback time is allowed. Say that you cannot confirm it right now.")]
    return _assemble(params, _CHECK_BODY, fallback, "dates.check")


def run_code(code, variables=None):
    """Execute a snippet the way Freya does: a dict called vars. Returns that dict."""
    v = {} if variables is None else variables
    exec(code, {"vars": v})
    return v
