"""Python source for code nodes. Parameters go in as a JSON string literal, never with braces in the source."""
import json

CALENDAR = r'''import datetime
import json
import re
P = json.loads(PARAMS)
HOL = set(P.get('holidays') or [])
WEEKEND = set(P.get('weekend_days') if P.get('weekend_days') is not None else [5, 6])
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def isbiz(d):
    return d.weekday() not in WEEKEND and d.isoformat() not in HOL
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
def read_list(node, field):
    # A list from an api_request result. A node-level mapping of a list did not arrive in practice;
    # the flattened keys <node>_response.data.<field>.<i>.<key> did. Try the mapped variable first, then those keys.
    v = vars.get(field)
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = None
    if isinstance(v, list) and v:
        return v
    found = dict()
    pat = re.compile('^' + re.escape(node) + r'_response\.data\.' + re.escape(field) + r'\.(\d+)\.(\w+)$')
    for k in list(vars.keys()):
        m = pat.match(str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
def num(x, default=0.0):
    try:
        return float(str(x).replace(',', ''))
    except Exception:
        return default
def money(x):
    x = num(x)
    return str(int(round(x))) if abs(x - round(x)) < 0.005 else '%.2f' % x
def get_now():
    s = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(s[:16])
    except Exception:
        return datetime.datetime.fromisoformat(s[:10] + 'T10:00')
'''


def with_params(body, params):
    """Prefix `body` with the calendar helpers and a PARAMS JSON string. Raises if braces would end up in the source."""
    lit = json.dumps(json.dumps(params))
    lit = lit.replace("{", "\\x7b").replace("}", "\\x7d")
    src = "PARAMS = " + lit + "\n" + CALENDAR + body
    if "{{" in src or "}}" in src:
        raise ValueError("braces in generated code")
    return src


def run_locally(src, variables):
    """Run a snippet the way the platform does: a `vars` dict in, the same dict out. For tests."""
    env = {"vars": dict(variables)}
    exec(compile(src, "<code node>", "exec"), env)
    return env["vars"]
