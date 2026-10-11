# Harbourview rules (rehearsal-1)
Conflicts resolved by date written: Policy (1 Sep) < Mail (2 Oct) < Addendum (3 Oct) < Memo (6 Oct).
- Second band deadline: 6th business day (memo 6 Oct beats addendum/policy 8th).
- Final band deadline: 3rd business day (addendum 3 Oct beats policy 4th; memo silent).
- Callback window 09:00-17:00 (memo beats addendum 18:00).
- Already paid: "up to two business days" (memo beats addendum one day).
- Note reasons: tool API enum is refused/hardship/dispute/paid/service_error -> declined=refused, welfare=hardship, contested=dispute, settled=paid, tech_fault=service_error. Close reasons use the brief's codes (declined/welfare/contested/tech_fault) via mapping in gen.py.

Front spec: opening (automated assistant + monitored, first sentence), "Is this {first} {last}?", confirm words, ask twice then NR-UN; robot/scam/unknown answers; nothing before security; third party rules 9.1.1-9.1.6 (callback today later than now / next biz day 09:00-17:00, ask once more, NR-NO; wrong number NR-WN; died "I am very sorry to hear that." NR-DE); security DOB then phone last4, DD/MM/YYYY, 3 wrong -> app/branch NV-FAIL; day_month_swapped -> month as word; refuse -> explain once, second -> NV-REF; human -> ask once, XF-HU.
Back half (dates/multi): get_account; debt statement per product (card ending/personal loan/car loan, amount, days); "Are you able to pay all of this today?"; order largest past_due first; bands first 1-5 (15 cal days roll back, 1 attempt), second 6-20 (6 biz, 2), final 21-45 (3 biz, 2); holidays 2026-10-19,10-29,11-16,12-25,2027-01-01.
Ladder per product: attempt1 full on end of week (if today then next week) -> too_much: floor (rest overdue) -> refuse: if attempts 2 -> attempt2 floor on deadline -> refuse: declined note. Floor-first start if already too much.
Dates 9.5.4-9.5.7, "next Friday" = following week; amounts floor..full accepted; below floor -> floor once.
Hardship -> sympathy, offer support transfer (XF-SU, no notes) else welfare notes. New plan -> XF-PL. Paid -> sentence + settled note. Dispute -> contested note.
Closing: read back all, "Can you confirm?", create_promise per product (retry once), tech_fault note on fail, "You will receive a text message confirming this arrangement." ARR/PD/NA-* codes in code.
