"""Re-score a run of our own practice brief (practice/brief-r) whose close codes the practice bank does not know.

The practice bank checks `close_call` against the public briefs' code list and rejects other codes (Brief R uses
cb_booked, restructure, ...), so its ledger has no outcome for those calls. Here the outcome and reason are taken from
the arguments the agent sent to `close_call`; every other ledger check and the judge's verdict are kept as they were.

    python3 tools/rescore_close.py results/<run>.json practice/brief-r/cases.json
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from score import http, score_ledger  # noqa: E402


def with_close_args(led):
    """The ledger with outcome/reason from the last close_call's arguments when the bank rejected that call."""
    led = dict(led)
    closes = [c for c in led.get("calls", []) if c["tool"] == "close_call"]
    if closes and not (closes[-1].get("result") or {}).get("ok"):
        a = closes[-1].get("args") or {}
        led["outcome"], led["reason"] = a.get("outcome"), a.get("reason")
    return led


def rescore(run, cases):
    by_id = {c["id"]: c for c in cases}
    ran = {r["id"] for r in run["all_rows"][0]}
    cases = [c for c in cases if c["id"] in ran]          # a run with --only holds some of the cases
    finals = []
    for k, c in enumerate(cases):
        passes = 0
        for rows in run["all_rows"]:
            row = next(r for r in rows if r["id"] == c["id"])
            led = with_close_args(http("/v1/practice/ledger/" + row["customer_id"]))
            r = score_ledger(by_id[c["id"]], led)
            judge = [f for f in row["failed"] if f.startswith("conversation:")]
            ok = r["pass"] and not judge
            passes += ok
            if not ok:
                print("FAIL", c["id"], "|", "; ".join((r["failed"] + judge))[:400])
        finals.append((c["id"], passes, len(run["all_rows"])))
    n = sum(p == t for _, p, t in finals)
    for i, p, t in finals:
        print(("PASS" if p == t else "FAIL"), i, f"{p}/{t}")
    print(f"\n{n} / {len(finals)} passed with close_call arguments as the outcome")
    return n, finals


if __name__ == "__main__":
    rescore(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))
