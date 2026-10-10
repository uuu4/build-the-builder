# Brief A rules (single brief file, no conflicts to resolve)
1 opening: digital assistant, Freya Bank, call recorded ("we are recording this call"); no collections/debt/payment/product pre-verify -> front opening_line, forbidden_before_verify
2 ask "Am I speaking with {title} {last_name}?" -> front confirm_question
3 confirmation words; ask twice then not_reached/unclear -> front (opening, opening_again)
4 robot/AI -> front agent_identity
5-7 third party: no reason; callback today/next biz day 10:00-19:00 after now; outside twice -> no_callback -> front third_party/callback
8 wrong_number, 9 deceased "I am sorry for your loss." -> front closes
10 relative gets no info -> front third_party rules
11-13 DOB then phone_last4, YYYY-MM-DD, DMY numeric, 3 wrong -> fail, day_month_swapped hint -> front identity
14 failed: app or branch -> close failed farewell
15 decline once explained, second -> declined -> front decline_kinds
16 get_account -> back: fetch_account api_request
17 debt line (product in words, past due, days late) -> back: code builds debt_line, tts
18-23 deadline/band/date rules -> back: code computes deadline, calendar table, weekday words; prompt
24-27 amounts / floor -> back: code facts + prompt plan
28 "Can you make this payment today?" -> end of debt_line
29-31 persuasion attempts -> back: numbered plan in prompt, intent route to close_refused
32 hardship -> back: hardship node, transfer support (api_request) or close hardship
33 no discount/plan -> system prompt
34-37 read-back, "Do you confirm?", create_promise, retry once, service_error -> back: negotiate tools + routes on create_promise_response / failure_count
38 "You will receive a text message confirming this promise." -> close_promise farewell (fixed)
39 paid -> close_paid; 40 dispute; 41 restructuring transfer (api_request); 42 human ask once then general
43 scam -> front scam_answer; 44 no info -> prompt; 45 no talk twice -> refused (post) / declined (pre)
46-47 one close_call, thank + goodbye before -> every close farewell
Choice: transfer after recorded promise not modelled (rare); promise close is literal "promise".
