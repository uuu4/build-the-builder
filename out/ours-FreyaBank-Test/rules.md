# Rules (Brief A, Freya Bank, one product) -> kit path, slots 1
Shape: outbound collections call; identity (DOB then phone_last4), get_account, one promise per product, one close_call. Kit covers it.
Single source doc (BRIEF.md); no conflicts. Service contract gives names/enums; close_call reason has no enum (free string, values from brief table).
- R1-4 opening, robot, confirmation (2 asks -> not_reached/unclear): front spec
- R5-10 third party, callback window today/next biz day 10:00-19:00 after now, 2 asks, wrong_number, deceased ("I am sorry for your loss."): front spec
- R11-15 identity, 3 wrong total, day_month_swapped hint, failed/declined (2 declines): front spec
- R16-17 get_account, debt statement fixed line: dates.json lines.state + today.say
- R18-23 bands early 1-7 (12th biz day, 1 attempt), late 8-45 (7th biz day, 2 attempts); holidays; next weekday = following week: dates.json, multi.json next_weekday
- R24-27 full first, floor = minimum_payment / instalment_amount, too much -> floor once: ladder
- R28-31 ladder state machine: ask today -> refuse -> attempt1 (full, or floor if too much) on last biz day this week (next week if today) -> refuse -> late: attempt2 floor on deadline; early: close no_promise/refused
- R32 hardship -> support transfer / no_promise hardship; R39 paid; R40 dispute; R41 restructuring; R42 human ask once; R43 scam; R45 two no-talk: back half situations
- R34-38 read-back "Do you confirm?", create_promise 2 tries, service_error, text-message sentence in promise farewell: multi closes
- R46-47 one close, thank + goodbye: closes. Brief A never uses add_note -> notes:false
Uncertain: contract does not name product item fields; used product_id,type,past_due,days_late,minimum_payment,instalment_amount,card_last4 (mock rejects test customer c_demo, could not probe).
