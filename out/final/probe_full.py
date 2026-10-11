import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
wf=json.load(open('out/final/workflow.json',encoding='utf-8'))
mode=sys.argv[1]
if mode=="nosys": wf["system_prompt"]="Sen Freya Bank asistanısın."
if mode=="notv": wf.pop("test_variables",None)
wid=freya.create_workflow("final-probe-full"+mode+str(time.time()),wf)["workflow_id"]
t=time.time()
try: print(mode, freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{"customerNumber":"93821776","now":"2026-10-12T10:30:00+03:00"}}))
except Exception as ex: print(mode,"ERR",str(ex)[:80])
print(mode, round(time.time()-t,1))
