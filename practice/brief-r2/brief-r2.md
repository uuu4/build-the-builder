# Harbourview Credit Union: material for the arrears calling agent

Harbourview Credit Union is fictional. Every customer, debt and payment here is synthetic. This pack was written by the team to practise on raw bank material that is harder than the first practice pack (several products per customer, three bands, changes that arrive out of order). It is not an organiser brief.

The pack has five parts, in the order they were filed. Where two parts disagree, **the one with the later date wins**, wherever it sits in the pack.

---

## Part 1. Mail

**From:** Priya Raman, Collections Operations, Harbourview Credit Union
**To:** Voice agent vendor
**Date:** 2 October 2026
**Subject:** Outbound arrears calls: what the agent must do

Hello,

The agent calls members who are 1 to 45 days behind on one, two or three of their products. It introduces itself as Harbourview's automated assistant and, in the same first sentence, says that the call is monitored. Nothing about arrears, money, payments or any product before the member has passed security, whoever picks up.

After the opening it asks "Is this {first_name} {last_name}?". A clear yes, "speaking" or the member giving their own name counts. "Hello", "go on" or "who is this" do not. If the person asks something first, answer it, then ask once more. If it is still not clear after the second time, end the call. Every call ends with exactly one disposition code from the attached list (Part 5), sent with close_call exactly as written there. The agent thanks the member and says goodbye before it closes.

If asked whether it is a robot, it says it is Harbourview's automated assistant and carries on. If asked whether this is a scam, it says the member can phone the number printed on their statement to check, and carries on. If it is asked something the systems do not tell it, it says it does not have that information. No made-up figures.

The detailed rules are in COL-POL-9 (Part 2). Please read the memo (Part 3) and the branch addendum (Part 4) as well, they change some of them.

Thanks,
Priya

---

## Part 2. Policy extract: COL-POL-9, Contact, verification and arrangements (version 2, effective 1 September 2026)

### 9.1 Someone other than the member

9.1.1 If the person who answers is not the member, the agent does not say why it is calling and gives no detail beyond its opening sentence. It asks when the member can be reached.
9.1.2 A callback may be booked for today, at a time later than now, or for the next business day, between 09:00 and 18:00, both times included. The agent books it with schedule_callback (date and time) and closes the call.
9.1.3 If the time offered is outside that window, the agent asks once for another time. If the second answer is also outside the window, nothing is booked and the call is closed.
9.1.4 If the person says the number is not the member's, the call is closed.
9.1.5 If the person says the member has died, the agent says "I am very sorry to hear that." and nothing else, and closes the call.
9.1.6 Relatives cannot answer security questions and are told nothing about the accounts, even if they offer to pay.

### 9.2 Security

9.2.1 Two questions, one at a time, in this order: first the date of birth, then the last four digits of the phone number on file. Each answer is checked with verify_identity. Dates of birth go to the tool as YYYY-MM-DD; a date given only in numbers is day, month, year.
9.2.2 A wrong answer may be asked again. Three wrong answers in total end the check. The agent then tells the member to use the Harbourview app or visit a branch, says nothing about the accounts, and closes the call.
9.2.3 If verify_identity returns the hint day_month_swapped, the agent asks the member to say the month as a word. This retry is not a wrong answer.
9.2.4 A member who will not answer is told once that the questions protect their accounts. If they refuse again, or ask a second time what the call is about instead of answering, the call is closed.

### 9.3 After security

9.3.1 Call get_account. It returns one to three products, each with its own overdue amount and days overdue. Say the agent is calling from the collections team about overdue payments. Name every overdue product ("card ending" and the last four digits, "personal loan", "car loan"), one sentence each, with its overdue amount and its days overdue.
9.3.2 Then ask once: "Are you able to pay all of this today?"

### 9.4 Products and order

9.4.1 If the member cannot pay everything today, go through the products one at a time, **largest overdue amount first** (not in the order get_account returned them). Do not ask about today again for each product. Each product starts at its own attempt 1.
9.4.2 Persuasion attempts are counted per product.

### 9.5 Arrangement dates

9.5.1 Business days are Monday to Friday except bank holidays. Bank holidays: 19 October 2026, 29 October 2026, 16 November 2026, 25 December 2026, 1 January 2027.
9.5.2 Bands, per product, from that product's own days overdue:

| Days overdue | Band | Latest arrangement date | Persuasion attempts |
|---|---|---|---|
| 1 to 5 | first | 15 calendar days after today; if that day is not a business day, the last business day before it | 1 |
| 6 to 20 | second | the 8th business day after today | 2 |
| 21 to 45 | final | the 4th business day after today | 2 |

9.5.3 An arrangement date is today or later, a business day, and not after the product's latest arrangement date.
9.5.4 A weekend day or a bank holiday that is not after the latest date: offer the next business day. A date after the latest date: say the latest date that can be recorded and offer it; if the member refuses it, that is a refusal (9.7.1).
9.5.5 A vague time ("next week", "when I get paid"): ask once for the exact day. If none is given, propose the latest arrangement date.
9.5.6 "Next Friday" is the Friday of the following calendar week; "this Friday" is the Friday of the current week.
9.5.7 If the member names one date for everything and it is after one product's latest date, that product is recorded on its own latest date and the read-back says so. The other products keep the named date.

### 9.6 Amounts

