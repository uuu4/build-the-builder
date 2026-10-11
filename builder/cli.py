"""Code tools the build agent calls with Bash. Inputs and outputs are files; stdout is a short summary.

    python3 -m builder.cli spec-doc                       print the front spec format
    python3 -m builder.cli lint <workflow.json>           local checks, exit 1 on a problem
    python3 -m builder.cli deploy <slot> <workflow.json>  lint + dry run + save + publish, writes out/<slot>/deployed.json
    python3 -m builder.cli test <slot> [--brief A] [--only ID,..] [--style S] [--reps N]   practice customers, refuses near the deadline
    python3 -m builder.cli chat <slot> <lines.json>       replay a customer's lines over chat (a case with no practice customers)
    python3 -m builder.cli event <kind> <message>         a line in the build trace
"""
import json, os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.kit.openapi import Api  # noqa: E402
from builder.kit.lint import lint  # noqa: E402

TOOL_API = os.environ.get("TOOL_API", str(ROOT / "tools/openapi.json"))
TEST_MINUTES = 12            # a ten-customer run takes up to 11 minutes


def event(kind, **data):
    """Append one line to the build trace, if build.py opened one."""
    path = os.environ.get("TRACE_PATH")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": "event", "kind": kind, **data}) + "\n")


def minutes_left():
    d = os.environ.get("BUILD_DEADLINE")
    return (float(d) - time.time()) / 60 if d else 1e9


def cmd_lint(path):
    errs = lint(json.load(open(path)), Api(TOOL_API))
    print("\n".join(errs) if errs else "lint: clean")
    event("lint", file=path, problems=len(errs))
    return 1 if errs else 0


def cmd_deploy(slot, path):
    wf = json.load(open(path))
    errs = lint(wf, Api(TOOL_API))
    if errs:
        print("not deployed, lint:\n" + "\n".join(errs)); event("deploy_refused", problems=errs[:20]); return 1
    from builder.kit.deploy import deploy
    d = deploy(slot, wf)
    if d.get("version") is None:      # a new workflow: the second save sets the model and publishes
        d = deploy(slot, wf)
    d["nodes"] = len(wf["nodes"]); d["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = ROOT / "out" / slot / "deployed.json"; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(d, indent=1))
    print(json.dumps(d)); event("created", slot=slot, **d)
    return 0


INFRA_WORDS = ("URLError", "ConnectionReset", "Connection reset", "timed out", "TimeoutExpired", "Temporary failure", "Name or service not known",
               "-> 502", "-> 503", "-> 504", "SSLError", "RemoteDisconnected", "Connection refused", "IncompleteRead")


def cmd_test(slot, args):
    """Run the practice customers. If the platform or the bank cannot be reached, say so in words the build agent cannot
    misread as a failing workflow: exit 3 and TEST_UNAVAILABLE (nothing is wrong with the workflow)."""
    left = minutes_left()
    if left < TEST_MINUTES:
        print(f"not run: {left:.0f} minutes left in the build, a test needs {TEST_MINUTES}"); event("budget_stop", minutes_left=round(left)); return 1
    d = json.load(open(ROOT / "out" / slot / "deployed.json"))
    out = ROOT / "out" / slot / f"test-{time.strftime('%H%M%S')}.json"
    cmd = [sys.executable, str(ROOT / "tools/run_cases.py"), d["agent_id"], "--out", str(out)] + args
    text, r = "", None
    for attempt in range(2):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=max(60, (minutes_left() - 1) * 60))
            text = r.stdout[-6000:] + r.stderr[-2000:]
        except subprocess.TimeoutExpired:
            text = "TimeoutExpired: the test did not finish in the time left"
        if out.exists():
            break
        if attempt == 0 and any(w in text for w in INFRA_WORDS) and minutes_left() > TEST_MINUTES + 2:
            print("the test could not reach the platform or the bank; trying once more in 30 s")
            time.sleep(30)
            continue
        break
    if not out.exists():
        infra = any(w in text for w in INFRA_WORDS)
        print(text[-1500:])
        if infra:
            print("TEST_UNAVAILABLE: the platform or the bank could not be reached. This says nothing about the workflow: do not change it because of this. "
                  "The deployed workflow stands. Do not start more tests; finish with your one-line report.")
            event("test_unavailable", slot=slot, args=args, error=text[-300:])
            return 3
        print("the test did not produce a result file (a problem in the test command, not in the workflow)")
        event("test", slot=slot, args=args, error=text[-300:])
        return 1
    print(text)
    try:
        res = json.load(open(out)); event("test", slot=slot, args=args, passed=res["passed"], total=res["total"], failed=[f["id"] for f in res["final"] if not f["pass"]])
    except Exception as e:
        event("test", slot=slot, args=args, error=str(e)[:300])
    return r.returncode if r is not None else 1


def cmd_chat(slot, path):
    """Replay a customer's lines against the deployed workflow, one chat turn each (no simulation, no queue). The file is JSON:
    {"variables": {...}, "lines": ["...", ...]}; variables default to the workflow's test_variables. Prints both sides."""
    sys.path.insert(0, str(ROOT))
    import freya
    d = json.load(open(ROOT / "out" / slot / "deployed.json"))
    spec = json.load(open(path))
    wf = ROOT / "out" / slot / "workflow.json"
    v = spec.get("variables") or (json.load(open(wf)).get("test_variables") if wf.exists() else {}) or {}
    call, said = None, []
    try:
        for line in spec["lines"]:
            body = {"workflowId": d["workflow_id"], "message": line, "customerVariables": v}
            if call:
                body["callId"] = call
            r = freya.api("POST", "/api/v2/chat/message", body); r = r.get("result", r); call = call or r.get("callId")
            said.append(r.get("response") or "")
            print(f"CUSTOMER: {line}\nAGENT:    {said[-1]}\n")
    except Exception as e:
        print("chat failed:", e)
    finally:
        if call:
            try:
                freya.api("POST", "/api/v2/chat/end", {"callId": call})
            except Exception:
                pass
    event("test", test=f"chat replay {pathlib.Path(path).name}", turns=len(said), agent_said=[s[:120] for s in said][:6], call_id=call)
    return 0 if said and all(said) else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    c, rest = argv[0], argv[1:]
    if c == "spec-doc":
        from builder.kit.front import SPEC_DOC; print(SPEC_DOC); return 0
    if c == "lint":
        return cmd_lint(rest[0])
    if c == "deploy":
        return cmd_deploy(rest[0], rest[1])
    if c == "test":
        return cmd_test(rest[0], rest[1:])
    if c == "chat":
        return cmd_chat(rest[0], rest[1])
    if c == "event":
        event(rest[0], msg=" ".join(rest[1:])); return 0
    print("unknown command " + c); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
