"""Thin client for the Freya API. Standard library only.

    export FREYA_API_KEY=fak_...            # your workspace key
    export FREYA_API_URL=https://staging-app.freyavoice.ai   # default
"""
import json, os, time, urllib.request, urllib.error, urllib.parse

URL = os.environ.get("FREYA_API_URL", "https://staging-app.freyavoice.ai")
# Cloudflare rejects requests without a browser-like User-Agent (error 1010).
HEADERS = {"Authorization": "Bearer " + os.environ.get("FREYA_API_KEY", ""), "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (build-the-builder)"}

def api(method, path, body=None, **params):
    """Call the API and return the `result` part of its {success, data: {message, result}} envelope."""
    q = "?" + urllib.parse.urlencode(params) if params else ""
    # 5xx and timeouts are retried: 3 tries, 10 s apart (11 October: 503 "API key validation is temporarily unavailable",
    # 504 on GET, 30 s answers). A POST is retried only on 502/503, where nothing was processed; a 504 may have been.
    for attempt in range(3):
        req = urllib.request.Request(URL + path + q, data=json.dumps(body).encode() if body is not None else None, headers=HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r: out = json.load(r)     # 60, not 120: with the retries a slow GET cost minutes at the build's close
            break
        except urllib.error.HTTPError as e:
            msg = f"{method} {path} -> {e.code}: {e.read().decode()[:1500]}"
            if attempt < 2 and (e.code in (502, 503) or (e.code == 504 and method == "GET")):
                time.sleep(10); continue
            raise RuntimeError(msg) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < 2 and method == "GET":
                time.sleep(10); continue
            raise RuntimeError(f"{method} {path} -> {e}") from None
    return out.get("data", {}).get("result", out) if isinstance(out, dict) else out

_ws = None
def workspace_id():
    """The workspace your key belongs to. List routes need it as a query parameter."""
    global _ws
    if not _ws:
        r = api("GET", "/api/v2/workspaces"); items = r.get("workspaces") or r.get("items") or r
        _ws = os.environ.get("FREYA_WORKSPACE_ID") or items[0]["id"]
    return _ws

def create_workflow(name, workflow):
    """Create a workflow. Freya creates its agent with it. Returns {workflow_id, agent_id}."""
    w = api("POST", "/api/v2/workflow", {"name": name, "workflow": workflow})["workflow"]
    return {"workflow_id": w["id"], "agent_id": w["agentId"]}

def save_workflow(slot, workflow, state_file=".freya-agents.json"):
    """Create the workflow the first time, update the same one afterwards. Use this in your builder.

    `slot` is your own label, for example the brief's file name. A workspace holds a limited number of workflows,
    so a builder that creates a new one on every run stops working after a few runs."""
    import pathlib
    f = pathlib.Path(state_file); state = json.loads(f.read_text()) if f.exists() else {}
    if slot in state:
        state[slot]["version"] = update_workflow(state[slot]["workflow_id"], workflow); f.write_text(json.dumps(state, indent=1))
    else:
        state[slot] = create_workflow(f"{slot} {time.strftime('%m%d-%H%M%S')}", workflow); f.write_text(json.dumps(state, indent=1))
    return state[slot]
def validate_workflow(name, workflow): return api("POST", "/api/v2/workflow", {"name": name, "workflow": workflow}, dryRun="true")
def update_workflow(workflow_id, workflow):
    """Update a workflow and publish the new version. Returns the published version number.

    An update alone only saves a new, unpublished version. Simulations and calls keep running the published one,
    so an update that is not published tests your old phone agent."""
    api("PUT", f"/api/v2/workflow/{workflow_id}", {"workflow": workflow})
    # The platform fills in a default agent_config. If its model is not the event's model, a simulation still runs
    # (it overrides the model), but a chat turn or a real call cannot start. Set the model and save once more.
    w = api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=workspace_id())["workflow"]["workflow"]
    ac = w.get("agent_config") or {}; llm = ac.get("llmConfig") or {}
    if (llm.get("provider"), llm.get("model")) != (AGENT_LLM["provider"], AGENT_LLM["model"]):
        ac["llmConfig"] = {**llm, **AGENT_LLM}; api("PUT", f"/api/v2/workflow/{workflow_id}", {"workflow": {**w, "agent_config": ac}})
    vs = api("GET", f"/api/v2/versions/workflow/{workflow_id}", workspaceId=workspace_id())["versions"]
    newest = max(vs, key=lambda v: v["versionNumber"])
    if not newest.get("isPublished"): api("POST", f"/api/v2/versions/workflow/{workflow_id}/publish", {"versionId": newest["id"]})
    return newest["versionNumber"]
def export_workflow(workflow_id, path):
    """Write the workflow as it is on the platform to a file. This file is part of what you submit."""
    w = api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=workspace_id())["workflow"]
    open(path, "w").write(json.dumps({"workflow_id": w["id"], "agent_id": w.get("agentId"), "updated_at": w.get("updatedAt"), "workflow": w["workflow"]}, indent=1)); return path
