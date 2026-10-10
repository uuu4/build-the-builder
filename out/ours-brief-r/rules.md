# Brief R rules (Northwind Bank). Newest wins: memo (Part 3) over policy (Part 2) over mail (Part 1).
Conflicts resolved: priority latest date = 6th business day (memo, was 5th); callback window 09:00-17:00 (memo, was 18:00); already paid = "up to two business days" (memo, was one).
Deceased: 7.1.5 "My condolences." and nothing else wins over the mail's thank-and-goodbye (more specific rule).

## Front spec
- Opening: Northwind Bank's automated assistant, first sentence says call is being recorded. Nothing about debt before security (anyone).
- Ask "Am I speaking to {first_name} {last_name}?"; yes/speaking/that's me/own name counts; hello/go ahead/who's this does not. Question first: answer, ask once more; still unclear -> NR-UC.
- Robot: "I am Northwind Bank's automated assistant". Scam: call the number on the back of your card. Unknown info: say not available.
- 7.1.1 third party: no reason, ask when customer reachable. 7.1.2 callback today later than now or next business day 09:00-17:00 -> schedule_callback -> NR-CB. 7.1.3 outside twice -> NR-NCB. 7.1.4 wrong number -> NR-WN. 7.1.5 deceased -> "My condolences." NR-DC. 7.1.6 family: no security, no info.
- 7.2.1 phone_last4 then date_of_birth (YYYY-MM-DD, numeric = day month year). 7.2.2 three wrong -> app/branch, NV-F. 7.2.3 day_month_swapped -> ask month as a word, not wrong. 7.2.4 one explanation, second decline -> NV-R. 7.8.5 before security = refusal.
- 7.8.4 human: ask once if agent can help; insist -> transfer general, TRF-AG.

## Back half
- 7.3.1 get_account (api_request), code: product words, amount, days -> fixed debt line + "Are you able to pay this amount today?" (7.3.2).
- 7.4 calendar: holidays 2026-10-20, 2026-11-03, 2026-12-25, 2027-01-01; standard 1-10 days: latest = 10th biz day, 1 attempt; priority 11-45: latest = 6th biz day, 2 attempts. Date table in code (weekend/holiday -> next biz day; after latest -> latest). Vague -> ask once, else propose latest. next/this Friday computed.
- 7.5 floor = minimum_payment (card) / instalment_amount (loans). Never ask how much. Too much -> floor once, remainder stays overdue. Customer amount floor..full accepted; below floor -> say cannot record, offer floor once.
- 7.6 ladder (state machine):
  today(full, today): refuses -> a1_full; too_much -> floor0
  floor0 (floor, no date, remainder overdue): refuses -> a1_floor
  a1_full (full on last biz day of week / next week if today is that day): refuses -> priority? a2_floor : close NP-REF; too_much -> floor1
  floor1 (floor, no date): refuses -> priority? a2_date : NP-REF
  a1_floor (date only, Friday): refuses -> priority? a2_date : NP-REF
  a2_floor (floor on latest date): refuses -> NP-REF
  a2_date (date only, latest date): refuses -> NP-REF
- 7.6.5 hardship: sympathy, offer welfare transfer (support) -> TRF-WF; declined -> NP-HS; may still take arrangement.
- 7.6.6 no discounts/waivers/plans.
- 7.7.1 read back product, amount, date, "Can you confirm?" -> create_promise after yes. 7.7.2 one arrangement. 7.7.3 retry once; two failures -> NP-ERR. 7.7.4 "You will receive a text message confirming this arrangement." -> PTP.
- 7.8.1 paid -> "up to two business days" -> PAID. 7.8.2 dispute -> NP-DS. 7.8.3 new plan -> transfer restructuring -> TRF-RS. 7.8.6 no add_note.

## Closing
Every close: thank + goodbye (except deceased), literal close_call outcome/reason from Part 4.
