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


TEXT_TYPES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv", ".html", ".xml"}


def to_text(path):
    """The text of one document (Markdown, Word, PDF, Excel, plain). None for a type it cannot read (an image: the agent views it)."""
    p, ext = pathlib.Path(path), pathlib.Path(path).suffix.lower()
    if ext in TEXT_TYPES:
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".docx":
        import docx
        d = docx.Document(str(p))
        out = [x.text for x in d.paragraphs]
        for t in d.tables:
            out += [" | ".join(c.text.strip() for c in row.cells) for row in t.rows]
        return "\n".join(out)
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(str(p), data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"## sheet {ws.title}")
            out += ["\t".join("" if c is None else str(c) for c in row) for row in ws.iter_rows(values_only=True)]
        return "\n".join(out)
    if ext == ".pdf":
        import pypdf
        return "\n\n".join((pg.extract_text() or "") for pg in pypdf.PdfReader(str(p)).pages)
    return None


def case_inputs(folder, slot):
    """A case folder (the final's zip): every document as text under out/<slot>/case/, BRIEF and README first. Returns the text
    files (the briefs), the files left as they are (images), and an OpenAPI file if the folder has one."""
    folder, dest = pathlib.Path(folder), ROOT / "out" / slot / "case"
    dest.mkdir(parents=True, exist_ok=True)
    texts, others, api = [], [], None
    files = sorted((f for f in folder.rglob("*") if f.is_file()), key=lambda f: (f.stem.upper() not in ("BRIEF", "README"), f.stem.upper() != "BRIEF", str(f)))
    for f in files:
        if is_openapi(f):
            api = str(f)
        try:
            t = to_text(f)
        except Exception as e:
            t = f"(could not read {f.name}: {e!r}; open the original: {f})"
        if t is None:
            others.append(str(f)); continue
        out = dest / (str(f.relative_to(folder)).replace(os.sep, "__").replace("/", "__") + ".txt")
        out.write_text(f"# {f.relative_to(folder)}  (original: {f})\n\n{t}", encoding="utf-8")
        texts.append(str(out))
    return texts, others, api