def create_personas(personas):        return api("POST", "/api/v2/personas", {"personas": personas})
def get_iteration(sim_id, it_id):
    """One iteration with ALL its runs. The route returns 30 runs by default and 100 at most, so this reads page by page."""
    out, off = None, 0
    while True:
        r = api("GET", f"/api/v2/simulations/{sim_id}/iterations/{it_id}", limit=100, offset=off)
        if out is None: out = r
        else: out["runs"] += r["runs"]
        off += 100
        if len(r["runs"]) < 100: return out
def get_call(call_id):
    """One simulated call: `messages` holds the transcript, tool calls included. Run ids and call ids come from get_iteration()['runs']."""
    return api("GET", f"/api/v2/call/{call_id}")["call"]

# The model every team's phone agent runs on: Freya's model on the event's own GPU box. Do not change it. (Organisers can point a test at another model with the two variables.)
AGENT_LLM = {"provider": os.environ.get("FREYA_AGENT_PROVIDER", "experimental-5"), "model": os.environ.get("FREYA_AGENT_MODEL", "experimental-5")}
SIM_LLM = {"provider": "google", "model": "gemini-3-flash-preview"}        # plays the customer and judges

def _newest_simulation(agent_id, name):
    """The simulation this agent started under `name`, if the platform has it (for a start that answered 504)."""
    try:
        r = api("GET", "/api/v2/simulations", limit=5); sims = r.get("simulations") or r.get("items") or r
        return next((x for x in sims if x.get("agentId") == agent_id and x.get("name") == name), None)
    except RuntimeError:
        return None

def run_simulation(agent_id, name, variables_by_persona, max_seconds=420, concurrency=int(os.environ.get("FREYA_SIM_CONCURRENCY", "5"))):
    """Start a text simulation, wait for it, return (simulation_id, iteration_id)."""
    while True:                      # a workspace runs one simulation at a time: wait for the running one instead of failing
        try:
            sim = api("POST", "/api/v2/simulations", {
                "agentId": agent_id, "name": name, "mode": "chat", "selectedPersonaIds": list(variables_by_persona),
                "customerVariablesMap": variables_by_persona, "maxConcurrentCalls": concurrency, "runsPerPersona": 1, "maxCallDurationSeconds": max_seconds,
                "assistantLlmOverride": AGENT_LLM, "routingLlmOverride": AGENT_LLM, "extractionLlmOverride": AGENT_LLM,
                "personaLlmOverride": SIM_LLM, "analysisLlmOverride": SIM_LLM})
            break
        except RuntimeError as e:
            if "-> 504" in str(e) or "timed out" in str(e):
                # 11 October: the POST answered 504 but may have started the simulation; adopt it rather than start another
                time.sleep(15)
                mine = _newest_simulation(agent_id, name)
                if mine:
                    sim = mine; print("the start answered 504 but the simulation is running: following it", flush=True); break
                print("starting the simulation failed (504), trying again in 30 s", flush=True); time.sleep(30); continue
            if "concurrent simulations" not in str(e): raise
            print("another simulation is running in this workspace, waiting 30 s", flush=True); time.sleep(30)
    sim_id = (sim.get("simulation") or sim)["id"]
    done_since = None
    while True:
        time.sleep(10)
        try:                         # a 504 on the poll does not stop the simulation on Freya; keep following it
            s = api("GET", f"/api/v2/simulations/{sim_id}"); s = s.get("simulation") or s
        except RuntimeError as e:
            print("polling the simulation failed, trying again:", str(e)[:120], flush=True); time.sleep(20); continue
        if s.get("status") in ("completed", "failed", "paused"): break
        # seen twice on 10 October: every run had its verdict but the simulation stayed "running" for an hour and
        # blocked the workspace. Two minutes after the last verdict, cancel it and read the verdicts.
        try:
            its = api("GET", f"/api/v2/simulations/{sim_id}/iterations"); its = its.get("iterations") or its.get("items") or its
            runs = get_iteration(sim_id, its[0]["id"])["runs"]
            # a verdict alone is not enough: on 11 October calls were still talking (promise, close_call to come) when
            # every run already showed an outcome, and the ledger was read too early. Every call must have ended too.
            # A call that never started (stuck "initiating", no messages) never ends: then 10 minutes after the verdicts.
            if len(runs) >= len(variables_by_persona) and all(r.get("outcome") in ("pass", "fail", "inconclusive", "error") for r in runs):
                done_since = done_since or time.time()
                ended = all(r.get("callId") and get_call(r["callId"]).get("endedAt") for r in runs)
                if (ended and time.time() - done_since > 120) or time.time() - done_since > 600:
                    api("POST", f"/api/v2/simulations/{sim_id}/cancel")
                    print("simulation kept 'running' after every verdict was in: cancelled it", flush=True)
                    s["status"] = "completed"
                    break
        except Exception:
            pass
    its = api("GET", f"/api/v2/simulations/{sim_id}/iterations"); its = its.get("iterations") or its.get("items") or its
    return sim_id, its[0]["id"], s.get("status")
