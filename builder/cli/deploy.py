"""cli deploy: lint, dry-run on Freya, save and publish, then read back what was stored.

    python3 -m builder.cli deploy out/<slot>/workflow.json --slot <slot> -o out/<slot>/deployed.json [--dry-run]

Needs FREYA_API_KEY (env.sh). Uses the kit's freya.py, so a slot always updates the same workflow
(.freya-agents.json) and every save is published. The platform drops fields it does not accept without an
error, so after saving we read the workflow back and report any node, tool or pre-action that went missing.
"""
import argparse
import os
import sys

from .common import event, read_json, write_json


def _shape(wf):
    shape = {}
    for group in ("nodes", "global_nodes"):
        for key, n in (wf.get(group) or {}).items():
            shape[f"{group}.{key}"] = (n.get("node_type"), len(n.get("tools") or []), len(n.get("pre_actions") or []),
                                      len(n.get("transitions") or []), len(n.get("extraction_schema") or []))
    shape["tools"] = len(wf.get("tools") or [])
    return shape


def compare(sent, stored):
    a, b = _shape(sent), _shape(stored)
    diffs = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            diffs.append(f"{k}: sent {a.get(k)}, stored {b.get(k)}")
    return diffs


def _lint(wf):
    try:
        from .lint import lint_workflow
    except ImportError:
        return None
    return lint_workflow(wf)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli deploy", description=__doc__.split("\n")[0])
    ap.add_argument("workflow")
    ap.add_argument("--slot", required=True)
    ap.add_argument("-o", "--out")
    ap.add_argument("--dry-run", action="store_true", help="lint and validate on Freya, save nothing")
    args = ap.parse_args(argv)
    wf = read_json(args.workflow)
    wf = wf.get("workflow", wf)

    report = _lint(wf)
    if report is None:
        print("warn: lint not available, deploying without it")
    elif report["errors"]:
        for e in report["errors"]:
            print(f"lint error {e['path']}: {e['msg']}")
        event("cli deploy", f"stopped: {len(report['errors'])} lint errors", [args.workflow])
        return 1

    if not os.environ.get("FREYA_API_KEY"):
        print("error: FREYA_API_KEY is not set (source env.sh)")
        return 1
    sys.path.insert(0, os.getcwd())
    import freya

    try:
        freya.validate_workflow(f"{args.slot} dry-run", wf)
    except RuntimeError as e:
        print(f"dry run rejected: {e}")
        event("cli deploy", "dry run rejected", [args.workflow], error=str(e)[:500])
        return 1
    if args.dry_run:
        print("dry run ok")
        event("cli deploy", "dry run ok", [args.workflow])
        return 0

    ids = freya.save_workflow(args.slot, wf)
    stored = freya.api("GET", f"/api/v2/workflow/{ids['workflow_id']}", workspaceId=freya.workspace_id())
    stored_wf = (stored.get("workflow") or {}).get("workflow") or {}
    diffs = compare(wf, stored_wf)
    out = {"slot": args.slot, "workflow_id": ids["workflow_id"], "agent_id": ids["agent_id"],
           "version": ids.get("version"), "steps": len(wf.get("nodes") or {}) + len(wf.get("global_nodes") or {}),
           "tools": sorted({t["function"]["name"] for n in list((wf.get("nodes") or {}).values())
                            + list((wf.get("global_nodes") or {}).values())
                            for t in (n.get("tools") or []) + (n.get("pre_actions") or [])}
                           | {t["function"]["name"] for t in wf.get("tools") or []}),
           "stored_differs": diffs}
    if args.out:
        write_json(args.out, out)
    summary = f"saved {args.slot}: workflow {out['workflow_id']}, agent {out['agent_id']}, {out['steps']} steps"
    if diffs:
        summary += f", {len(diffs)} fields changed by the platform"
    event("cli deploy", summary, [args.workflow], args.out, kind="created", workflow_id=out["workflow_id"],
          agent_id=out["agent_id"], steps=out["steps"], tools=out["tools"])
    print(summary)
    for d in diffs:
        print("  platform changed:", d)
    return 0
