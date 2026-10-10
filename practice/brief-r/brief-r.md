# Northwind Bank: material for the arrears calling agent

Northwind Bank is fictional. Every customer, debt and payment here is synthetic. This pack was written by the team to practise on raw bank material. It is not an organiser brief.

The pack has four parts, in the order the bank sent them. Where they disagree, the later part wins.

---

## Part 1. Mail

**From:** Hannah Oduya, Head of Arrears, Northwind Bank
**To:** Voice agent vendor
**Date:** 2 October 2026
**Subject:** Outbound arrears calls: what the agent must do

Hi all,

As discussed, the agent will call customers who are 1 to 45 days behind on one product. It calls on our behalf, so it introduces itself as Northwind Bank's automated assistant. In the first sentence it must also say that the call is recorded. Nothing about arrears, money, payments or the product before the customer has passed security. That goes for anyone who picks up, family included.

After the opening it asks "Am I speaking to {first_name} {last_name}?". Only a clear yes, "speaking", "that's me" or the customer giving their own name counts. Hello, go ahead or who's this do not. If the person asks something first, answer it, then ask once more. If it is still not clear after the second time, end the call. The disposition codes are in the list I attach (Part 4); please make sure the agent closes every call with exactly one of them through close_call, outcome and reason as written there, and that it thanks the customer and says goodbye before it closes.

People will ask if it is a robot. It says it is Northwind Bank's automated assistant and carries on. If they ask whether this is a scam, it tells them they can call the number on the back of their card to check, and carries on. If it is asked something the systems do not tell it, it says it does not have that information. No made-up figures, ever.

The detailed rules are in the policy extract (Part 2). Note the memo (Part 3), it changes a few of them.

Thanks,
Hannah

---

## Part 2. Policy extract: COL-POL-7, Contact, verification and arrangements (version 4, effective 1 September 2026)

### 7.1 Someone other than the customer

7.1.1 If the person who answers is not the customer, the agent does not say why it is calling and gives no detail beyond its opening sentence. It asks when the customer can be reached.
7.1.2 A callback may be booked for today, at a time later than now, or for the next business day, between 09:00 and 18:00, both times included. The agent books it with schedule_callback (date and time) and closes the call.
7.1.3 If the time offered is outside that window, the agent asks once for another time. If the second answer is also outside the window, nothing is booked and the call is closed.
7.1.4 If the person says the number is not the customer's, the call is closed.
7.1.5 If the person says the customer has passed away, the agent says "My condolences." and nothing else, and closes the call.
7.1.6 Family members cannot answer security questions and are told nothing about the account, even if they offer to pay.

### 7.2 Security

7.2.1 Two questions, one at a time, in this order: first the last four digits of the phone number on file, then the date of birth. Each answer is checked with verify_identity. Dates of birth go to the tool as YYYY-MM-DD; a date given only in numbers is day, month, year.
7.2.2 A wrong answer may be asked again. Three wrong answers in total end the check. The agent then tells the customer to use the Northwind app or visit a branch, says nothing about the account, and closes the call.
7.2.3 If verify_identity returns the hint day_month_swapped, the agent asks the customer to say the month as a word. This retry is not a wrong answer.
7.2.4 A customer who will not answer is told once that the questions protect their account. If they refuse again, or ask a second time what the call is about instead of answering, the call is closed.

### 7.3 After security

7.3.1 Call get_account. Say the agent is calling from the arrears team about an overdue payment, name the product ("credit card ending" and the last four digits, "personal loan", "car loan"), and give the overdue amount and the number of days overdue.
7.3.2 Then ask: "Are you able to pay this amount today?"

### 7.4 Arrangement dates

7.4.1 Business days are Monday to Friday except bank holidays. Bank holidays: 20 October 2026, 3 November 2026, 25 December 2026, 1 January 2027.
7.4.2 Bands:

| Days overdue | Band | Latest arrangement date | Persuasion attempts |
|---|---|---|---|
| 1 to 10 | standard | 10th business day after today | 1 |
| 11 to 45 | priority | 5th business day after today | 2 |

7.4.3 An arrangement date is today or later, a business day, and not after the latest arrangement date.
7.4.4 A weekend day or a bank holiday that is not after the latest date: offer the next business day. A date after the latest date: say the latest date that can be recorded and offer it; if the customer refuses it, that is a refusal (7.6.1).
7.4.5 A vague time ("next week", "when I get paid"): ask once for the exact day. If none is given, propose the latest arrangement date.
7.4.6 "Next Friday" is the Friday of the following calendar week; "this Friday" is the Friday of the current week.

### 7.5 Amounts

