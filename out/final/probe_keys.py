import sys,json; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
from builder.kit import graph as g
N=json.load(open('out/final/workflow.json',encoding='utf-8'))['nodes']
say={"name":"say","node_type":"conversation","task_message":"Tell the user exactly this text, verbatim: {{dbg}}","transitions":[]}
src="ks = [str(k) + '=' + str(vars[k])[:25] for k in vars ]\nvars['dbg'] = ' ; '.join(sorted(ks))[:1800]\n"
a2=dict(N['get_cards']); a2['transitions']=[g.always("dbg")]; a2['passthrough_default_transition']='dbg'
wid=freya.create_workflow("final-probe-keys-"+str(__import__("time").time()),{"initial_node":"get_cards","system_prompt":"x","nodes":{"get_cards":a2,"dbg":g.code("dbg",src,"say"),"say":say}})["workflow_id"]
print(freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":"95004361"}}).get('response'))
