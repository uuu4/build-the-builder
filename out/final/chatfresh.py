import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
wf=json.load(open('out/final/workflow.json',encoding='utf-8'))
wid=freya.create_workflow("final-chatfresh"+str(time.time()),wf)["workflow_id"]
for path in sys.argv[1:]:
    spec=json.load(open(path,encoding='utf-8')); call=None
    print("=====",path)
    for line in spec["lines"]:
        b={"workflowId":wid,"message":line,"customerVariables":spec["variables"]}
        if call: b["callId"]=call
        try:
            r=freya.api("POST","/api/v2/chat/message",b); call=call or r.get("callId")
            print("C:",line,"\nA:",r.get("response"))
        except Exception as e:
            print("C:",line,"\nERR",str(e)[:80]); break
