# Brief I: rules and where they go

Source: practice/brief-i/brief-i.md (Brief A plus a two-instalment split: rules 26, 26a, 33, 36). One brief file, so nothing conflicts. Tool API: openapi-i.json (create_promise has an optional `instalment` 1|2).

## Front (front.json, kit front.py)
1. Opening: digital assistant from Freya Bank, "we are recording this call"; no collections/debt/payment/product before verify. front
2. Ask "Am I speaking with {title} {last_name}?". front
3. Only yes / that's me / speaking / own name confirms; ask twice, then not_reached/unclear; answer questions first. front
4. Robot/AI → Freya Bank's digital assistant. front
5. Third party: no reason for the call; ask when reachable. front
6. Callback today or next business day, 10:00–19:00, after now → schedule_callback, not_reached/callback. front
7. Outside window twice → not_reached/no_callback. front
8. Wrong number → not_reached/wrong_number. front
9. Deceased → "I am sorry for your loss.", not_reached/deceased. front
10. Relative: no security questions, no account info. front
11. DOB (YYYY-MM-DD, numbers read as day-month-year), then phone last 4. front
12. Three wrong answers in total end the check. front
13. hint day_month_swapped → ask with the month as a word, does not count. front
14. Failed → app or branch, not_verified/failed. front
15. Decline: explain once, second decline (or asking the purpose) → not_verified/declined. front

## Back half (multi.json + dates.json, kit multi.py/dates.py; slots 1)
16–17. get_account, then the fixed debt statement (product in words, past due, days late). dates lines.state
18. Bands: 1–7 early (12th business day, 1 attempt), 8–45 late (7th business day, 2 attempts). dates bands
19–23. Date checks (business day, deadline, weekend/holiday → next business day, vague → ask once then deadline, next/this weekday, after deadline → offer deadline; refusing deadline = flat refusal). kit date table + ladder rules
24–25. Ask full first; floor = minimum_payment (card) or instalment_amount (loans). dates floor_field_by_type
26. Too much → split once (inst 1 = half rounded up to the cent by the deadline; inst 2 = rest, business day after inst 1, ≤ 10th business day after deadline). Refused split → floor once, rest stays overdue. Refused floor → flat refusal; attempt 2 = floor on the deadline. **gen.py + split_nodes.py**
26a. Customer asks for two parts → the split (ladder rule: treated as "too much"). Three or more → new plan (rule 41).
27. Amount floor..full accepted; below floor → offer floor once. ladder rules
28. "Can you make this payment today?". dates joined_lines suffix_one
29–31. Ladder state machine:
   today → no → attempt1_full (full, end of week)
   attempt1_full: too_much → split_offer; refuses → attempt2 if late else refused
   split_offer: accepts → split_rb (read both, "Do you confirm?" once) → create_promise inst 1 then 2; refuses/too_much → attempt1_floor (floor, end of week, rest overdue)
   attempt1_floor: refuses → attempt2 if late else refused
   attempt2: floor on deadline; refuses → refused
   today "too much" → split_offer as well (enter_1 rewired).
32. Hardship → sympathy, offer support transfer; yes → transferred/support, no → no_promise/hardship. kit
33. No discount/waiver; split of rule 26 is the only split. ladder rules
34–35. Read back, "Do you confirm?", record after yes; changes re-checked. kit / split_rb
36. Split: create_promise instalment 1 then 2, one read-back, one confirm. split_nodes.py
37. Record only after ok:true; one retry; second failure → no_promise/service_error (split: inst 1 failing twice → service_error; inst 2 failing after inst 1 recorded → promise, since one promise is recorded).
38. "You will receive a text message confirming this promise." promise close farewell
39. Already paid → one business day, close paid. kit situations.paid
40. Dispute → no_promise/dispute. kit
41. New plan → transfer restructuring. kit
42. Human: ask once, insist → transfer general, transferred/human. kit
43–44. Scam answer; unknown → no information. rules
45. Twice no talk → no_promise/refused (before verify: not_verified/declined). kit
46–47. Exactly one close_call, thanks and goodbye in the farewell. closes

## Choices
- Split dates offered: instalment 1 on the attempt-1 date (last business day this week, next week if today), instalment 2 on the deadline (a business day after instalment 1, well inside the 10-business-day limit). Conservative; the customer's own split dates are not re-checked in code (time).
- No add_note (brief: never used): notes false.
