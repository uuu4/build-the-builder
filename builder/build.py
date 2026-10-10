"""Our builder. One command, brief files in, a Freya phone agent out.

    python3 builder/build.py <brief> [<brief> ...] [--tools tools/openapi.json] [--slot NAME] [--minutes 30]

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
CLOSE_MINUTES = 4            # kept for the close: lint, save, export, trace


def log(trace, kind, **data):
    with open(trace, "a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": kind, **data}, default=str) + "\n")


def prompt_for(briefs, tool_api, slot, deadline):
    return (f"Use the collections-builder skill to build the phone agent.\n"
            f"Brief files, in order (a later file can change an earlier one): {', '.join(briefs)}\n"
            f"Tool API file: {tool_api}\nSlot: {slot}  (write everything to out/{slot}/)\n"
            f"Hard deadline: {time.strftime('%H:%M:%S', time.localtime(deadline))} local time "
            f"({(deadline - time.time()) / 60:.0f} minutes from now). Have a deployed workflow well before it.")


async def run_agent(briefs, tool_api, slot, deadline, trace):
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query
    options = ClaudeAgentOptions(
        cwd=ROOT, model=MODEL, skills=["collections-builder"], setting_sources=["project"],
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"], permission_mode="dontAsk", max_turns=200,
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
             "TRACE_PATH": str(trace), "BUILD_DEADLINE": str(deadline), "TOOL_API": tool_api})
    async for m in query(prompt=prompt_for(briefs, tool_api, slot, deadline), options=options):
        log(trace, type(m).__name__, **dataclasses.asdict(m))
        if isinstance(m, AssistantMessage):
            for b in m.content:
                if isinstance(b, TextBlock):
                    print(b.text, flush=True)
                elif isinstance(b, ToolUseBlock):
                    print(f"  [{b.name}] {str(b.input)[:140]}", flush=True)
        elif isinstance(m, ResultMessage):
            print(f"agent done: {m.num_turns} turns, {m.duration_ms / 1000:.0f} s, ${m.total_cost_usd or 0:.2f}", flush=True)


def close(slot, trace):
    """Lint, save and export whatever valid workflow the agent left. Never raises."""
    from builder.kit.lint import lint
    from builder.kit.openapi import Api
    from builder.kit.deploy import deploy
    wf_path = ROOT / "out" / slot / "workflow.json"
    if not wf_path.exists():
        gen = ROOT / "out" / slot / "gen.py"
        if gen.exists():                     # the agent wrote the generator but did not get to run it
            r = subprocess.run([sys.executable, str(gen)], cwd=ROOT, capture_output=True, text=True, timeout=120)
            log(trace, "event", kind="close_regenerate", rc=r.returncode, err=r.stderr[-500:])
    if not wf_path.exists():
        log(trace, "event", kind="close_failed", msg="no workflow.json"); print("no workflow to submit"); return None
    wf = json.load(open(wf_path))
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
    ap.add_argument("--tools", default=str(ROOT / "tools/openapi.json"))
    ap.add_argument("--slot")
    ap.add_argument("--minutes", type=float, default=30)
    a = ap.parse_args()
    t0 = time.time()
    deadline = t0 + a.minutes * 60
    slot = a.slot or pathlib.Path(a.briefs[-1]).stem
    os.environ["TOOL_API"] = str(pathlib.Path(a.tools).resolve())
    (ROOT / "traces").mkdir(exist_ok=True)
    trace = ROOT / "traces" / f"{slot}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    os.environ["TRACE_PATH"] = str(trace)
    log(trace, "start", briefs=a.briefs, tool_api=os.environ["TOOL_API"], model=MODEL, slot=slot, deadline=deadline)
    try:
        asyncio.run(asyncio.wait_for(run_agent(a.briefs, os.environ["TOOL_API"], slot, deadline - CLOSE_MINUTES * 60, trace),
                                     timeout=max(60, deadline - CLOSE_MINUTES * 60 - time.time())))
    except asyncio.TimeoutError:
        log(trace, "event", kind="budget_stop", msg="agent stopped at its deadline"); print("agent stopped at its deadline")
    except Exception as e:
        log(trace, "event", kind="agent_error", msg=repr(e)[:800]); print("agent error:", e)
    close(slot, trace)
    log(trace, "end", seconds=round(time.time() - t0))
    summary(trace, str(trace).replace(".jsonl", ".log"))
    print(f"done in {time.time() - t0:.0f} s. Trace: {trace}")


if __name__ == "__main__":
    main()
