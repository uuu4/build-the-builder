"""Validate, save and export a workflow on Freya. Uses the kit's freya.py client."""
import json, pathlib, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402


RETRIES = 4          # one call can meet a 502 or a reset while the platform is struggling; a lost save is a lost brief
WAIT_S = 8


def _retry(fn, *args, wait=None, **kw):
    """Call fn, repeat on a network or server error (not on a rejection of the workflow). Waits 8, 16, 24 s."""
    wait = WAIT_S if wait is None else wait
    for i in range(RETRIES):
        try:
            return fn(*args, **kw)
        except Exception as e:                                   # urllib errors, timeouts and RuntimeError from freya.api
            m = re.search(r"-> (\d{3}):", str(e))
            rejected = bool(m) and m.group(1)[0] == "4" and m.group(1) != "429"      # the platform said no; asking again changes nothing
            if rejected or i == RETRIES - 1:
                raise
            time.sleep(wait * (i + 1))


def deploy(slot, wf, export_to=None):
    """dryRun first, then create-or-update and publish under `slot`. Returns {workflow_id, agent_id, version?}.

    Every platform call is repeated on a transient error. If the export from the platform fails, the workflow we
    sent is written to `export_to` instead, so a submission file exists whatever the platform did."""
    _retry(freya.validate_workflow, slot, wf)
    out = _retry(freya.save_workflow, slot, wf, state_file=str(ROOT / ".freya-agents.json"))
    if export_to:
        pathlib.Path(export_to).parent.mkdir(parents=True, exist_ok=True)
        try:
            _retry(freya.export_workflow, out["workflow_id"], str(export_to))
        except Exception as e:
            pathlib.Path(export_to).write_text(json.dumps({"workflow": wf}, indent=1))
            out["export"] = f"platform export failed ({type(e).__name__}); wrote the workflow we sent"
    return out


def chat(workflow_id, messages, variables):
    """Talk to the published workflow turn by turn. Returns [(user, agent), ...] and the call id."""
    turns, call_id = [], None
    for m in messages:
        body = {"workflowId": workflow_id, "message": m, "customerVariables": variables}
        if call_id:
            body["callId"] = call_id
        r = freya.api("POST", "/api/v2/chat/message", body)
        call_id = r.get("callId") or call_id
        turns.append((m, r.get("response")))
    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except RuntimeError:
            pass
    return turns, call_id
