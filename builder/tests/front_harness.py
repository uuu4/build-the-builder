"""Build only the front of the call (who answered + identity) on Freya and check it on the practice customers.

    python3 -m builder.tests.front_harness [--style talkative] [--no-run]

After a verified identity a stub reads the account and closes. So only the front is judged here:
the right path (identity, third party, failure) and the right number of verify calls.
"""
import argparse, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from builder.kit import front, graph as g  # noqa: E402
from builder.kit.openapi import Api  # noqa: E402
from builder.kit.lint import lint  # noqa: E402

# what the front must do for each practice customer (test data, not builder knowledge)
EXPECT = {"PUB-02": ("callback", 0), "PUB-03": ("failed", 3), "PUB-12": ("verified", 3)}


def workflow(spec_path):
    api = Api(ROOT / "tools/openapi.json")
    spec = json.load(open(spec_path))
    nodes = front.build(api, spec, after_verify="stub_account")
    nodes["stub_account"] = g.api_request("stub_account", api.pre_action("get_account", {}), "stub_close")
    nodes["stub_close"] = g.close(api, "stub_close", "no_promise", "refused", "Thank you, that is all for today. Goodbye.")
    wf = {"initial_node": "setup", "system_prompt": "You are the digital assistant of " + spec["bank"] + ", on an outbound phone call. Speak English. "
          "One or two short sentences per turn. Address the customer as {{title}} {{last_name}}. After every tool result, speak or call the next tool; never leave a turn empty. "
          "Do not say goodbye yourself; the system says it.", "nodes": nodes, "global_nodes": {}}
    return api, wf


def judge(rows):
    from score import http
    good = 0
    for r in rows:
        led = http("/v1/practice/ledger/" + r["customer_id"])
        tools = [c["tool"] for c in led["calls"]]
        closes = [c for c in led["calls"] if c["tool"] == "close_call"]
        out = (closes[-1].get("args") or closes[-1].get("body") or {}) if closes else {}
        want, nver = EXPECT.get(r["id"], ("verified", 2))
        v = tools.count("verify_identity")
        if want == "verified":
            ok = "get_account" in tools and v == nver
        elif want == "failed":
            ok = "get_account" not in tools and v == nver and "failed" in json.dumps(out)
        else:
            ok = "schedule_callback" in tools and "verify_identity" not in tools and "callback" in json.dumps(out)
        good += ok
        print("OK  " if ok else "BAD ", r["id"], f"{r.get('style') or '':<10}", " > ".join(tools), "|", json.dumps(out)[:90])
    print(f"\nfront correct: {good} / {len(rows)}")
    return good


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--spec", default=str(ROOT / "builder/tests/fixtures/front-brief-a.json"))
    ap.add_argument("--style"); ap.add_argument("--no-run", action="store_true"); ap.add_argument("--only")
    a = ap.parse_args()
    api, wf = workflow(a.spec)
    errs = lint(wf, api)
    if errs:
        sys.exit("lint:\n" + "\n".join(errs))
    from builder.kit.deploy import deploy
    d = deploy("front-test", wf)
    print("deployed", d)
    if a.no_run:
        return
    out = ROOT / "results" / f"front-{a.style or 'plain'}.json"
    cmd = [sys.executable, str(ROOT / "tools/run_cases.py"), d["agent_id"], "--out", str(out)] + (["--style", a.style] if a.style else []) + (["--only", a.only] if a.only else [])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    rows = json.load(open(out))["rows"]
    for r in rows:
        r["style"] = a.style
    judge(rows)


if __name__ == "__main__":
    main()