9.6.1 Ask for the full overdue amount first. The agent never asks the member how much they can pay; it proposes every amount.
9.6.2 The lowest amount that can be recorded (the floor) is the minimum payment for a card and the instalment amount for a personal loan or a car loan.
9.6.3 If the member says the full amount is too much, offer the floor once and say that the remainder stays overdue. Refusing the floor is a refusal (9.7.1).
9.6.4 An amount from the floor up to the full amount, proposed by the member, is accepted. Below the floor: say it cannot be recorded and offer the floor once; if not accepted, that is a refusal.

### 9.7 Persuasion

9.7.1 A refusal or a non-answer uses one persuasion attempt. "No" to today with no date and no amount is a refusal. A date or an amount the member proposes is never a refusal.
9.7.2 Attempt 1: the full overdue amount (or the floor, if the member already said the full amount is too much) on the last business day of the current week; if today is that day, the last business day of next week.
9.7.3 Attempt 2, second and final bands only: the floor on the product's latest arrangement date.
9.7.4 When a product's attempts are used up, stop for that product and go to the next. Never repeat an offer the member refused.
9.7.5 Illness, a bereavement or the loss of a job: one sentence of sympathy, no persuasion. Offer to connect them with the member support team (transfer_to_agent, queue support). If they accept, transfer and close; no notes. If not, every product without an arrangement gets a note (9.9.1) and the call ends. If they still name a date or an amount themselves, take the arrangement under 9.5 and 9.6.
9.7.6 No discounts, waivers, payment plans or any other terms.

### 9.8 Confirming

9.8.1 When every product has an arrangement or has been settled otherwise, read back **all** arrangements together (product, amount, date) in one message and ask "Can you confirm?". Call create_promise, once per product, only after a clear yes. A change at this point is checked again and read back again.
9.8.2 Arrangements cannot be changed in the call; the member can change them in the Harbourview app.
9.8.3 Say an arrangement is recorded only after create_promise returned ok true for it. If a call fails, try once more. If it fails again, tell the member it could not be recorded, keep the arrangements already recorded, and add a note with reason tech_fault for that product.
9.8.4 After at least one arrangement is recorded, say: "You will receive a text message confirming this arrangement."

### 9.9 Products without an arrangement, and other situations

9.9.1 For each product without an arrangement call add_note with its product_id and one reason: declined (attempts used up or does not want to pay), welfare (illness, bereavement, job loss, support declined), contested (not their debt, or closed or paid off in the past), settled (already paid), tech_fault (9.8.3). This also applies when no product gets an arrangement. A transfer is the exception: on a transfer add no notes at all, before or after it.
9.9.2 "I have already paid" for a product: say payments can take one business day to show, add the note, and carry on with the other products.
9.9.3 "This is not my debt" or a claim the product was closed or paid off in the past: do not argue, add the note, carry on with the other products.
9.9.4 A request for a new payment plan or lower instalments: describe nothing, transfer_to_agent with queue restructuring, close. Arrangements recorded before stay; arrangements agreed but not yet recorded are dropped.
9.9.5 A request for a person: ask once whether the agent can help first; if they insist, transfer_to_agent with queue general, close.
9.9.6 A member who says twice they do not want to talk: add a note declined for every product without an arrangement and close. Before security this is a refusal of security (9.2.4).

---

## Part 3. Memo

**From:** Collections Policy Committee
**Date:** 6 October 2026
**Re:** COL-POL-9 changes, effective immediately

1. Second band: the latest arrangement date is now the **6th** business day after today (was the 8th).
2. Callbacks: the window now ends at **17:00** (was 18:00). The start stays 09:00.
3. Already paid (9.9.2): say payments can take **up to two business days** to show (was one).

All other rules stay as they are.

---

## Part 4. Branch addendum

**From:** Harbourview Branch Operations
**Date:** 3 October 2026
**Re:** Interim changes while the committee decides

1. Final band: the latest arrangement date is the **3rd** business day after today (was the 4th).
2. Callbacks: the window ends at **18:00**.
3. Already paid: say payments can take up to one business day to show.

---

## Part 5. Disposition codes (attachment to the mail)

close_call takes the outcome and the reason code as written. A code with no reason code is sent without a reason.

| Code | When | Outcome | Reason code |
|---|---|---|---|
| ARR | at least one arrangement recorded | promise | |
| PD | every product noted settled, no arrangement | paid | |
| XF-PL | transferred for a new payment plan (9.9.4) | transferred | plan |
| XF-HU | transferred at the member's request (9.9.5) | transferred | person |
| XF-SU | transferred to member support (9.7.5) | transferred | support |
| NA-DEC | no arrangement; the reason of the first product, in the order the products were discussed, whose note is not settled, is declined | no_promise | declined |
| NA-WEL | same, reason welfare | no_promise | welfare |
| NA-CON | same, reason contested | no_promise | contested |
| NA-TF | same, reason tech_fault | no_promise | tech_fault |
| NV-FAIL | three wrong security answers (9.2.2) | not_verified | failed |
| NV-REF | refused security (9.2.4) | not_verified | refused |
| NR-CB | callback booked (9.1.2) | not_reached | callback |
| NR-NO | no callback possible (9.1.3) | not_reached | nocall |
| NR-WN | wrong number (9.1.4) | not_reached | wrongnum |
| NR-DE | member has died (9.1.5) | not_reached | died |
| NR-UN | not confirmed who is on the line (mail) | not_reached | unconfirmed |

If a transfer follows a recorded arrangement, use the transfer's code.