def log(trace, entry_type, **data):
    with open(trace, "a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "type": entry_type, **data}, default=str) + "\n")


def case_note():
    """What the prompt adds for a case folder (the final's form): the converted documents, files left as they are, the mock."""
    x = json.loads(os.environ.get("CASE_EXTRA") or "{}")
    if not x.get("case_folders"):
        return ""
    note = (f"This is a case folder ({', '.join(x['case_folders'])}): every document was converted to text and is listed above "
            "as the brief files (BRIEF and README first). Read all of them; open an original only when its text looks broken. ")
    if x.get("other_files"):
        note += f"Files left as they are (view them with Read, a flow drawing is one): {', '.join(x['other_files'])}. "
    if x.get("mock_url"):
        note += f"The bank's services for this case run at {x['mock_url']}: every tool the phone agent calls goes to that base URL. "
    if not x.get("tool_api_exists"):
        note += ("There is no OpenAPI file: write the tool API file named above from the service contract first (OpenAPI 3, "
                 "servers url = the mock URL, one path per service, request and response fields and enums exactly as the contract says). ")
    return note + "Follow the skill's section 'A case that is not the kit's shape'.\n"


def prompt_for(briefs, tool_api, slot, deadline, again=False):
    return (("A first build attempt stopped early. Files it left in out/" + slot + "/ may be used if they are complete; "
             "check them before you rely on them.\n") if again else "") + (f"Use the collections-builder skill to build the phone agent.\n"
            f"Brief files, in order (a later file can change an earlier one): {', '.join(briefs)}\n"
            f"Tool API file: {tool_api}\nSlot: {slot}  (write everything to out/{slot}/)\n" + case_note() +
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
    api_path = os.environ.get("TOOL_API", str(ROOT / "tools/openapi.json"))
    errs = lint(wf, Api(api_path) if pathlib.Path(api_path).exists() else None)
    if errs:
        log(trace, "event", kind="close_lint", problems=errs[:30]); print("lint problems at close:\n" + "\n".join(errs))
    sub = ROOT / "submission" / f"{slot}.workflow.json"
    try:
        d = deploy(slot, wf, export_to=sub)
        if d.get("version") is None:
            d = deploy(slot, wf, export_to=sub)
        log(trace, "event", kind="created", slot=slot, submission=str(sub), **d, **shape(wf)); print(f"submitted {sub}: {d}")
        smoke(d.get("workflow_id"), wf.get("test_variables") or {}, trace)
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


SMOKE_TURNS = ("Hello?", "Yes, speaking.")


def smoke(workflow_id, variables, trace):
    """Two chat turns against the submitted workflow (the FAQ's check for a brief with no practice customers): does it
    start a call, open, and answer a yes. Only logged: nothing is changed because of it. Never raises."""
    said, call = [], None
    try:
        import freya
        for msg in SMOKE_TURNS:
            body = {"workflowId": workflow_id, "message": msg, "customerVariables": variables}
            if call:
                body["callId"] = call
            r = freya.api("POST", "/api/v2/chat/message", body)
            r = r.get("result", r)
            call = call or r.get("callId")
            said.append((r.get("response") or "").strip())
        ok = all(said)
        log(trace, "event", kind="test", test="chat smoke test (2 turns: opening, then 'Yes, speaking.')", passed=ok,
            agent_said=[s[:200] for s in said])
        print(f"chat smoke test: {'PASS' if ok else 'FAIL'}: {said}")
    except Exception as e:
        log(trace, "event", kind="test", test="chat smoke test", passed=False, agent_said=said, error=repr(e)[:300])
        print("chat smoke test: FAIL:", e)
    finally:
        if call:
            try:
                freya.api("POST", "/api/v2/chat/end", {"callId": call})
            except Exception:
                pass


def shape(wf):
    """Steps and the bank tools the workflow calls, for the trace (the rules ask for the number of steps and tools)."""
    nodes = wf.get("nodes") or {}
    tools = sorted({f["function"].get("name") for n in nodes.values() for k in ("tools", "pre_actions", "post_actions")
                    for f in n.get(k) or [] if isinstance(f, dict) and "function" in f} - {"code_exec", None})
    return {"steps": len(nodes), "tools": len(tools), "tool_names": tools}


def summary(trace, out):
    """The plain-text trace the rules ask for: times, model calls with a purpose, what was created, tests run."""
    lines, start, end, calls, seen = [], None, None, 0, {}
    for raw in open(trace):
        e = json.loads(raw)
        start = start or e["t"]; end = e["t"]
        if e["type"] == "start":
            lines.append(f"start {e['t']}  briefs {', '.join(e['briefs'])}  tool api {e['tool_api']}  builder model {e['model']}")
        elif e["type"] == "AssistantMessage":
            # The SDK splits one model response into several messages (thinking, then text or a tool use) with one message_id.
            what = [c.get("text", "")[:100].replace("\n", " ") for c in e.get("content", []) if c.get("text")] or \
                   [f"{c.get('name')}: {str(c.get('input'))[:100]}" for c in e.get("content", []) if c.get("name")]
            mid = e.get("message_id")
            if mid and mid in seen:
                i = seen[mid]
                if what and lines[i].endswith("(thinking)"):
                    lines[i] = lines[i][:-len("(thinking)")] + what[0]
                continue
            calls += 1
            if mid:
                seen[mid] = len(lines)
            lines.append(f"{e['t']} model call {calls} ({e.get('model') or 'builder model'}): {(what or ['(thinking)'])[0]}")
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
    ap.add_argument("--minutes", type=float, default=None)
    a = ap.parse_args()
    # the final's form: python3 builder/build.py {case_folder} {mock_url}
    urls = [p for p in a.briefs if p.startswith(("http://", "https://"))]
    folders = [p for p in a.briefs if p not in urls and pathlib.Path(p).is_dir()]
    a.briefs = [p for p in a.briefs if p not in urls and p not in folders]
    mock_url = urls[-1].rstrip("/") if urls else ""
    if mock_url:
        os.environ["MOCK_URL"] = mock_url
    case_slot = a.slot or ("ours-" + pathlib.Path(folders[-1]).resolve().name if folders else None)
    others = []
    for f in folders:
        texts, imgs, api = case_inputs(f, case_slot)
        a.briefs += texts; others += imgs
        a.tools = a.tools or api
    if folders and not a.tools:      # no OpenAPI file in the case: the agent writes one from the service contract
        a.tools = str(ROOT / "out" / case_slot / "tools.openapi.json")
    a.briefs, a.tools = split_inputs(a.briefs, a.tools)
    if not a.briefs:
        ap.error("no brief file (every positional file is an OpenAPI file)")
    t0 = time.time()
    deadline = t0 + (a.minutes or (60 if folders else 30)) * 60
    slot = case_slot or a.slot or "ours-" + pathlib.Path(a.briefs[-1]).stem      # never the slot of another builder
    os.environ["TOOL_API"] = str(pathlib.Path(a.tools).resolve())
    os.environ["CASE_EXTRA"] = json.dumps({"case_folders": [str(pathlib.Path(f).resolve()) for f in folders], "other_files": others, "mock_url": mock_url,
                                           "tool_api_exists": pathlib.Path(a.tools).exists()})
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
