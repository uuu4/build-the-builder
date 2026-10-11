"""Reference generator for a brief with several products per customer (public Brief B).

    python3 examples/multi-brief-b/gen.py [out_dir]

front spec -> builder/kit/front.py, product facts and dates -> builder/kit/dates.py, the per-product
ladders, read-back and record stage -> builder/kit/multi.py. All brief values are in front.json and multi.json
next to this file; nothing here knows a bank.
"""
import json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from builder.kit import front, graph as g, dates, multi
from builder.kit.openapi import Api
from builder.kit.lint import lint

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "ours-FreyaBank-Test")
OUT.mkdir(parents=True, exist_ok=True)
api = Api(os.environ.get("TOOL_API", str(HERE / "tools.openapi.json")))
SPEC = pathlib.Path(os.environ.get("SPEC_DIR", HERE))
fspec = json.load(open(SPEC / "front.json"))
mspec = json.load(open(SPEC / "multi.json"))

nodes = front.build(api, fspec, after_verify="fetch_account")

params = json.load(open(SPEC / "dates.json"))
params["holidays"] = fspec["calendar"]["holidays"]
params["weekend"] = fspec["calendar"]["weekend_days"]
params["slots"] = mspec["slots"]
facts_src = dates.build_facts_code(params)
nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action(mspec["tools"]["account"], {}, retries=2), "facts")
nodes["facts"] = g.code("facts", facts_src, "close_error",
                        [g.eq(multi.entry(), "facts_state", "ok", "facts ready"), g.unset("facts_again", "facts_state", "code did not run")])
nodes["facts_again"] = g.code("facts_again", facts_src, "close_error",
                              [g.eq(multi.entry(), "facts_state", "ok", "facts ready")])
nodes.update(multi.build(api, mspec))

SYS = ("You are Freya Bank's digital assistant on an outbound phone call with {{title}} {{last_name}}. Speak English, short sentences, polite. "
       "Address the customer as {{title}} {{last_name}}. Never say goodbye yourself and never end the call: the system does that. "
       "Never invent figures, dates or terms. Never compute a date or an amount yourself: use the facts. "
       "Never say anything was recorded or booked.")
wf = {"initial_node": "setup", "system_prompt": SYS, "nodes": nodes,
      "test_variables": {api.id_field: "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
problems = lint(wf, api)
json.dump(wf, open(OUT / "workflow.json", "w"), indent=1)
print("lint:", problems or "clean", len(nodes), "nodes ->", OUT / "workflow.json")
