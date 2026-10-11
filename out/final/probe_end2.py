import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
from builder.kit import graph as g
N=json.load(open('out/final/workflow.json',encoding='utf-8'))['nodes']
mode=sys.argv[1]
keep=["start","get_cards","cards_facts","end_nocard","end_nocard_hangup","end_fail","end_fail_hangup","get_balance"]
nodes={k:json.loads(json.dumps(N[k])) for k in keep}
nodes["get_balance"]["transitions"]=[g.always("end_fail")]; nodes["get_balance"]["passthrough_default_transition"]="end_fail"
nodes["cards_facts"]["transitions"]=[t for t in nodes["cards_facts"]["transitions"] if t["target_node"] in nodes]
if mode=="callclosed":
    nodes["end_nocard_hangup"]["terminal"]["function"]["name"]="call_closed"
if mode=="noapi":
    nodes["start"]["transitions"]=[g.always("end_nocard")]; nodes["start"]["passthrough_default_transition"]="end_nocard"
    for k in ["get_cards","cards_facts","end_fail","end_fail_hangup","get_balance"]: nodes.pop(k)
wid=freya.create_workflow("final-probe-e2"+mode+str(time.time()),{"initial_node":"start","system_prompt":"x","nodes":nodes})["workflow_id"]
t=time.time()
try: print(mode, freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":"93821776"}}))
except Exception as ex: print(mode,"ERR",str(ex)[:80])
print(mode, round(time.time()-t,1))
