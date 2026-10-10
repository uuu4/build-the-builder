"""Validate, save and export a workflow on Freya. Uses the kit's freya.py client."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402


def deploy(slot, wf, export_to=None):
    """dryRun first, then create-or-update and publish under `slot`. Returns {workflow_id, agent_id, version?}."""
    freya.validate_workflow(slot, wf)
    out = freya.save_workflow(slot, wf, state_file=str(ROOT / ".freya-agents.json"))
    if export_to:
        pathlib.Path(export_to).parent.mkdir(parents=True, exist_ok=True)
        freya.export_workflow(out["workflow_id"], str(export_to))
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
