"""Reference generator for a brief with one product per customer (public Brief A (one product per customer, no notes)).

    python3 examples/multi-brief-a/gen.py [out_dir]

front spec -> builder/kit/front.py, product facts and dates -> builder/kit/dates.py, the per-product
ladders, read-back and record stage -> builder/kit/multi.py. All brief values are in front.json and multi.json
next to this file; nothing here knows a bank.
"""
import json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from builder.kit import front, graph as g, dates, multi, pycode
from builder.kit.openapi import Api
from builder.kit.lint import lint

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "inst-i")
OUT.mkdir(parents=True, exist_ok=True)
api = Api(os.environ.get("TOOL_API", str(ROOT / "practice/brief-i/openapi-i.json")))
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

# --- two-instalment split (brief rules 26, 26a, 33, 36): amounts and dates computed in code, read back once, two promises
SPLIT_BODY = """
try:
    due = float(str(vars.get('s1_due') or '').replace(',', '').strip())
    c = int(round(due * 100))
    h = (c + 1) // 2
    a1 = '%.2f' % (h / 100.0)
    a2 = '%.2f' % ((c - h) / 100.0)
    d1 = str(vars.get('end_of_week') or '')
    d2 = str(vars.get('s1_deadline_text') or '')
    lab = str(vars.get('s1_label') or 'account')
    vars['split1_amt'] = a1
    vars['split2_amt'] = a2
    vars['split_line'] = ('I understand. I can offer to split the past-due amount of ' + ('%.2f' % due) + ' into two instalments: ' + a1 + ' on ' + d1 + ', and ' + a2 + ' on ' + d2 + '. Would that work for you?')
    vars['split_readback'] = ('Let me read back what we agreed. For your ' + lab + ': a first instalment of ' + a1 + ' on ' + d1 + ', and a second instalment of ' + a2 + ' on ' + d2 + '. Do you confirm?')
    vars['split_state'] = 'ok'
except Exception:
    vars['split_state'] = 'err'
"""
nodes["split_calc"] = g.code("split_calc", pycode.with_params(SPLIT_BODY, {}), multi.entry())
for fn in ("facts", "facts_again"):
    for t in nodes[fn]["transitions"]:
        if t["target_node"] == multi.entry():
            t["target_node"] = "split_calc"
# accepting the split goes to its own read-back, not to the single-promise save
sp = nodes["p1_split"]
for t in sp["transitions"]:
    if t["target_node"].startswith("save_1"):
        t["target_node"] = "split_rb"
rbvar = "split_rb_ans"
for dead in ("save_1_split", "save_1_split_again"):
    nodes.pop(dead, None)
nodes["split_rb"] = g.conversation(
    "split_rb",
    "The customer's identity is verified. You read back the two instalments and asked 'Do you confirm?'. A clear yes is a confirmation: do not call any tool, the system records both instalments. "
    "If they refuse the split now, the system offers the floor. Never say anything is recorded. If they ask a question, answer it in a few words and ask 'Do you confirm?' again. "
    "If they want other dates or amounts for the instalments, say these are the dates and amounts I can offer for the split and ask 'Do you confirm?' again.",
    [g.eq("split_rec1", rbvar, "confirms", "confirmed"), g.eq("p1_floor_b", rbvar, "refuses", "refused the split")],
    extract=[g.enum_field(rbvar, ["confirms", "refuses", "other"],
                          "Classify ONLY the customer's last message. confirms: a clear yes to the read-back. refuses: they no longer want the split or say no. other: anything else (a question, a change, chat).", 0.4)],
    on_enter={"type": "tts", "text": "{{split_readback}}"}, max_turns=6, max_turn_target="refused_1")
ok = api.ok_field(mspec["tools"]["promise"])
pt = mspec["tools"]["promise"]
def inst(n, amt, date):
    return {"product_id": "{{s1_pid}}", "amount": "{{%s}}" % amt, "date": "{{%s}}" % date, "instalment": n}
nodes["split_rec1"] = g.api_request("split_rec1", api.pre_action(pt, inst(1, "split1_amt", "end_of_week_iso"), retries=0), "split_rec1b",
                                    transitions=[g.is_true("split_rec2", f"split_rec1_response.data.{ok}", "recorded")])
nodes["split_rec1b"] = g.api_request("split_rec1b", api.pre_action(pt, inst(1, "split1_amt", "end_of_week_iso"), retries=0), "close_error",
                                     transitions=[g.is_true("split_rec2", f"split_rec1b_response.data.{ok}", "recorded on retry")])
nodes["split_rec2"] = g.api_request("split_rec2", api.pre_action(pt, inst(2, "split2_amt", "s1_deadline"), retries=0), "split_rec2b",
                                    transitions=[g.is_true("close_promise", f"split_rec2_response.data.{ok}", "recorded")])
nodes["split_rec2b"] = g.api_request("split_rec2b", api.pre_action(pt, inst(2, "split2_amt", "s1_deadline"), retries=0), "close_promise",
                                     transitions=[g.is_true("close_promise", f"split_rec2b_response.data.{ok}", "recorded on retry")])

SYS = ("You are Freya Bank's digital assistant on an outbound phone call with {{title}} {{last_name}}. Speak English, short sentences, polite. "
       "Address the customer as {{title}} {{last_name}}. Never say goodbye yourself and never end the call: the system does that. "
       "Never invent figures, dates or terms. Never compute a date or an amount yourself: use the facts. "
       "Never say anything was recorded or booked.")
wf = {"initial_node": "setup", "system_prompt": SYS, "nodes": nodes,
      "test_variables": {api.id_field: "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
problems = lint(wf, api)
json.dump(wf, open(OUT / "workflow.json", "w"), indent=1)
print("lint:", problems or "clean", len(nodes), "nodes ->", OUT / "workflow.json")
