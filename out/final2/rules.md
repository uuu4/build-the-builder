# final2 — Freya Bank statement debt: rules and where they go

## Shape check
Not a collections call. Inbound, caller already identified by the IVR (`customerNumber`, `now`). Steps (flow drawing, analysis 8 Oct, examples):
cards.list → (choose card) → cards.balance → reading → [another card?] → contact.email.get → offer (week change / e-mail) →
statement.week.get → week options → statement.week.decide (preview) → explicit yes → statement.week.change, or
e-mail confirm → statement.pdf.send. Ends: main menu, agent, (IVR login for someone else's card). No close tool, no promise.
=> Graph built by hand in gen.py with graph.py/pycode.py. Kit front (identity) does not apply: the IVR did identity, no question is asked.

## Conflicts resolved (later written date wins)
- Analysis 2 Sep < kickoff mails 24/29 Sep < contract 1 Oct < transcript 7 Oct < analysis 8 Oct < recap mail 9 Oct.
- Angry caller: 9 Oct recap: three calming replies, then "Sizi müşteri temsilcimize aktarıyorum." (beats "two"). Prompt-level only (no counter, time).
- Out-of-scope question: 9 Oct recap (later than 8 Oct analysis 8.4): ask "Size bu konuda yardımcı olamıyorum. Sizi ana menüye aktarmamı ister misiniz?"; yes → main menu ("Sizi ana menüye aktarıyorum."), no → back to the flow (offer if debt already read, else card choice). Node oos_ask.
- Card number: 9 Oct: production returns full numbers; never say more than last four. Last-six and full-number steps built (match_card), they work with full numbers; with the masked test list last-six falls back to last four.
- Second identity factor in drawing: never built (8 Oct §2). Not asked.
- Contact.email.get before the offer (8 Oct, replaces Sept "after asking").
- Example 5 says spouse card → "routes to main menu"; analysis says IVR login step. Scoring examples win: close_security says the security sentence then main menu.

## Rules → node
1. Never ask customer number / PIN / code (system prompt).
2. No eligible card (404 FB_IVR_CHANNEL_102 or empty) → close_nocard. cards.list 500/timeout → close_fail (agent).
3. One card → read directly; several → "Hangi kartınızın borcunu öğrenmek istersiniz? Örneğin, X veya Y diyebilirsiniz." (≤2 own names) — cards_code/ask_card.
4. Same name → last four; same last four → last six; same last six → full number (fixed lines, match_card).
5. "All cards" → ask again, costs a try; three tries → close_tries. Repeat request costs no try.
6. Supplementary-only card (isMainCard false) → not eligible, choose another.
7. Reading order: intro "Sonu <last4 digit by digit> ile biten <name> kartınıza ait <date> tarihinde kesilen ekstre" + TL (3 cases by remainingMinPayment vs minPayment) + USD/EUR/GBP + one no-debt sentence (missing blocks left out) + automatic payment remainder (after due date, flag Y) + due date ("bugündür" if today; passed → total debt) — reading_code, spoken as one fixed line.
8. Card-level NO_DEBT → 4.7 sentence with total; single card → main menu; several → another card?
9. Amounts in words (lira/kuruş, dolar/euro sent, sterlin peni, no "sıfır kuruş"); currency names in full; dates "5 Ekim 2026".
10. Several cards → "Başka bir kartınızın borcunu öğrenmek ister misiniz?" before the offer.
11. Offer by registered e-mail: both / week only (no flag exists for the yearly right: always offered).
12. Pay → close_pay; agent → close_agent; dispute → close_dispute; service failure → close_fail / close_week_fail (agent).
13. E-mail: only latest statement, only registered address; old month/paper/other address → say so (email_old_node) and offer latest; confirm "Ekstrenizi … adresine göndermemi ister misiniz?"; send only after clear yes; "gönderildi" only after DONE (pdf_code) → close_sent. No auto retry on send (contract §7).
14. Week: read current week + next dates (joint statement: both cards) → ask change → offer other weeks only → decide preview → joint note → "Onaylıyor musunuz?" → only explicit "evet" (hedged asks again) → change once (no retry) → done line with preview dates + main menu.
15. Week named up front ("3. haftaya al") → current week read, then straight to preview and confirmation.
16. Never more than last four digits; never repeat digits the caller said; PIN volunteered → not used (prompt).
17. Someone else's card → close_security. Not Turkish → close_lang.
18. Every conversation node: max_turns → close_tries ("Size şu anda yardımcı olamıyorum. Sizi ana menüye aktarıyorum.").
19. Silence: third silence → "Sesinizi alamadığım için görüşmeyi sonlandırıyorum." — not built (no documented idle hook); left to the platform.

## Platform notes
- Pre_actions of the initial node are skipped: the graph starts with a code node `start`.
- chat replay returns 504 on end_call turns (a bare end node does the same): not a workflow fault.