7.5.1 Ask for the full overdue amount first. The agent never asks the customer how much they can pay; it proposes every amount.
7.5.2 The lowest amount that can be recorded (the floor) is the minimum payment for a credit card and the instalment amount for a personal loan or a car loan.
7.5.3 If the customer says the full amount is too much, offer the floor once and say that the remainder stays overdue. Refusing the floor is a refusal (7.6.1).
7.5.4 An amount from the floor up to the full amount, proposed by the customer, is accepted. Below the floor: say it cannot be recorded and offer the floor once; if not accepted, that is a refusal.

### 7.6 Persuasion

7.6.1 A refusal or a non-answer uses one persuasion attempt. "No" to today with no date and no amount is a refusal. A date or an amount the customer proposes is never a refusal.
7.6.2 Attempt 1: the full overdue amount (or the floor, if the customer already said the full amount is too much) on the last business day of the current week; if today is that day, the last business day of next week.
7.6.3 Attempt 2, priority band only: the floor on the latest arrangement date.
7.6.4 When the attempts are used up, stop and close. Never repeat an offer the customer refused.
7.6.5 Illness, a bereavement or the loss of a job: one sentence of sympathy, no persuasion. Offer to connect them with the customer welfare team (transfer_to_agent, queue support). If they accept, transfer and close; if not, close. If they still name a date or an amount themselves, take the arrangement under 7.4 and 7.5.
7.6.6 No discounts, waivers, payment plans or any other terms.

### 7.7 Confirming

7.7.1 Read back the product, the amount and the date and ask "Can you confirm?". Call create_promise only after a clear yes. A change at this point is checked again and read back again.
7.7.2 One arrangement per call. It cannot be changed in the call; the customer can change it in the Northwind app.
7.7.3 Say the arrangement is recorded only after create_promise returns ok true. If it fails, try once more. If it fails again, tell the customer it could not be recorded and close.
7.7.4 After a recorded arrangement, say: "You will receive a text message confirming this arrangement."

### 7.8 Other situations

7.8.1 "I have already paid": say payments can take one business day to show, take no arrangement, close.
7.8.2 "This is not my debt" or a claim the product was closed or paid off in the past: do not argue, no arrangement, close.
7.8.3 A request for a new payment plan or lower instalments: describe nothing, transfer_to_agent with queue restructuring, close.
7.8.4 A request for a person: ask once whether the agent can help first; if they insist, transfer_to_agent with queue general, close.
7.8.5 A customer who says twice they do not want to talk: close. Before security this is a refusal of security (7.2.4).
7.8.6 add_note is not used in these calls.

---

## Part 3. Memo

**From:** Arrears Policy Committee
**Date:** 6 October 2026
**Re:** COL-POL-7 changes, effective immediately

1. Priority band: the latest arrangement date is now the **6th** business day after today (was the 5th).
2. Callbacks: the window now ends at **17:00** (was 18:00). The start stays 09:00.
3. Already paid (7.8.1): say payments can take **up to two business days** to show (was one).

All other rules stay as they are.

---

## Part 4. Disposition code list (attachment to the mail)

close_call takes the outcome and the reason code as written. A code with no reason code is sent without a reason.

| Code | When | Outcome | Reason code |
|---|---|---|---|
| PTP | at least one arrangement recorded | promise | |
| PAID | customer says they already paid (7.8.1) | paid | |
| TRF-RS | transferred for a new payment plan (7.8.3) | transferred | restructure |
| TRF-AG | transferred at the customer's request (7.8.4) | transferred | agent_request |
| TRF-WF | transferred to customer welfare (7.6.5) | transferred | welfare |
| NP-REF | attempts used up, or does not want to talk (7.6.4, 7.8.5) | no_promise | refusal |
| NP-HS | illness, bereavement or job loss, declined the transfer (7.6.5) | no_promise | financial_difficulty |
| NP-DS | disputes the debt (7.8.2) | no_promise | disputed |
| NP-ERR | arrangement could not be recorded twice (7.7.3) | no_promise | system_error |
| NV-F | three wrong security answers (7.2.2) | not_verified | id_fail |
| NV-R | refused security (7.2.4) | not_verified | id_refused |
| NR-CB | callback booked (7.1.2) | not_reached | cb_booked |
| NR-NCB | no callback possible (7.1.3) | not_reached | cb_none |
| NR-WN | wrong number (7.1.4) | not_reached | wrong_no |
| NR-DC | customer passed away (7.1.5) | not_reached | deceased |
| NR-UC | not confirmed who is on the line (mail) | not_reached | no_confirm |

If a transfer follows a recorded arrangement, use the transfer's code.
