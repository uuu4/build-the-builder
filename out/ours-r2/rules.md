# Harbourview (brief r2) rules
## Conflicts (later written date wins): Policy 1 Sep < Mail 2 Oct < Addendum 3 Oct < Memo 6 Oct
- Second band deadline: 6th business day (memo 6 Oct beats policy 8th).
- Final band deadline: 3rd business day (addendum 3 Oct beats policy 4th; memo silent, so addendum stays).
- Callback window: 09:00-17:00 (memo 6 Oct beats addendum 18:00).
- Already paid: "up to two business days" (memo beats addendum).
## Front spec
- Opening: automated assistant of Harbourview + call monitored in same first sentence; nothing about money before security.
- "Is this {first_name} {last_name}?"; yes/speaking/own name counts; second unclear -> NR-UN (not_reached/unconfirmed).
- Robot: Harbourview's automated assistant. Scam: phone number on statement. Unknown: no information.
- Third party: no reason; callback today later than now or next business day 09:00-17:00 -> NR-CB; second outside -> NR-NO; wrong number NR-WN; died: "I am very sorry to hear that." NR-DE. Relatives told nothing.
- Security: DOB (YYYY-MM-DD, numbers = D/M/Y) then phone last4, verify_identity; 3 wrong -> app/branch, NV-FAIL; day_month_swapped -> month as word; refuse twice / ask purpose twice -> NV-REF.
## Back half (multi kit)
- get_account; debt statement per product (card ending X / personal loan / car loan, amount, days overdue); "Are you able to pay all of this today?"
- Order: largest past_due first (order_by past_due desc).
- Bands: 1-5 first: 15 calendar days back-rolled, 1 attempt; 6-20 second: 6th bd, 2; 21-45 final: 3rd bd, 2.
- Holidays 2026-10-19, 2026-10-29, 2026-11-16, 2026-12-25, 2027-01-01.
- Floor: card minimum_payment, loans instalment_amount.
- Ladder: attempt1 full on end of week (if today -> next week) --refuse--> attempts==2 ? attempt2 (floor on deadline) : refused.
  too much -> floor (no date pinned), remainder stays overdue --refuse--> attempts==2 ? attempt2 date-only : refused.
- Hardship -> sympathy, offer support transfer (XF-SU); declined -> notes welfare.
- New plan -> restructuring XF-PL; human -> ask once -> general XF-HU.
- Notes: brief declined/welfare/contested/settled/tech_fault -> API refused/hardship/dispute/paid/service_error (API enum). close_call reasons use brief codes (declined/welfare/contested/tech_fault), mapped in gen.py.
- Confirm: one readback, "Can you confirm?", create_promise per product, one retry; text-message sentence after recorded -> in promise farewell.
- Closes: ARR promise; PD paid; NA-* no_promise + reason of first discussed non-settled product.
