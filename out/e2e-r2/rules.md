# Rules, Harbourview (brief-r2)
Conflicts (later written date wins): Policy 1 Sep < Branch addendum 3 Oct < Memo 6 Oct.
- Second band deadline: 6th business day (memo 6 Oct beats policy 8th).
- Final band deadline: 3rd business day (addendum 3 Oct; memo silent, so stays).
- Callback window 09:00-17:00 (memo 6 Oct beats addendum 18:00).
- Already paid: "up to two business days" (memo beats addendum one day).
- Note reasons: API enum (refused/hardship/dispute/paid/service_error) mapped from brief declined/welfare/contested/settled/tech_fault; close_call reasons as in Part 5 (declined/welfare/contested/tech_fault) via mapping in gen.py.

## Front (front.json)
- Opening: automated assistant + monitored in first sentence; nothing about money before security.
- "Is this {first_name} {last_name}?" ; ask twice, then close NR-UN (not_reached/unconfirmed).
- Robot -> automated assistant; scam -> phone number on statement; unknown -> no info.
- Third party: no reason, ask when reachable; callback today later than now or next business day 09:00-17:00, ask twice -> NR-CB / NR-NO; wrong number NR-WN; died "I am very sorry to hear that." NR-DE; relatives told nothing.
- Security: DOB (YYYY-MM-DD, numbers = D/M/Y) then phone last4; 3 wrong -> app/branch, NV-FAIL; day_month_swapped -> month as word; refuse twice -> NV-REF.
- Human: ask once, insist -> general queue, XF-HU (transferred/person).

## Back half (multi kit)
- get_account, state each product (label, overdue, days overdue), ask "Are you able to pay all of this today?"
- Order: largest past_due first (order_by). Bands: 1-5 first (15 cal days, roll back, 1 attempt), 6-20 second (6th bd, 2), 21-45 final (3rd bd, 2). Holidays 2026-10-19, 10-29, 11-16, 12-25, 2027-01-01.
- Ladder per product: a1_full (full, end of week; if today = that day, next week) -> refuse: attempts 2 ? a2 : refused. too much -> floor_b (floor, end of week, remainder stays overdue) -> refuse: a2 or refused. a2 = floor on latest date -> refuse: refused.
- Next Friday = following week. Vague -> ask once then latest date.
- Hardship -> sympathy, offer support (XF-SU); declined -> notes welfare.
- New plan -> restructuring XF-PL. Paid -> note settled, carry on. Dispute -> note contested.
- Read-back all, "Can you confirm?", create_promise per product, 1 retry, fail -> note tech_fault.
- Closing: ARR promise; PD paid; else NA-* by first non-settled note reason in discussion order.
- Farewell after recorded: "You will receive a text message confirming this arrangement."
