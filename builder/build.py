"""Our builder. One command, brief files in, a Freya phone agent out.

    python3 builder/build.py <brief> [<brief> ...] [--tools tools/openapi.json] [--slot NAME] [--minutes 30]
    python3 builder/build.py <brief> <tool api .json>      the organisers' form: a positional OpenAPI file is the tool API

Three layers:
1. this file: the clock, the trace, and the close. Whatever the agent does, it ends with a linted, saved and exported workflow.
2. a Claude agent (Claude Agent SDK) with the `collections-builder` skill: reads the brief, writes the specs and the generator.
3. code tools (`python3 -m builder.cli ...`, `builder/kit`): everything that must not go wrong.

Writes out/<slot>/..., submission/<slot>.workflow.json and traces/<slot>-<time>.jsonl + .log.
Needs FREYA_API_KEY, FREYA_BANK_TEAM_KEY and a Claude login or ANTHROPIC_API_KEY.
"""
import argparse, asyncio, dataclasses, json, os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
CLOSE_MINUTES = 8            # kept for the close: lint, save, export, trace (rehearsal of 11 October: 7 min on a slow platform)
RETRY_MINUTES = 10           # an agent that crashed or left no workflow is started once more if this much time is left
FALLBACK = ROOT / "examples" / "base-agent.json"     # the kit's base agent: submitted only when nothing else exists


def is_openapi(path):
    """True for an OpenAPI file (JSON with "openapi" and "paths"). The organisers' form passes the tool API positionally."""
    try:
        d = json.load(open(path))
        return isinstance(d, dict) and "openapi" in d and "paths" in d
    except Exception:
        return False


def split_inputs(paths, tools_flag):
    """Brief files and the tool API file from the command line. An explicit --tools wins; otherwise the last positional
    OpenAPI file is the tool API. Every other positional file is a brief, in order."""
    briefs = [p for p in paths if not is_openapi(p)]
    apis = [p for p in paths if is_openapi(p)]
    tools = tools_flag or (apis[-1] if apis else str(ROOT / "tools/openapi.json"))
    return briefs, tools


def log(trace, entry_type, **data):
    with open(trace, "a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": entry_type, **data}, default=str) + "\n")


def prompt_for(briefs, tool_api, slot, deadline, again=False):
    return (("A first build attempt stopped early. Files it left in out/" + slot + "/ may be used if they are complete; "
             "check them before you rely on them.\n") if again else "") + (f"Use the collections-builder skill to build the phone agent.\n"
            f"Brief files, in order (a later file can change an earlier one): {', '.join(briefs)}\n"
            f"Tool API file: {tool_api}\nSlot: {slot}  (write everything to out/{slot}/)\n"
            f"Hard deadline: {time.strftime('%H:%M:%S', time.localtime(deadline))} local time "
            f"({(deadline - time.time()) / 60:.0f} minutes from now). Have a deployed workflow well before it.")


async def run_agent(briefs, tool_api, slot, deadline, trace, again=False):
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query
    options = ClaudeAgentOptions(
        cwd=ROOT, model=MODEL, skills=["collections-builder"], setting_sources=["project"],
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"], permission_mode="dontAsk", max_turns=200,
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
             "TRACE_PATH": str(trace), "BUILD_DEADLINE": str(deadline), "TOOL_API": tool_api})
    async for m in query(prompt=prompt_for(briefs, tool_api, slot, deadline, again), options=options):
        log(trace, type(m).__name__, **dataclasses.asdict(m))
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    print(b.text, flush=True)
                elif isinstance(b, ToolUseBlock):
                    print(f"  [{b.name}] {str(b.input)[:140]}", flush=True)
        elif isinstance(m, ResultMessage):
            print(f"agent done: {m.num_turns} turns, {m.duration_ms / 1000:.0f} s, ${m.total_cost_usd or 0:.2f}", flush=True)


def regenerate(slot, trace):
    """out/<slot>/workflow.json, generated from out/<slot>/gen.py when the agent wrote the generator but did not run it."""
    wf_path = ROOT / "out" / slot / "workflow.json"
    gen = ROOT / "out" / slot / "gen.py"
    if not wf_path.exists() and gen.exists():
        try:
            r = subprocess.run([sys.executable, str(gen)], cwd=ROOT, capture_output=True, text=True, timeout=120)
            log(trace, "event", kind="close_regenerate", rc=r.returncode, err=r.stderr[-500:])
        except Exception as e:
            log(trace, "event", kind="close_regenerate", rc=None, err=repr(e)[:500])
    return wf_path


