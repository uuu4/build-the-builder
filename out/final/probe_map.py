import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
from builder.kit import graph as g
N=json.load(open('out/final/workflow.json',encoding='utf-8'))['nodes']
say={"name":"say","node_type":"conversation","task_message":"Tell the user exactly this text, verbatim: {{dbg}}","transitions":[]}
src="ks = [str(k) + '=' + str(vars[k])[:60] for k in vars if not str(k).startswith('date.') and not str(k).startswith('system')]\nvars['dbg'] = ' ; '.join(sorted(ks))[:2500]\n"
a2=dict(N['get_cards']); a2['transitions']=[g.always("dbg")]; a2['passthrough_default_transition']='dbg'
a2['response_mapping']=[{"path":p,"variable":v} for p,v in [("data.data.validCardsCount","vc"),("data.result.returnCode","rc"),("status_code","sc"),("data.data.cards","cl"),("data","raw")]]
wid=freya.create_workflow("final-probe-map-"+str(time.time()),{"initial_node":"get_cards","system_prompt":"x","nodes":{"get_cards":a2,"dbg":g.code("dbg",src,"say"),"say":say}})["workflow_id"]
print(freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":sys.argv[1] if len(sys.argv)>1 else "95004361"}}).get('response'))
