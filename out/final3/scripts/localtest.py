import json, sys, urllib.request
sys.path.insert(0, '.')
from builder.kit import pycode
wf = json.load(open('out/final3/workflow.json', encoding='utf-8'))
B = 'https://btb-bank-mock.latif-akgun1907.workers.dev/voice/v1/'
def call(op, data):
    req = urllib.request.Request(B + op, json.dumps({"data": data}).encode(), {"content-type": "application/json", "User-Agent": "curl/8.0"})
    try:
        r = urllib.request.urlopen(req, timeout=30); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
def flatten(pfx, o, out):
    if isinstance(o, dict):
        for k, v in o.items(): flatten(pfx + '.' + k, v, out)
    elif isinstance(o, list):
        for i, v in enumerate(o): flatten(pfx + '.' + str(i), v, out)
    else: out[pfx] = 'true' if o is True else 'false' if o is False else o
def put(v, node, st, body):
    for k in [k for k in v if k.startswith(node + '_response')]: del v[k]
    v[node + '_response.status_code'] = st
    flatten(node + '_response.data', body, v)
def run(node, v):
    src = wf['nodes'][node]['pre_actions'][0]['function']['parameters']['properties']['code']['default']
    return pycode.run_locally(src, v)
cust, now = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '2026-10-12T10:30:00+03:00'
v = {'customerNumber': cust, 'now': now}
put(v, 'get_cards', *call('cards.list', {"customerNo": cust}))
v = run('cards_code', v); print(v['cards_state'], v.get('card_count'), v.get('select_line'))
put(v, 'get_email', *call('contact.email.get', {"customerNo": cust, "intAddressInfoType": "E"}))
v = run('email_code', v); print(v.get('has_email'), v.get('email_spoken'), v.get('offer_line'))
for n in range(1, int(v.get('card_count') or 0) + 1):
    v['card_pick'] = str(n); v = run('pick_code', v)
    put(v, 'get_balance', *call('cards.balance', {"cardNumber": v['sel_number']}))
    v = run('balance_code', v); print('  ', v['bal_state'], v.get('reading_full'), v.get('code_error', ''))
put(v, 'get_week', *call('statement.week.get', {"cardNumber": v['sel_number']}))
v = run('week_code', v); print(v['week_state'], v.get('week_text'), v.get('options_text'))
v['wk_ans'] = sys.argv[3] if len(sys.argv) > 3 else [x for x in '1234' if x != v['cur_week']][0]
v = run('choose_code', v)
put(v, 'decide_week', *call('statement.week.decide', {"cardNumber": v['sel_number'], "newStatementWeek": v['new_week'], "statementDay": v['cur_day']}))
v = run('decide_code', v); print(v['decide_state'], v.get('confirm_text'), v.get('done_text'))
