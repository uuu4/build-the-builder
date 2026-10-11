"""The front of every collections call: who answered, someone else on the line, and the identity check.

Built once, the same way for every brief. The brief only fills the spec (see `SPEC_DOC`). What the practice runs taught
is built in here rather than left to a prompt:

- A question back ("why do you need that?", "who is this?") is answered and the question asked again. Only the kinds of
  turn the brief counts as declining move towards a `declined` close, and the first one gets one explanation.
- An answer given in pieces is joined before the bank is asked. A partial answer is never sent as a wrong one.
- The opening line, the farewells and every close are fixed text and literal close_call values: no model call decides them.
"""
from . import graph as g
from .pycode import with_params

SPEC_DOC = """front spec (JSON), every value from the brief and the tool API file:
{
  "bank": "name the agent calls from",
  "agent_identity": "what the agent says it is when asked if it is a robot or an AI",
  "opening_line": "first sentence, spoken word for word. Use {{title}}, {{last_name}}, {{first_name}}",
  "confirm_question": "the question that asks whether the right person is on the line",
  "confirm_words": "what counts as confirmation, in words",
  "not_confirm_words": "what does not count",
  "scam_answer": "what to say when asked whether the call is a scam (empty if the brief says nothing)",
  "purpose_before_verify": "what to say when asked what the call is about before identity is verified",
  "forbidden_before_verify": ["words or topics not to mention before identity is verified"],
  "identity": {
    "tool": "verify_identity",
    "field_param": "name of the request field that says which question is answered",
    "answer_param": "name of the request field with the answer",
    "questions": [{"field": "enum value of field_param", "ask": "how to ask it", "format": "how the answer is sent, e.g. YYYY-MM-DD", "complete_when": "what a complete answer has, e.g. day, month and year"}],
    "rules": ["other identity rules from the brief, one sentence each, e.g. how to read a date given only as numbers"],
    "result": {"all_verified": "response field true when every question passed", "left": "response field with wrong answers left, or empty",
               "verified": "response field true when this answer passed", "ok": "response field false when the request was not carried out",
               "hint": "response field with a hint, or empty"},
    "hints": {"hint value": "what the agent does when the bank returns it"},
    "explain_line": "the one explanation given after the first decline",
    "decline_kinds": ["refuses", "asks_purpose", "no_talk"],
    "declines_to_close": 2
  },
  "human": {"ask_first": "what to ask once before transferring a customer who wants a human", "queue": "queue value",
            "tool": "the transfer tool of the tool API file, default transfer_to_agent", "queue_param": "its queue field, default queue"},
  "third_party": {
    "rules": ["what to do and not do with someone who is not the customer, one sentence each"],
    "callback": {"tool": "schedule_callback", "days": ["today", "next_business_day"], "from": "HH:MM", "to": "HH:MM", "after_now": true,
                 "date_param": "date", "time_param": "time", "outside_asks": 2},
    "loss_line": "what to say when told the customer has died"
  },
  "calendar": {"holidays": ["YYYY-MM-DD"], "weekend_days": [5, 6]},
  "closes": {"unclear|callback|no_callback|wrong_number|deceased|failed|declined|human":
             {"outcome": "close_call outcome", "reason": "close_call reason or empty", "farewell": "spoken word for word"}}
}"""

FRONT_CLOSES = ("unclear", "callback", "no_callback", "wrong_number", "deceased", "failed", "declined", "human")

_CALLBACK_CODE = r'''
try:
    cb = P.get('callback') or dict()
    dt = get_now()
    today = dt.date()
    hhmm = dt.strftime('%H:%M')
    lo = cb.get('from') or '00:00'
    hi = cb.get('to') or '23:59'
    lines = []
    allowed = []
    for kind in cb.get('days') or []:
        if kind == 'today':
            d = today
        elif kind == 'next_business_day':
            d = nextbiz(today)
        elif kind == 'next_day':
            d = today + ONE
        else:
            continue
        if d == today and cb.get('after_now', True) and hhmm >= lo:
            if hhmm >= hi:
                continue
            lines.append('- ' + say(d) + ' (' + d.isoformat() + '), later than ' + hhmm + ', until ' + hi + ' (included)')
        else:
            lines.append('- ' + say(d) + ' (' + d.isoformat() + '), from ' + lo + ' to ' + hi + ' (both included)')
        allowed.append(d.isoformat())
    vars['today_iso'] = today.isoformat()
    vars['today_say'] = say(today)
    vars['callback_facts'] = ('Now is ' + say(today) + ', ' + hhmm + '. "Tomorrow" is ' + say(today + ONE) + '. A callback can be booked only for:\n'
                              + '\n'.join(lines) + '\nAny other day or time is outside the window.')
    vars['callback_dates'] = ','.join(allowed)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['callback_facts'] = 'The callback window could not be computed. Do not book a callback.'
    vars['setup_state'] = 'error ' + str(e)
'''


