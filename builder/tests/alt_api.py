"""A second bank: the same tool API with every name and code changed, and the example specs rewritten to match.

Used by test_alt_api to find what the kit assumes about the API. The renames cover three kinds of drift a new brief or
a new tool API file could bring: other values (codes, queues, identity fields), other field names (including the customer
id and the response flag), and other operation names."""
import copy
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

OPS = {"verify_identity": "check_answer", "get_account": "lookup_account", "create_promise": "register_promise", "add_note": "log_note",
       "schedule_callback": "book_callback", "transfer_to_agent": "hand_off", "close_call": "end_call"}
FIELDS = {"customer_id": "client_id", "field": "check", "answer": "value", "product_id": "account_ref", "amount": "sum", "date": "pay_on",
          "time": "at", "reason": "why", "queue": "route", "outcome": "result", "text": "memo",
          "ok": "success", "error": "err", "verified": "passed", "wrong_answers_left": "tries_left", "all_verified": "all_passed",
          "minimum_payment": "min_due", "instalment_amount": "rate", "card_last4": "card_tail", "past_due": "overdue", "days_late": "late_days",
          "type": "kind"}
VALUES = {"date_of_birth": "dob", "phone_last4": "mobile_tail",
          "promise": "kept", "paid": "settled", "transferred": "handed_over", "no_promise": "no_deal", "not_verified": "unverified", "not_reached": "unreached",
          "refused": "declined_to_pay", "hardship": "hard_times", "dispute": "disputed", "service_error": "system_fault",
          "restructuring": "plan_desk", "general": "front_desk", "support": "care",
          "credit_card": "card", "personal_loan": "loan_p", "car_loan": "loan_c"}
# values of the logical reasons inside a note (the bank's note reason for a paid product differs from the outcome "paid")
NOTE_PAID = "settled_already"


def _walk_api(o, key=None):
    """Rename an OpenAPI document: paths, operation ids, property names, required lists, enum values."""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            nk = k
            if key == "properties":
                nk = FIELDS.get(k, k)
            elif key == "paths":
                nk = "/" + OPS.get(k.strip("/"), k.strip("/"))
            out[nk] = _walk_api(v, k)
        return out
    if isinstance(o, list):
        if key == "required":
            return [FIELDS.get(x, x) for x in o]
        if key == "enum":
            return [VALUES.get(x, x) for x in o]
        return [_walk_api(x, key) for x in o]
    return o


def alt_openapi():
    doc = _walk_api(json.load(open(ROOT / "tools/openapi.json")))
    for ops in doc["paths"].values():
        for op in ops.values():
            op.pop("operationId", None)
    # note reasons: the bank calls a paid product "settled_already" in a note
    for p, ops in doc["paths"].items():
        for op in ops.values():
            props = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("properties", {})
            if "why" in props and "enum" in props["why"]:
                props["why"]["enum"] = [NOTE_PAID if x == "settled" else x for x in props["why"]["enum"]]
    return doc


def _val(o):
    """Rename values (never keys) of a spec."""
    if isinstance(o, dict):
        return {k: _val(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_val(x) for x in o]
    if isinstance(o, str):
        for a, b in {**OPS, **FIELDS, **VALUES}.items():
            if o == a:
                return b
        return o.replace("<card_last4>", "<card_tail>")
    return o


def alt_specs(example):
    """(front, multi, dates) of an example directory, rewritten for the alternative bank."""
    d = ROOT / "examples" / example
    front = _val(json.load(open(d / "front.json")))
    multi = json.load(open(d / "multi.json"))
    notes = copy.deepcopy(multi["reasons"])
    for key in ("reasons", "queues", "closes", "tools", "fields"):        # the ladder's node names are the kit's, not the bank's
        multi[key] = _val(multi[key])
    multi["reasons"] = {k: (NOTE_PAID if k == "paid" else VALUES.get(v, v)) for k, v in notes.items()}   # logical -> bank value
    dates = json.load(open(d / "dates.json"))
    fts = dates.pop("floor_field_by_type")
    labels = dates.pop("product_label")
    dates = _val(dates)
    dates["floor_field_by_type"] = {VALUES.get(k, k): FIELDS.get(v, v) for k, v in fts.items()}
    dates["product_label"] = {VALUES.get(k, k): v.replace("<card_last4>", "<card_tail>") for k, v in labels.items()}
    dates["products_fallback_vars"] = ["fetch_account_response.data.products"]
    dates["fields"] = {"id": "account_ref", "type": "kind", "past_due": "overdue", "days_late": "late_days"}
    return front, multi, dates


def alt_products(products):
    out = []
    for p in products:
        out.append({FIELDS.get(k, k): VALUES.get(v, v) if k == "type" else v for k, v in p.items()})
    return out
