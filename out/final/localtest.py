import json,sys,pathlib
sys.path.insert(0,'.')
from builder.kit import pycode
wf=json.load(open('out/final/workflow.json',encoding='utf-8'))
cust=json.load(open('out/final/case/test-environment__test-customers.json.txt',encoding='utf-8')) if False else None
def src(n): return wf['nodes'][n]['pre_actions'][0]['function']['parameters']['properties']['code']['default']
def flat(prefix,o,out):
    if isinstance(o,dict):
        for k,v in o.items(): flat(prefix+'.'+k,v,out)
    elif isinstance(o,list):
        for i,v in enumerate(o): flat(prefix+'.'+str(i),v,out)
    else: out[prefix]=o if not isinstance(o,bool) else str(o).lower()
import urllib.request
U='https://btb-bank-mock.latif-akgun1907.workers.dev/voice/v1/'
def call(node,op,data,v):
    req=urllib.request.Request(U+op,data=json.dumps({"data":data}).encode(),headers={'content-type':'application/json','user-agent':'curl/8'})
    try:
        r=urllib.request.urlopen(req,timeout=20); code=r.status; body=json.loads(r.read())
    except urllib.error.HTTPError as e:
        code=e.code; body=json.loads(e.read())
    v[node+'_response.status_code']=code
    flat(node+'_response.data',body,v)
cn=sys.argv[1]
v={'customerNumber':cn,'now':sys.argv[2] if len(sys.argv)>2 else '2026-10-12T10:30:00+03:00'}
call('get_cards','cards.list',{'customerNo':cn},v)
v=pycode.run_locally(src('cards_facts'),v); print(v.get('cards_state'),v.get('select_prompt'),v.get('card_menu'))
if v.get('cards_state')=='multi':
    v['sel_act']='choose'; v['sel_name_said']=sys.argv[3] if len(sys.argv)>3 else ''; v['sel_digits_said']=sys.argv[4] if len(sys.argv)>4 else ''
    v=pycode.run_locally(src('match_card'),v); print(v['match_state'],v.get('select_prompt'))
if v.get('sel_card'):
    call('get_balance','cards.balance',{'cardNumber':v['sel_card']},v)
    v=pycode.run_locally(src('bal_facts'),v); print(v['bal_state']); print(v.get('reading_text'))
    call('get_email','contact.email.get',{'customerNo':cn,'intAddressInfoType':'E'},v)
    v=pycode.run_locally(src('email_facts'),v); print(v.get('route'),v.get('email_say'),v.get('offer_text'))
    call('get_week','statement.week.get',{'cardNumber':v['sel_card']},v)
    v=pycode.run_locally(src('week_facts'),v); print(v.get('week_state'),v.get('week_intro'))
    v['week_pick']='3'; v=pycode.run_locally(src('week_check'),v)
    call('decide','statement.week.decide',{'cardNumber':v['sel_card'],'newStatementWeek':v['new_week'],'statementDay':v['cur_day']},v)
    v=pycode.run_locally(src('decide_facts'),v); print(v.get('dec_state'),v.get('confirm_text'),v.get('week_done'))
