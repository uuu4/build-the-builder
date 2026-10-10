# Brief A rules (single brief file, no conflicts)
- R1 opening: digital assistant of Freya Bank, "we are recording this call"; no collections/debt/payment/product before verify -> front
- R2-3 confirm question, confirm words, ask twice then not_reached/unclear -> front
- R4 robot -> digital assistant; R43 scam -> customer service number -> front + back prompts
- R5-10 third party, callback today/next biz day 10:00-19:00 after now, outside twice -> no_callback, wrong_number, deceased loss line -> front
- R11-15 identity DOB (YYYY-MM-DD, numbers = D/M/Y) then phone last4; 3 wrong -> failed (app/branch); swapped hint -> month as word; decline twice -> declined -> front
- R16-17 get_account, debt line in code (collections team, product words, past due, days late) -> back (code + tts)
- R18-23 deadline 12th/7th biz day, date table in code -> back facts
- R24-27 full first, floor once on too much, accept floor..full, below floor -> floor once -> back ladder
- R28 "Can you make this payment today?" -> appended to debt line
- R30-31 ladder: ask_today --refuses--> attempt1(full, last biz day of week) --refuses--> late? attempt2 (floor on deadline) : close refused
           ask_today --too_much--> floor_offer --refuses--> attempt1_floor --refuses--> late? attempt2 : close
           attempt1_full --too_much--> floor_offer_b (floor on attempt1 date) --refuses--> late? attempt2 : close
- R32 hardship node: sympathy, offer support transfer; yes -> transferred/support; no -> no_promise/hardship
- R33 no discounts -> prompt
- R34-38 read-back + "Do you confirm?", create_promise after yes, retry once, 2 failures -> service_error; text-message sentence in close farewell
- R39 paid -> close paid (one business day line); R40 dispute; R41 restructuring transfer; R42 human ask once; R44 no info; R45 no_talk -> refusal route
- R46-47 one close_call, thank + goodbye in every farewell
