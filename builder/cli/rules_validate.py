"""cli rules-validate: check the agent's rule table against the brief it quotes.

    python3 -m builder.cli rules-validate out/<slot>/rules.json [--tools out/<slot>/tools.json] [--strict] [-o report.json]

docs/interfaces.md §1. At build time (default) only an unreadable or empty table is an error; everything else is a
warning, because a hard stop during the hidden run costs the whole brief. With --strict (tests, practice) conflicts,
broken supersedes links and missing quotes are errors.
- every rule has an id (unique), a known type and a quote that appears in its source (whitespace and quotes ignored)
- supersedes points at an existing rule, without cycles; superseded rules stay in the table
- two effective rules of the same type for overlapping applies_to are a conflict: the newer source_date wins,
  equal dates are reported
- identity field names and outcome codes are checked against the tool API's allowed values
"""
import argparse
import pathlib
import re

from .common import event, read_json, write_json

TYPES = {"band", "date_window", "amount_min", "installments", "holiday", "identity_fields", "outcome_codes",
         "disclosure", "statement", "attempts", "callback", "escalation", "call_hours", "free"}
SINGLE = {"holiday", "identity_fields", "outcome_codes", "call_hours"}


def _norm(text):
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[*_`>|]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _enums(tools):
    out = {}
    for name, t in (tools or {}).get("tools", {}).items():
        body = t["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
        for field, leaf in body.items():
            if leaf.get("enum"):
                out[f"{name}.{field}"] = set(leaf["enum"])
    return out


def validate(table, base_dir=".", tools=None, strict=False):
    errors, warnings = [], []
    hard = errors if strict else warnings
    if not isinstance(table, dict) or not table.get("rules"):
        return {"errors": [{"path": "rules", "msg": "empty or unreadable rule table"}], "warnings": [], "effective": []}
    texts = {}
    for i, s in enumerate(table.get("sources") or []):
        sid = s.get("id")
        if not sid:
            errors.append({"path": f"sources[{i}]", "msg": "source without id"})
            continue
        p = pathlib.Path(base_dir) / str(s.get("path", ""))
        try:
            texts[sid] = _norm(p.read_text(encoding="utf-8"))
        except OSError:
            warnings.append({"path": f"sources[{i}]", "msg": f"cannot read {p}; quotes not checked"})
    rules, ids = table["rules"], {}
    for i, r in enumerate(rules):
        path = f"rules[{i}]"
        rid = r.get("id")
        if not rid:
            errors.append({"path": path, "msg": "rule without id"})
            continue
        if rid in ids:
            errors.append({"path": path, "msg": f"duplicate id {rid}"})
        ids[rid] = r
        if r.get("type") not in TYPES:
            hard.append({"path": path, "msg": f"{rid}: unknown type {r.get('type')!r}"})
        q = (r.get("source") or {}).get("quote")
        doc = (r.get("source") or {}).get("doc")
        if not q:
            hard.append({"path": path, "msg": f"{rid}: no quote"})
            r["confidence"] = "uncertain"
        elif doc in texts and _norm(q) not in texts[doc]:
            hard.append({"path": path, "msg": f"{rid}: quote not found in source {doc}"})
            r["confidence"] = "uncertain"
    superseded = set()
    for rid, r in ids.items():
        sup = r.get("supersedes")
        if not sup:
            continue
        if sup not in ids:
            hard.append({"path": f"rules.{rid}", "msg": f"supersedes unknown rule {sup}"})
            continue
        seen, cur = {rid}, sup
        while cur:
            if cur in seen:
                hard.append({"path": f"rules.{rid}", "msg": "supersedes cycle"})
                break
            seen.add(cur)
            cur = ids.get(cur, {}).get("supersedes")
        superseded.add(sup)
    effective = [rid for rid in ids if rid not in superseded]
    by_type = {}
    for rid in effective:
        r = ids[rid]
        if r.get("type") in SINGLE or r.get("type") in ("date_window", "amount_min", "attempts"):
            by_type.setdefault(r["type"], []).append(r)
    for typ, group in by_type.items():
        for a_i in range(len(group)):
            for b_i in range(a_i + 1, len(group)):
                a, b = group[a_i], group[b_i]
                sa, sb = set(a.get("applies_to") or ["all"]), set(b.get("applies_to") or ["all"])
                if not ("all" in sa or "all" in sb or sa & sb):
                    continue
                if a.get("value") == b.get("value"):
                    continue
                da, db = a.get("source_date") or "", b.get("source_date") or ""
                if da != db:
                    newer = a if da > db else b
                    warnings.append({"path": f"rules.{a['id']}+{b['id']}",
                                     "msg": f"{typ} conflict, newer {newer['id']} wins; consider supersedes"})
                else:
                    hard.append({"path": f"rules.{a['id']}+{b['id']}",
                                 "msg": f"{typ} conflict with equal dates; use the stricter rule and mark it uncertain"})
    enums = _enums(tools)
    for rid in effective:
        r = ids[rid]
        v = r.get("value") or {}
        if r.get("type") == "identity_fields" and "verify_identity.field" in enums:
            for f in v.get("fields") or []:
                if f.get("name") not in enums["verify_identity.field"]:
                    warnings.append({"path": f"rules.{rid}", "msg": f"identity field {f.get('name')!r} not in the tool API"})
        if r.get("type") == "outcome_codes" and "close_call.outcome" in enums:
            for c in v.get("codes") or []:
                if c.get("code") not in enums["close_call.outcome"]:
                    warnings.append({"path": f"rules.{rid}", "msg": f"outcome {c.get('code')!r} not in the tool API"})
    uncertain = [rid for rid in effective if ids[rid].get("confidence") == "uncertain"]
    return {"errors": errors, "warnings": warnings, "effective": effective, "superseded": sorted(superseded),
            "uncertain": uncertain, "counts": {"rules": len(ids), "effective": len(effective)}}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cli rules-validate", description=__doc__.split("\n")[0])
    ap.add_argument("rules")
    ap.add_argument("--tools")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--base", default=".", help="folder the source paths are relative to")
    ap.add_argument("-o", "--out")
    args = ap.parse_args(argv)
    try:
        table = read_json(args.rules)
    except (OSError, ValueError) as e:
        print(f"error: cannot read {args.rules}: {e}")
        return 1
    rep = validate(table, args.base, read_json(args.tools) if args.tools else None, args.strict)
    if args.out:
        write_json(args.out, rep)
    c = rep.get("counts", {})
    summary = (f"{c.get('rules', 0)} rules, {c.get('effective', 0)} effective, {len(rep.get('uncertain', []))} uncertain, "
               f"{len(rep['errors'])} errors, {len(rep['warnings'])} warnings")
    event("cli rules-validate", summary, [args.rules], args.out)
    print(summary)
    for e in rep["errors"]:
        print(f"  error {e['path']}: {e['msg']}")
    for w in rep["warnings"]:
        print(f"  warn {w['path']}: {w['msg']}")
    return 1 if rep["errors"] else 0
