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
