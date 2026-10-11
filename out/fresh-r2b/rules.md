# Rules, Harbourview (brief r2)
Conflicts (later date wins): Policy v2 (1 Sep) < Mail (2 Oct) < Addendum (3 Oct) < Memo (6 Oct).
- Second band deadline: 6th business day (memo 6 Oct over policy 8th). -> dates.json
- Final band deadline: 3rd business day (addendum 3 Oct; memo silent) -> dates.json
- Callback window 09:00-17:00 (memo 6 Oct beats addendum 18:00) -> front
- Already paid: "up to two business days" (memo beats addendum) -> multi.situations.paid
Front: opening = automated assistant + monitored call; "Is this {first} {last}?"; ask twice then NR-UN close; robot/scam answers; nothing before security.
Front: third party: no detail, callback today later/next business day 09:00-17:00, one re-ask, NR-CB/NR-NO; wrong number NR-WN; died "I am very sorry to hear that." NR-DE.
Front: DOB then phone last4, verify_identity, numbers = D/M/Y, 3 wrong -> app/branch NV-FAIL; hint day_month_swapped -> month as word; refuse twice -> NV-REF.
Back: get_account, collections team statement, one sentence per product (label, amount, days), "Are you able to pay all of this today?"
Back: order largest past_due first (order_by); attempts per product; band 1-5 first (15 cal days roll back, 1 attempt), 6-20 second (6 biz, 2), 21-45 final (3 biz, 2).
Ladder: a1 full on end_of_week (next week if today) -> refuse: attempts 2 ? a2 (floor on deadline) : refused; too much -> floor_b once (rest stays overdue) -> refuse same as above. start_floor if already too much.
Back: dates/amounts checked by kit; one-date-for-all clamped; read back all + "Can you confirm?"; create_promise after yes, 1 retry, tech_fault note on failure; SMS line after recorded (promise close).
Back: notes at end only; reasons tool enum (refused/hardship/dispute/paid/service_error) because note tool does not take brief words; close reasons mapped to brief codes declined/welfare/contested/tech_fault via close_reasons.
Back: hardship -> sympathy, offer support transfer (XF-SU), declined -> welfare notes; new plan -> restructuring XF-PL; person -> ask once then general XF-HU; no discounts.
Closing: ARR promise, PD paid, NA-* no_promise with first non-settled reason, goodbye + thanks in each farewell.
