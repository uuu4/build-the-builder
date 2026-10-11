import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
from builder.kit import graph as g
N=json.load(open('out/final/workflow.json',encoding='utf-8'))['nodes']
say={"name":"say","node_type":"conversation","task_message":"Tell the user exactly this text, verbatim: {{dbg}}","transitions":[]}
src="ks = [str(k) + '=' + str(vars[k])[:60] for k in vars if 'get_cards' in str(k)]\nvars['dbg'] = 'KEYS ' + ' ; '.join(sorted(ks))[:2500]\n"
a2=json.loads(json.dumps(N['get_cards'])); a2['transitions']=[g.always("dbg")]; a2['passthrough_default_transition']='dbg'
start=g.code("start", "vars['x'] = '1'\n", "get_cards")
wid=freya.create_workflow("final-probe-start"+str(time.time()),{"initial_node":"start","system_prompt":"x","nodes":{"start":start,"get_cards":a2,"dbg":g.code("dbg",src,"say"),"say":say}})["workflow_id"]
print(freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":"95004361"}}).get('response'))
