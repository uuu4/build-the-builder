import json, sys, urllib.request
sys.path.insert(0, '.'); sys.path.insert(0, 'out/final2')
from builder.kit import pycode
import code_bodies as cb
M = 'https://btb-bank-mock.latif-akgun1907.workers.dev/voice/v1/'
def call(svc, data):
    r = urllib.request.Request(M + svc, json.dumps({'data': data}).encode(), {'Content-Type': 'application/json', 'User-Agent': 'curl/8.0'})
    try:
        resp = urllib.request.urlopen(r); code = resp.status; body = json.load(resp)
    except urllib.error.HTTPError as e:
        code = e.code; body = json.load(e)
    return code, body
def flat(prefix, o, out):
    if isinstance(o, dict):
        for k, v in o.items(): flat(prefix + '.' + k, v, out)
    elif isinstance(o, list):
        for i, v in enumerate(o): flat(prefix + '.' + str(i), v, out)
    else:
        out[prefix] = '' if o is None else (str(o) if not isinstance(o, bool) else str(o).lower())
def put(v, node, svc, data):
    code, body = call(svc, data)
    flat(node + '_response.data', body, v); v[node + '_response.status_code'] = str(code)
def run(body, v):
    return pycode.run_locally(pycode.with_params(cb.COMMON + body, {}), v)
for cust in sys.argv[1:]:
    v = {'customerNumber': cust, 'now': '2026-10-12T10:30:00+03:00'}
    put(v, 'get_cards', 'cards.list', {'customerNo': cust, 'aiFlow': 'CardOps'})
    v = run(cb.CARDS, v); print(cust, v['cards_state'], v.get('card_prompt', ''))
    if v['cards_state'] == 'many':
        v['pick_kind'] = 'card'; v['pick_text'] = 'Yıldız Premium'
        v = run(cb.MATCH, v); print(' match', v['match_state'], v['card_prompt'])
    if v.get('sel_num'):
        put(v, 'get_balance', 'cards.balance', {'cardNumber': v['sel_num']})
        v = run(cb.READING, v); print(' ', v['reading_state'], v.get('reading_text'))
        put(v, 'get_email', 'contact.email.get', {'customerNo': cust, 'intAddressInfoType': 'E'})
        v = run(cb.OFFER, v); print(' ', v['offer_state'], v['ar_stage'], v.get('followup_q'), v.get('email_say'))
        put(v, 'get_week', 'statement.week.get', {'cardNumber': v['sel_num']})
        v = run(cb.WEEK, v); print(' ', v['week_state'], v.get('week_text'), v.get('week_prompt'))