def close(slot, trace):
    """Lint, save and export whatever valid workflow the agent left. Never raises."""
    from builder.kit.lint import lint
    from builder.kit.openapi import Api
    from builder.kit.deploy import deploy
    wf_path = regenerate(slot, trace)
    if wf_path.exists():
        wf = json.load(open(wf_path))
    elif FALLBACK.exists():          # far below a built agent, but a submission scores more than none
        wf = json.load(open(FALLBACK))
        log(trace, "event", kind="close_fallback", msg="no workflow.json: submitting the kit's base agent " + str(FALLBACK.relative_to(ROOT)))
        print("no workflow from the agent: submitting the fallback base agent")
    else:
        log(trace, "event", kind="close_failed", msg="no workflow.json"); print("no workflow to submit"); return None
    errs = lint(wf, Api(os.environ.get("TOOL_API", str(ROOT / "tools/openapi.json"))))
    if errs:
        log(trace, "event", kind="close_lint", problems=errs[:30]); print("lint problems at close:\n" + "\n".join(errs))
    sub = ROOT / "submission" / f"{slot}.workflow.json"
    try:
        d = deploy(slot, wf, export_to=sub)
        if d.get("version") is None:
            d = deploy(slot, wf, export_to=sub)
        log(trace, "event", kind="created", slot=slot, submission=str(sub), **d); print(f"submitted {sub}: {d}")
        return d
    except Exception as e:
        log(trace, "event", kind="close_failed", msg=str(e)[:800]); print("save failed:", e)
        # 11 October rehearsal: the close's save answered 504 four times and no submission file was written, although
        # the agent had saved this workflow minutes before. The workflow is the submission: write it from disk.
        try:
            ids = json.load(open(ROOT / "out" / slot / "deployed.json")) if (ROOT / "out" / slot / "deployed.json").exists() else {}
            sub.parent.mkdir(parents=True, exist_ok=True)
            sub.write_text(json.dumps({"workflow_id": ids.get("workflow_id"), "agent_id": ids.get("agent_id"), "workflow": wf}, indent=1))
            log(trace, "event", kind="close_fallback_file", submission=str(sub), workflow_id=ids.get("workflow_id"), agent_id=ids.get("agent_id"),
                msg="platform save failed at the close; submission written from out/<slot>/workflow.json (the agent's last deploy)")
            print(f"submission written from disk: {sub}")
        except Exception as e2:
            log(trace, "event", kind="close_failed", msg="writing the submission from disk failed: " + repr(e2)[:400])
        return None


def summary(trace, out):
    """The plain-text trace the rules ask for: times, model calls with a purpose, what was created, tests run."""
    lines, start, end, calls = [], None, None, 0
    for raw in open(trace):
        e = json.loads(raw)
        start = start or e["t"]; end = e["t"]
        if e["type"] == "start":
            lines.append(f"start {e['t']}  briefs {', '.join(e['briefs'])}  tool api {e['tool_api']}  builder model {e['model']}")
        elif e["type"] == "AssistantMessage":
            calls += 1
            what = [c.get("text", "")[:100].replace("\n", " ") for c in e.get("content", []) if c.get("text")] or \
                   [f"{c.get('name')}: {str(c.get('input'))[:100]}" for c in e.get("content", []) if c.get("name")]
            lines.append(f"{e['t']} model call {calls} ({e.get('model') or 'builder model'}): {(what or ['(no text)'])[0]}")
        elif e["type"] == "event":
            lines.append(f"{e['t']} {e['kind']}: " + json.dumps({k: v for k, v in e.items() if k not in ('t', 'type', 'kind')})[:400])
        elif e["type"] == "ResultMessage":
            lines.append(f"{e['t']} agent finished: {e.get('num_turns')} turns, cost ${e.get('total_cost_usd') or 0:.2f}")
    lines.insert(0, f"build trace  start {start}  end {end}  model calls {calls}")
    pathlib.Path(out).write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("briefs", nargs="+")
    ap.add_argument("--tools")
    ap.add_argument("--slot")
    ap.add_argument("--minutes", type=float, default=30)
    a = ap.parse_args()
    a.briefs, a.tools = split_inputs(a.briefs, a.tools)
    if not a.briefs:
        ap.error("no brief file (every positional file is an OpenAPI file)")
    t0 = time.time()
    deadline = t0 + a.minutes * 60
    slot = a.slot or "ours-" + pathlib.Path(a.briefs[-1]).stem      # never the slot of another builder
    os.environ["TOOL_API"] = str(pathlib.Path(a.tools).resolve())
    (ROOT / "traces").mkdir(exist_ok=True)
    trace = ROOT / "traces" / f"{slot}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    os.environ["TRACE_PATH"] = str(trace)
    log(trace, "start", briefs=a.briefs, tool_api=os.environ["TOOL_API"], model=MODEL, slot=slot, deadline=deadline)
    for attempt in (1, 2):
        try:
            asyncio.run(asyncio.wait_for(run_agent(a.briefs, os.environ["TOOL_API"], slot, deadline - CLOSE_MINUTES * 60, trace, again=attempt > 1),
                                         timeout=max(60, deadline - CLOSE_MINUTES * 60 - time.time())))
        except asyncio.TimeoutError:
            log(trace, "event", kind="budget_stop", msg="agent stopped at its deadline"); print("agent stopped at its deadline")
            break
        except Exception as e:
            log(trace, "event", kind="agent_error", attempt=attempt, msg=repr(e)[:800]); print("agent error:", e)
        left = (deadline - CLOSE_MINUTES * 60 - time.time()) / 60
        if regenerate(slot, trace).exists() or attempt == 2 or left < RETRY_MINUTES:
            break
        log(trace, "event", kind="agent_retry", minutes_left=round(left), msg="no workflow.json after the agent: starting it once more")
        print(f"no workflow after the agent, {left:.0f} minutes left: starting it once more")
    close(slot, trace)
    log(trace, "end", seconds=round(time.time() - t0))
    summary(trace, str(trace).replace(".jsonl", ".log"))
    print(f"done in {time.time() - t0:.0f} s. Trace: {trace}")


if __name__ == "__main__":
    main()
