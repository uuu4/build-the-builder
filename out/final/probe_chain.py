import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
full=json.load(open('out/final/workflow.json',encoding='utf-8'))
N=full['nodes']
chain=sys.argv[1].split(',')
show=sys.argv[2]
cust=sys.argv[3] if len(sys.argv)>3 else "95004361"
nodes={}
for i,n in enumerate(chain):
    x=json.loads(json.dumps(N[n])); nxt=chain[i+1] if i+1<len(chain) else 'say'
    x['transitions']=[{"target_node":nxt,"description":"always","condition":{"operator":"always"}}]; x['passthrough_default_transition']=nxt
    nodes[n]=x
nodes['say']={"name":"say","node_type":"conversation","task_message":"Tell the user exactly this text, verbatim: "+show,"transitions":[]}
wid=freya.create_workflow("final-bisect-"+str(len(chain)),{"initial_node":chain[0],"system_prompt":"x","nodes":nodes})["workflow_id"]
t=time.time()
try:
    r=freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":cust,"now":"2026-10-12T10:30:00+03:00"}}); print(r.get('response'))
except Exception as e: print("ERR",str(e)[:100])
print(round(time.time()-t,1))
