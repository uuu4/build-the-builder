"""Checks before the hidden-run submission. Nothing here changes a file.

    python3 tools/preflight.py                                  this machine, tests, secret scan, git state
    python3 tools/preflight.py --skip-env                       the same without the machine checks (a machine that only reviews)
    python3 tools/preflight.py hidden-1=ours-hidden-1 hidden-2=ours-hidden-2
                                                                 also the submitted workflows and traces; prints the form

`name=slot`: `name` is the key in the submission form (hidden-1), `slot` the slot build.py used (its default is
ours-<brief file name>). Exit code 0 when every check passes; WARN lines (the practice bank cannot be reached) do not
fail it but matter: the builder's own tests will be unavailable.
"""
import glob
import importlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", "results", ".claude/jobs"}
KEY_RE = re.compile(r"fak_[A-Za-z0-9]{16,}")
BANK_HOST = os.environ.get("FREYA_BANK_HOST", "https://freya-bank-mock.freyavoice.workers.dev")
problems, notes = [], []


def sh(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def ok(msg):
    print("  ok   " + msg)


def bad(msg):
    problems.append(msg)
    print("  FAIL " + msg)


def warn(msg):
    notes.append(msg)
    print("  WARN " + msg)


def check_python(version=None):
    v = version or sys.version_info[:2]
    (ok if tuple(v) >= (3, 10) else bad)(f"Python {v[0]}.{v[1]} (3.10 or newer)")


def check_sdk(import_fn=importlib.import_module):
    """The builder's agent runs on the Claude Agent SDK. Without it build.py ends in a second with 'no workflow to submit'."""
    try:
        import_fn("claude_agent_sdk")
        ok("claude_agent_sdk is installed")
    except ImportError:
        bad("claude_agent_sdk is not installed: pip install claude-agent-sdk (build.py would end at once with 'no workflow to submit')")


def check_keys(env=os.environ, which=shutil.which):
    for name in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY"):
        (ok if env.get(name) else bad)(f"{name} is set" if env.get(name) else f"{name} is not set (source env.sh)")
    if env.get("ANTHROPIC_API_KEY"):
        ok("ANTHROPIC_API_KEY is set")
    elif which("claude"):
        ok("claude CLI found (the SDK uses its login; make sure you are logged in)")
    else:
        bad("no ANTHROPIC_API_KEY and no claude CLI: the builder's agent cannot call a model")


def reachable(url, headers=None, timeout=12):
    """True when the host answers (any HTTP status), False when the connection fails or is reset."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (build-the-builder preflight)"})
    try:
        urllib.request.urlopen(req, timeout=timeout)
        return True, ""
    except urllib.error.HTTPError:
        return True, ""
    except Exception as e:                                          # URLError, reset, timeout
        return False, f"{type(e).__name__}: {e}"


def check_network(env=os.environ, probe=reachable):
    url = env.get("FREYA_API_URL", "https://staging-app.freyavoice.ai")
    up, why = probe(url)
    (ok if up else bad)(f"Freya platform reachable ({url})" if up else f"Freya platform not reachable ({why})")
    up, why = probe(BANK_HOST)
    if up:
        ok(f"practice bank reachable ({BANK_HOST})")
    else:
        warn(f"practice bank NOT reachable ({why}). The builder still runs, but its own tests end as TEST_UNAVAILABLE. "
             "Some networks cut *.workers.dev: use a VPN or another machine.")


def environment():
    print("0. this machine (where the builder will run)")
    check_python()
    check_sdk()
    check_keys()
    check_network()


def tests():
    print("1. unit tests, including the no-leak test")
    r = sh(sys.executable, "-m", "unittest", "discover", "-s", "builder/tests", "-t", ".")
    last = [x for x in r.stderr.strip().splitlines() if x][-1:] or [""]
    (ok if r.returncode == 0 else bad)(f"{last[0]}")


def secrets():
    print("2. keys in files that could be committed")
    values = [os.environ.get(k, "") for k in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY")]
    values = [v for v in values if len(v) >= 8]
    hits = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if p.is_dir() or any(part in SKIP_DIRS for part in rel.parts) or rel.name in ("env.sh", ".env", ".freya-agents.json"):
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if KEY_RE.search(text) or any(v in text for v in values):
            hits.append(str(rel))
    (bad if hits else ok)("found in " + ", ".join(hits) if hits else "no key found in any file")
    ig = sh("git", "check-ignore", "env.sh").returncode == 0
    (ok if ig else bad)("env.sh is ignored by git")


def git_state():
    print("3. git")
    head = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()
    dirty = sh("git", "status", "--porcelain").stdout.strip().splitlines()
    tracked = [x for x in dirty if not x.startswith("??")]
    (ok if not tracked else bad)(f"HEAD {head}; " + ("no uncommitted change to tracked files" if not tracked else f"{len(tracked)} tracked file(s) changed, commit them"))
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    ahead = sh("git", "rev-list", "--count", f"origin/{branch}..HEAD").stdout.strip()
    (ok if ahead == "0" else bad)(f"branch {branch}: " + ("everything is pushed" if ahead == "0" else f"{ahead} commit(s) not pushed (or no remote branch)"))
    return head


def submission(name, slot):
    print(f"4. {name} (slot {slot})")
    sub = ROOT / "submission" / f"{slot}.workflow.json"
    out = {}
    try:
        wf = json.loads(sub.read_text())
        wf = wf.get("workflow", wf)
        nodes = wf.get("nodes") or {}
        (ok if nodes else bad)(f"{sub.relative_to(ROOT)}: {len(nodes)} nodes")
        init = wf.get("initial_node")
        (ok if init in nodes else bad)(f"initial_node {init!r} is a node")      # an export carries the platform's own agent_config: that is normal
        out["workflow"] = f"submission/{slot}.workflow.json"
    except (OSError, ValueError) as e:
        bad(f"{sub.relative_to(ROOT)} cannot be read: {e}")
    logs = sorted(glob.glob(str(ROOT / "traces" / f"{slot}-*.log")))
    if not logs:
        bad(f"no traces/{slot}-*.log")
        return out
    log = pathlib.Path(logs[-1])
    text = log.read_text()
    first = text.splitlines()[0] if text else ""
    needs = [("start and end time", "start" in first and "end" in first), ("model calls with a purpose", "model call" in text),
             ("what was created (workflow id, agent id)", "workflow_id" in text and "agent_id" in text),
             ("a test it ran, or the line saying none was available", bool(re.search(r"test|TEST_UNAVAILABLE|budget_stop", text)))]
    for label, good in needs:
        (ok if good else bad)(f"{log.name}: {label}" if good else f"{log.name} lacks: {label}")
    if len(logs) > 1:
        notes.append(f"{name}: {len(logs)} traces for slot {slot}; the form must name the one of the run that made the submitted workflow ({log.name} is the newest)")
    out["trace"] = f"traces/{log.name}"
    m = re.search(r"build trace\s+start (\S+)\s+end (\S+)", first)
    if m:
        print(f"       build time {m.group(1)} -> {m.group(2)}")
    return out


def main(argv):
    pairs = [a.split("=", 1) for a in argv if "=" in a and not a.startswith("--")]
    print("preflight (changes nothing)")
    if "--skip-env" not in argv:
        environment()
    tests()
    secrets()
    head = git_state()
    form = {"team": "<team name>", "repo": sh("git", "remote", "get-url", "origin").stdout.strip().removesuffix(".git"), "commit": head,
            "run_command": "python3 builder/build.py {brief_path} {tool_api_path}", "workflows": {}, "traces": {}}
    for name, slot in pairs:
        r = submission(name, slot)
        if "workflow" in r:
            form["workflows"][name] = r["workflow"]
        if "trace" in r:
            form["traces"][name] = r["trace"]
    for n in notes:
        print("  note " + n)
    if pairs:
        print("\nsubmission form (check the team name; send it before the deadline):")
        print(json.dumps(form, indent=2))
    print("\n" + ("ALL CHECKS PASSED" if not problems else f"{len(problems)} PROBLEM(S): " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
