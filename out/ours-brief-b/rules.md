# Rules (brief A + brief B; B wins)
- A1-4 opening/who/robot -> front spec
- A5-10 third party, callback today/next biz 10:00-19:00 -> front spec
- A11-15 identity (dob YYYY-MM-DD, phone_last4, 3 wrong total, swapped hint, decline twice) -> front spec
- A16-17 get_account, debt statement per product (B2: all products, one sentence each) -> back half code node, fixed tts
- A18-23 dates, bands, deadlines per product (B3) -> code node facts/date table
- A24-27 amounts, floor -> code facts
- A28-31 + B4/B5 ladder per product: ask all today; then per product attempt1 (end of week / next week if Friday last biz day), attempt2 late band floor on deadline -> negotiation node prompt with per-product attempt lines (time-limited build: one negotiation node, not ladder.py)
- A32 hardship -> transfer support / note hardship
- A34-38 + B7 one read-back, one confirm, create_promise per product, retry once, then note service_error (B11); confirmation sentence fixed
- A39/40 + B9 paid/dispute per product -> add_note, continue
- A41 + B10 restructuring transfer, no notes on any transfer
- A42 human, A43 scam, A44, A45
- Closing: B closing rule; outcome extracted at end of negotiation -> literal closes
Choice: due to 26-minute deadline, negotiation is a single conversation node with code-computed facts rather than per-product ladder graph.
