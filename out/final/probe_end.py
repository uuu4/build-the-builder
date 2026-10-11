import sys,json,time; sys.path.insert(0,'.'); sys.path=[p for p in sys.path if not p.endswith('final')]
import freya
from builder.kit import graph as g
mode=sys.argv[1]
e=g.end("bye")
if mode=='custom':
    e['terminal']['function']['parameters']['properties']={"message_mode":{"type":"string","default":"custom"},"spoken_message":{"type":"string","default":"Sizi ana menüye yönlendiriyorum."}}
nodes={"start":g.code("start","vars['x'] = '1'\n","bye"),"bye":e}
if mode=='tts':
    nodes["start"]=g.code("start","vars['x'] = '1'\n","say")
    nodes["say"]={"name":"say","node_type":"code","passthrough":True,"passthrough_default_transition":"bye","on_enter":{"type":"tts","text":"Sizi ana menüye yönlendiriyorum."},"disable_inactivity_monitor":True,"pre_actions":nodes["start"]["pre_actions"],"transitions":[g.always("bye")]}
wid=freya.create_workflow("final-probe-end"+mode+str(time.time()),{"initial_node":"start","system_prompt":"x","nodes":nodes})["workflow_id"]
t=time.time()
try: print(mode, freya.api("POST","/api/v2/chat/message",{"workflowId":wid,"message":"Merhaba","customerVariables":{}}))
except Exception as ex: print(mode,"ERR",str(ex)[:80])
print(mode, round(time.time()-t,1))
