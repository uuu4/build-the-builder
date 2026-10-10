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

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "multi-brief-b")
OUT.mkdir(parents=True, exist_ok=True)
api = Api(os.environ.get("TOOL_API", str(ROOT / "tools/openapi.json")))
fspec = json.load(open(HERE / "front.json"))
mspec = json.load(open(HERE / "multi.json"))

nodes = front.build(api, fspec, after_verify="fetch_account")

params = {
    "now_var": "now", "slots": mspec["slots"],
    "products_fallback_vars": ["fetch_account_response.data.products"],
    "holidays": fspec["calendar"]["holidays"], "weekend": fspec["calendar"]["weekend_days"],
    "bands": [{"name": "early", "days_late_min": None, "days_late_max": 7, "deadline": {"kind": "business_days", "n": 12}, "attempts": 1},
              {"name": "late", "days_late_min": 8, "days_late_max": None, "deadline": {"kind": "business_days", "n": 7}, "attempts": 2}],
    "floor_field_by_type": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
    "product_label": {"credit_card": "credit card ending <card_last4>"},
    "named_dates": [{"name": "end_of_week", "kind": "last_business_day_this_week", "if_today_use_next_week": True}],
    "lines": {
        "state": "Your <label> has a past-due amount of <due> and is <days_late> days late.",
        "a1_full": "I understand. Could you pay the full past-due amount of <due> on <end_of_week> for your <label>?",
        "a1_floor": "I understand. Could you pay <floor> on <end_of_week> for your <label>? The rest stays overdue.",
        "floor_b": "I understand. The lowest amount I can record for your <label> is <floor>, on <end_of_week>. The rest stays overdue. Can you pay <floor> on <end_of_week>?",
        "a2": "I understand. As a last option, could you pay <floor> on <deadline> for your <label>? The rest stays overdue.",
    },
    "joined_lines": {"debt_statement": {"line": "state", "suffix": " Can you pay all of them today?", "suffix_one": " Can you make this payment today?"}},
}
facts_src = dates.build_facts_code(params)
nodes["fetch_account"] = g.api_request("fetch_account", api.pre_action("get_account", {}, retries=2), "facts")
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
      "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
problems = lint(wf, api)
json.dump(wf, open(OUT / "workflow.json", "w"), indent=1)
print("lint:", problems or "clean", len(nodes), "nodes ->", OUT / "workflow.json")
