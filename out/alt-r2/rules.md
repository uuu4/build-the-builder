# alt-r2 rules (Harbourview)
Conflicts (later written date wins): policy eff. 1 Sep < mail 2 Oct < addendum 3 Oct < memo 6 Oct.
- Second band deadline: 6th business day (memo 6 Oct beats addendum/policy).
- Final band deadline: 3rd business day (addendum 3 Oct; memo silent; beats policy 4th).
- Callback window 09:00-17:00 (memo 6 Oct beats addendum 18:00).
- Already paid: "up to two business days" (memo).
Front: opening = automated assistant + monitored, same sentence; ask "Is this {first} {last}?"; 2 asks then NR-UN.
Front: robot/scam/unknown answers; nothing about money before security.
Front: third party -> callback today later/next biz day 09:00-17:00, ask once more, NR-CB/NR-NO; wrong num NR-WN; died "I am very sorry to hear that." NR-DE.
Front: DOB (YYYY-MM-DD, numeric = d/m/y) then mobile tail; 3 wrong -> app/branch NV-FAIL; day_month_swapped -> month as word; refusal x2 -> NV-REF.
Back: get_account; statement per product; "Are you able to pay all of this today?"; order largest overdue first.
Back bands: 1-5 first (15 cal days, roll back, 1 attempt); 6-20 second (6th bd, 2); 21-45 final (3rd bd, 2).
Ladder: a1 full on end of week (if today -> next week); too much -> floor once (remainder overdue); refuse -> attempts==2 ? a2 floor on deadline : declined.
Floor: card min_due, loans "rate" field (only loan amount field in API).
Readback all together "Can you confirm?"; create_promise after yes, retry once, tech_fault note on failure.
Notes: declined/welfare/contested/settled/tech_fault mapped to API enum refused/hardship/dispute/paid/service_error.
Closes: ARR promise; PD paid; XF-PL transferred plan; XF-HU person; XF-SU support; NA-* no_promise with reason code; NV/NR per table.
Choice: close reason codes sent as written in Part 5 (declined, welfare...), note reasons from API enum.
