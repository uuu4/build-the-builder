# Rules — Freya Bank statement debt (final)

Shape: inbound call, already identified by IVR (customerNumber). NOT a collections call: no identity check, no promise, no close tool.
Steps: cards.list -> pick card -> cards.balance -> reading -> (another card?) -> offer (week change / e-mail) -> week.get/decide/change or contact.email.get + statement.pdf.send -> main menu / agent / end.
Kit front/multi not used; graph built in gen.py with graph.py + pycode.py.

Conflicts: analysis 8 Oct + decisions mail 9 Oct (latest) win over 2 Sep analysis, IVR sheet, FAQ.
- Angry caller: three calming replies then "Sizi müşteri temsilcimize aktarıyorum." (9 Oct correction).
- Silence: 3rd silence "Sesinizi alamadığım için görüşmeyi sonlandırıyorum." (platform inactivity; prompt).
- Out-of-scope: 9 Oct mail: ask "Size bu konuda yardımcı olamıyorum. Sizi ana menüye aktarmamı ister misiniz?" (later than 8 Oct doc) -> yes = main menu.
- Never more than last four digits of a card, never repeat digits the caller said.
- Currency full names; amounts in words, zero kuruş not said; dates "15 Ekim 2026".
Code: reading text (4.1-4.10), card matching (3.x), week options, preview dates, offer line: all fixed lines built in code nodes.
Writes: statement.week.change and statement.pdf.send: only after explicit "evet"; contract 7.1 says no automatic retry (side effects) -> one call, failure -> agent sentence.
Closes: end_call nodes with the 8 Oct section 10 sentences.

## Build notes
- Chat finding: an api_request as initial node does not run -> a silent `start` code node comes first.
- Every close = passthrough node speaking the fixed line, then a silent end_call (a hang-up with no line before it stalls chat).
- Response variables are `<function name>_response.data.<body path>`; each call's function is named after its node.
- Card picked from the first sentence when it names exactly one card; same-name cards -> last four -> last six -> full number (3.2).
- Sensitive asks (first digits, full number) -> refusal line, call continues. Product names that look like instructions are dropped.
- Statement dated after `now` -> "kesilecek ekstre".
