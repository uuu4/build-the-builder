import json,sys
sys.path.insert(0,'.')
from builder.kit import pycode
exec(open('out/final/localtest.py',encoding='utf-8').read().split("cn=sys.argv[1]")[0])
data=json.load(open('out/final/case/test-environment__test-customers.json.txt',encoding='utf-8-sig')) if False else None
import re
txt=open('out/final/case/test-environment__test-customers.md.txt',encoding='utf-8').read()
for cn in sorted(set(re.findall(r'^\| (\d{8}) ',txt,re.M))):
    v={'customerNumber':cn,'now':'2026-10-12T10:30:00+03:00'}
    call('get_cards','cards.list',{'customerNo':cn},v)
    v=pycode.run_locally(src('cards_facts'),v)
    cl=json.loads(v.get('cards_json') or '[]')
    if not cl: print(cn,v.get('cards_state')); continue
    for c in cl:
        w=dict(v); w['sel_card']=c['cardNumber']; w['sel_last4']=c['cardNumberLast4']; w['sel_name']=c.get('productName','')
        call('get_balance','cards.balance',{'cardNumber':c['cardNumber']},w)
        w=pycode.run_locally(src('bal_facts'),w)
        print(cn,c['cardNumber'],w['bal_state'],'|',(w.get('reading_text') or '')[:330])