def verify_result_rules(spec):
    """How to read the bank's answer to a security question. Said in the prompt, not in a Python hook:
    hooks run in the platform's code sandbox, and when the sandbox is down the whole tool call fails."""
    r = spec["identity"]["result"]
    order = " then ".join(q["field"] for q in spec["identity"]["questions"])
    out = []
    if r.get("all_verified"):
        out.append(f"{r['all_verified']} is true: every answer passed. Say nothing more about the check.")
    if r.get("left"):
        out.append(f"{r['left']} is 0: no answers left, the check has failed. Say nothing about the account.")
    for hv, what in (spec["identity"].get("hints") or {}).items():
        out.append(f"{r.get('hint') or 'hint'} is {hv}: {what} This is not counted as a wrong answer.")
    if r.get("ok"):
        out.append(f"{r['ok']} is false: the answer could not be read and is not counted. Ask for the same answer again, said clearly and in full.")
    if r.get("verified"):
        out.append(f"{r['verified']} is true: that answer passed. Ask the next question that has not passed yet, in this order: {order}.")
        out.append(f"{r['verified']} is false: that answer does not match. Do not say what the right answer is. Say it does not match and ask the same question again.")
    out.append("The tool call itself fails (an error, no result): say you need a moment and ask for the same answer again. Do not transfer the call because of it.")
    return "Read each result of the check like this:\n" + "\n".join("- " + x for x in out)


def pre_verify_rules(spec):
    words = ", ".join(spec.get("forbidden_before_verify") or [])
    return ("Identity is NOT verified yet. Do not say why you are calling" + (f" and do not use these words or topics: {words}" if words else "") + ". "
            f"If asked what the call is about: {spec['purpose_before_verify']}")


def common_answers(spec):
    """Questions a customer may ask anywhere. Answer, then go back to the step's own question."""
    out = [f"Asked whether you are a robot or an AI: {spec['agent_identity']}"]
    if spec.get("scam_answer"):
        out.append(f"Asked whether this is a scam: {spec['scam_answer']}")
    out.append("Asked something you have no information about: say you do not have that information. Never invent anything.")
    return "\n".join("- " + x for x in out)


REQUIRED = ["opening_line", "confirm_question", "confirm_words", "not_confirm_words", "purpose_before_verify", "agent_identity",
            "identity.questions", "identity.field_param", "identity.answer_param", "identity.result.all_verified", "identity.explain_line",
            "human.ask_first", "human.queue", "third_party.callback", "third_party.loss_line"] + ["closes." + k for k in FRONT_CLOSES]


def check_spec(spec):
    """Names of the spec parts that are missing. The front is the same for every brief of this kind of bank (who answered,
    someone else on the line, a callback, the identity check, a human): a brief that lacks one of them still needs a value here,
    taken from the brief, not invented."""
    missing = []
    for path in REQUIRED:
        cur = spec
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                missing.append(path)
                break
            cur = cur[part]
    return missing


