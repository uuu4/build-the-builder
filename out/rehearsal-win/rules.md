# Rules (Harbourview, brief-r2)
Conflicts (later written date wins): policy 1 Sep, mail 2 Oct, addendum 3 Oct, memo 6 Oct.
- Second band deadline: memo (6 Oct) -> 6th business day.
- Final band deadline: addendum (3 Oct) -> 3rd business day (memo silent, addendum later than policy).
- Callback window: memo -> 09:00-17:00.
- Already paid: memo -> "up to two business days".
- Note/close reasons: brief codes (declined, welfare, contested, settled, tech_fault) used; API enum differs (uncertain, logged).

Front: opening = automated assistant + monitored in same sentence; "Is this {first_name} {last_name}?"; ask twice then NR-UN; robot/scam answers; nothing before security.
Third party: no reason, callback today later than now / next business day 09-17, ask once more, NR-CB/NR-NO; wrong number NR-WN; died "I am very sorry to hear that." NR-DE.
Security: DOB then phone_last4, verify_identity, numeric = D/M/Y, 3 wrong -> app/branch NV-FAIL; day_month_swapped -> month as word; refuse twice -> NV-REF.
Back: get_account, collections team statement, one sentence per product, "Are you able to pay all of this today?"
Order: largest past_due first. Bands 1-5 first (15 cal days roll back, 1 attempt), 6-20 second (6th bd, 2), 21-45 final (3rd bd, 2).
Ladder: a1 full on end of week (next week if today) -> too much -> floor (remainder overdue) -> refuse -> a2 floor on deadline (2-attempt bands) -> refused note declined.
Hardship -> sympathy, support queue XF-SU, no notes. New plan -> restructuring XF-PL. Human -> ask once, general XF-HU.
Paid -> note settled; dispute -> note contested. Readback all, "Can you confirm?", create_promise per product, retry once, tech_fault.
Closing: ARR promise / PD paid / NA-* no_promise with first non-settled note reason; text message sentence after recording.