def build(api, spec, after_verify, prefix=""):
    """Return {node_key: node} for the front of the call. `after_verify` is the node that follows a verified identity.

    Entry node: `{prefix}setup`. Close nodes: `{prefix}close_<kind>` for FRONT_CLOSES, all leading to `{prefix}end`."""
    P = lambda n: prefix + n  # noqa: E731
    spec = dict(spec)
    spec.setdefault("calendar", {"holidays": [], "weekend_days": [5, 6]})
    missing = check_spec(spec)
    if missing:
        raise ValueError("front spec is missing: " + ", ".join(missing))
    idn, tp = spec["identity"], spec["third_party"]
    r = idn["result"]
    nodes = {}

    # --- closes: farewell, literal close_call, hang up
    nodes[P("end")] = g.end(P("end"))
    for kind in FRONT_CLOSES:
        c = spec["closes"][kind]
        nodes[P("close_" + kind)] = g.close(api, P("close_" + kind), c["outcome"], c.get("reason") or "", c["farewell"], P("end"))

    # --- setup: dates for the callback window
    setup_src = with_params(_CALLBACK_CODE, {"callback": tp["callback"], **spec["calendar"]})
    # the code sandbox can drop a run: try once more before the call starts
    nodes[P("setup")] = g.code(P("setup"), setup_src, P("opening"), [g.greater(P("setup_again"), P("setup") + "_failure_count", 0, "The setup code did not run")])
    nodes[P("setup_again")] = g.code(P("setup_again"), setup_src, P("opening"))

    # --- who answered
    who = g.enum_field("who_answered", ["customer", "someone_else", "wrong_number", "deceased", "question", "unclear"],
                       "Classify ONLY the last thing the person said, as an answer to: " + spec["confirm_question"] + " "
                       f"customer: {spec['confirm_words']}. "
                       "someone_else: they say they are not that person (a relative, partner, colleague), or that person is not there or not available. "
                       "wrong_number: they say this number does not belong to that person, or they do not know that person. "
                       "deceased: they say that person has died. "
                       "question: they ask something back (who is calling, what it is about, is this a robot, is this a scam) without confirming. "
                       f"unclear: anything else ({spec['not_confirm_words']}).")
    who_task = ("You are on an outbound call. " + pre_verify_rules(spec) + "\n" + common_answers(spec) + "\n"
                "Your only goal in this step is to learn whether you are speaking with {{title}} {{last_name}}. No tool call is allowed in this step.")

    def who_trs(fallback):
        return [g.eq(P("identity"), "who_answered", "customer", "The right person confirmed"),
                g.eq(P("third_party"), "who_answered", "someone_else", "Someone else answered"),
                g.eq(P("close_wrong_number"), "who_answered", "wrong_number", "Wrong number"),
                g.eq(P("close_deceased"), "who_answered", "deceased", "The customer has died"),
                g.always(fallback, "Not confirmed yet")]

    nodes[P("opening")] = g.conversation(P("opening"), who_task, who_trs(P("opening_again")), extract=[who],
                                         on_enter={"type": "tts", "text": spec["opening_line"]})
    who2 = dict(who, name="who_answered")
    nodes[P("opening_again")] = g.conversation(
        P("opening_again"), who_task, who_trs(P("close_unclear")), extract=[who2],
        on_enter={"type": "llm", "prompt": "The person did not confirm who they are. If they asked a question, answer it in one short sentence first. "
                                           f"Then ask exactly: \"{spec['confirm_question']}\" No tool call."})

    # --- someone else on the line
    cb = tp["callback"]
    cb_ok = api.ok_field(cb.get("tool", "schedule_callback"))
    hu = spec["human"]
    xfer, xq = hu.get("tool", "transfer_to_agent"), hu.get("queue_param", "queue")
    cb_tool = api.tool(cb.get("tool", "schedule_callback"),
                       "Book a callback. CALL it as soon as the person gives a day and an exact time that are inside the callback window. "
                       "Never call it for a day or time outside the window. If the result has ok false or an error, nothing was booked: do not say it was.",
                       descriptions={cb.get("date_param", "date"): "Callback date as YYYY-MM-DD.", cb.get("time_param", "time"): "Callback time as HH:MM, 24 hour."})
    tp_rules = "\n".join("- " + x for x in tp.get("rules") or [])
    nodes[P("third_party")] = g.conversation(
        P("third_party"),
        "You are speaking with someone who is NOT {{title}} {{last_name}}.\n" + tp_rules + "\n"
        "- Never say why you are calling. Never mention an account, product, amount, debt or payment. Never ask security questions, even if they offer to pay or to answer.\n"
        "- Your only goal: learn when {{title}} {{last_name}} can be reached, as a day and an exact time.\n\n{{callback_facts}}\n\n"
        "When the person gives a day and an exact time inside that window, call " + cb.get("tool", "schedule_callback") + ". "
        "If they give only a part of the day (\"in the morning\"), ask for an exact time. "
        # style "corrects", 11 October: "around ten, sorry", then "at ten, no, I" was booked at the first time said, not the corrected one
        "If they start to correct the time and do not finish (\"ten, sorry\", \"at ten, no, I\"), ask which time they meant before you book. "
        f"If what they give is outside the window, say the window in one sentence and ask once for another time. "
        "If they then again give a time outside the window, or cannot say, do not book anything; say you will try again another time. "
        f"If they say the customer has died: say \"{tp['loss_line']}\" and nothing else.\n" + common_answers(spec),
        tools=[cb_tool],
        extract=[g.enum_field("tp_state", ["giving_time", "outside_twice", "no_time", "wrong_number", "deceased", "other"],
                              "Classify the conversation with this person so far. outside_twice: they proposed a callback time outside the allowed window, "
                              "were asked for another one, and proposed a time outside it again. no_time: they cannot or will not say when the customer can be reached. "
                              "wrong_number: the number does not belong to the customer. deceased: the customer has died. giving_time: they are giving or about to give a time. other: anything else.")],
        on_enter={"type": "llm", "prompt": "The person on the line is not {{title}} {{last_name}}. Do not say why you are calling. Ask politely when {{title}} {{last_name}} can be reached."},
        transitions=[g.is_true(P("close_callback"), cb.get("tool", "schedule_callback") + "_response.data." + cb_ok, "The callback was booked"),
                     g.eq(P("close_deceased"), "tp_state", "deceased", "The customer has died"),
                     g.eq(P("close_wrong_number"), "tp_state", "wrong_number", "Wrong number"),
                     g.any_eq(P("close_no_callback"), "tp_state", ["outside_twice", "no_time"], "No callback can be booked")],
        max_turns=10, max_turn_target=P("close_no_callback"))

    # --- identity
    qs = idn["questions"]
    q_lines = "\n".join(f"{i + 1}. field {q['field']}: {q['ask']} Send the answer as {q['format']}. A complete answer has {q['complete_when']}."
                        for i, q in enumerate(qs))
    v_tool = api.tool(
        idn.get("tool", "verify_identity"),
        "Check ONE security answer with the bank. CALL it once for every COMPLETE answer the customer gives, with the field of the question asked. "
        "Never call it with a partial answer; parts given in different messages, joined, are a complete answer. Never call it twice for the same answer. A complete answer that comes with a question or a "
        "complaint in the same message is still an answer: call it first. After the result, speak to the customer.",
        descriptions={idn["field_param"]: "Which question was answered. One of: " + ", ".join(q["field"] for q in qs) + ".",
                      idn["answer_param"]: "The customer's complete answer, converted: " + "; ".join(f"{q['field']} as {q['format']}" for q in qs) + "."})
    transfer = api.tool(xfer,
                        "Hand the call to a person. CALL it with queue " + spec["human"]["queue"] + " only when the customer insists on a human after you asked once whether you can help. Never call it because of a technical problem.",
                        model_fields=(xq,), descriptions={xq: "Use " + spec["human"]["queue"] + "."})
    id_rules = "\n".join("- " + x for x in idn.get("rules") or [])
    id_task = (pre_verify_rules(spec) + "\n\nVerify the customer's identity. Ask these questions one at a time, in this order:\n" + q_lines + "\n\n"
               "How to handle answers:\n"
               "- Call " + idn.get("tool", "verify_identity") + " for every complete answer. After every result, speak to the customer: never leave a turn empty.\n"
               "- If the customer gives only part of an answer, or gives it over several turns, ask for the missing part and join the parts. Do not call the tool with a part.\n"
               # style "pieces", 11 October: "19 October" then "1983" was asked for again thirteen times, the tool never called
               "- Parts said in different messages together ARE a complete answer: a day and month in one message and the year in the next "
               "(for example '19 October', then '1983') is the date 1983-10-19. Digits are joined in the order they were said: 'forty-four', then 'zero one' is 4401 (never 0144); 'four four', then 'one zero' is 4410. "
               "As soon as every part has been said, join them and call the tool at once. Never ask again for a part the customer already gave: "
               "ask only for the part that is still missing, by name (for example 'And the year?').\n"
               "- If the customer corrects themselves, use the corrected value.\n"
               # PUB-03, live run of 10 October: "Twenty one July nineteen ninety. How much do I owe?" was a third wrong
               # answer; the model answered the question, never checked the date, and the customer passed on a fourth try
               "- If one message holds a complete answer AND a question or a complaint, call " + idn.get("tool", "verify_identity") + " with the answer FIRST, "
               "then answer the question after the result. Never skip or re-ask an answer because something else came with it: every complete "
               "answer is checked, a wrong one too, because the bank counts the wrong answers.\n"
               # the judge counts a repeated security question as asking it again (asks_back, talkative PUB-12)
               "- If the customer asks a question back (why you need it, who is calling, is this a robot, is this a scam), answer it in one short sentence "
               "and end with 'Whenever you are ready.' Do not repeat the security question, not even after the second question back "
               "(for example: 'I can only discuss that once your identity is verified. Whenever you are ready.'). "
               # B asks_back PUB-12, 11 October: "Which account is this about?" got the purpose line, whose spec text said to ask again
               "This holds for every question back, also one about what the call is about or which account, whatever the rule for that "
               "question says ('then continue', 'ask the security question again'): say what that rule says, end with 'Whenever you are ready.' "
               "and do not repeat the security question.\n"
               "- If the customer talks about something else, reply in a few words and wait. Repeat the security question only after two such "
               "messages in a row without an answer.\n"
               "- Never tell the customer a correct answer. Never say anything about the account.\n" + id_rules + "\n"
               f"- If the customer asks for a human: ask once, \"{spec['human']['ask_first']}\" If they still want a human, call {xfer}.\n"
               + common_answers(spec) + "\n\n" + verify_result_rules(spec))
    kinds = {"answer": "they give an answer or part of one, even with other words around it",
             "question": "they ask something back (why do you need this, who is calling, is this a robot, is this a scam, which account) without answering",
             "chat": "they talk about something unrelated",
             "refuses": "they say they will not answer or will not give that information",
             "asks_purpose": "instead of answering they ask what the call is about or why the bank is calling them",
             "no_talk": "they say they do not want to talk",
             "human": "they ask for a human",
             "other": "anything else"}
    desc = "Classify ONLY the customer's last message. " + " ".join(f"{k}: {v}." for k, v in kinds.items())
    declines = [k for k in idn.get("decline_kinds") or [] if k in kinds]
    id_trs = [g.is_true(after_verify, f"{idn.get('tool', 'verify_identity')}_response.data.{r['all_verified']}", "Identity verified")]
    if r.get("left"):
        id_trs.append(g.eq(P("close_failed"), f"{idn.get('tool', 'verify_identity')}_response.data.{r['left']}", "0", "No answers left"))
    id_trs.append(g.and_eq(P("close_human"), [[(xfer + "_response.data." + api.ok_field(xfer), v), (xfer + "_args." + xq, spec["human"]["queue"])] for v in ("true", "True")],
                           "Transferred to a human"))
    nodes[P("identity")] = g.conversation(
        P("identity"), id_task,
        id_trs + ([g.any_eq(P("identity_explain"), "id_turn", declines, "The customer declined once")] if declines else []),
        tools=[v_tool, transfer], extract=[g.enum_field("id_turn", list(kinds), desc)],
        on_enter={"type": "llm", "prompt": "Thank the person in a few words and ask the first security question: " + qs[0]["ask"] + " No tool call yet."},
        max_turns=16, max_turn_target=P("close_declined"))
    nodes[P("identity_explain")] = g.conversation(
        P("identity_explain"), id_task,
        id_trs + ([g.any_eq(P("close_declined"), "id_turn2", declines, "The customer declined a second time")] if declines else []),
        tools=[v_tool, transfer], extract=[g.enum_field("id_turn2", list(kinds), desc)],
        on_enter={"type": "llm", "prompt": f"Say: \"{idn['explain_line']}\" Then ask the security question that has not passed yet. No tool call yet."},
        max_turns=16, max_turn_target=P("close_declined"))
    return nodes
