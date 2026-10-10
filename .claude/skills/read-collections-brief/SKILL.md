---
name: read-collections-brief
description: Read a bank's collections brief (a clean specification or raw material such as mails, policy extracts, memos and code lists) and write its rules as a rule table with a quote for every rule. Use in step 2 of build-phone-agent.
---

# Read a collections brief

Most failed calls come from one rule that was skipped. Read every line. Then write `out/<slot>/rules.json` in the
shape of `docs/interfaces.md` §1 (RuleTable): `{brief_id, sources[], rules[]}`.

## Sources

- List every document as a source with an id, a kind (`spec`, `mail`, `policy`, `memo`, `codelist`, `other`) and its
  date if it has one.
- Raw material: a later memo or mail **changes** an earlier policy. Keep the old rule, add the new one with
  `supersedes` pointing at it, and use the new one. Equal or missing dates: use the stricter rule and mark it
  `uncertain`.
- A code list (outcome codes, reasons, queues, product types) is data: copy the values exactly. When the tool API also
  lists allowed values, the tool API wins; note any mismatch.

## For every rule

- `quote`: the sentence from the source, copied exactly. A rule without a quote is `uncertain`.
- `type`: one of the types in §1. Use `free` only when nothing else fits.
- `node_hint`: the step of the call where it applies (identity, disclose, negotiate, record, close, or a global case).
- `applies_to`: `["all"]`, or a band, a product type, or multi-product customers.

## What a collections brief usually contains (check each one)

1. **Call variables**: the names the call starts with (customer id, names, title, the current time). Which one is
   "now" for every date rule.
2. **Opening**: the exact first sentence; words that must not be said before identity is verified; what counts as a
   confirmation of the person; how many asks before giving up.
3. **Someone else answers**: what may be said; callback window (days, hours, later than now); how many tries; wrong
   number; deceased.
4. **Identity**: which questions, in which order, the answer format the tool expects, how many wrong answers in total,
   retries that do not count, what to say on failure, refusing to answer.
5. **Disclosure**: what to say once verified (team, product wording, amounts, days late).
6. **Dates**: business days, weekend, the holiday list, bands by days late, the deadline per band, vague periods,
   "next/this weekday" meaning, dates after the deadline.
7. **Amounts**: full amount first, the floor per product type (which account field), what is accepted, below the floor.
8. **Persuasion**: the first ask, what counts as a refusal, attempts per band and what each attempt proposes.
9. **Special situations**: hardship, already paid, dispute, restructuring, human request, scam question, robot
   question, unanswerable questions, not wanting to talk.
10. **Recording**: read-back and confirmation, one promise per product, tool failure and retry, the sentence after a
    promise, changes after recording.
11. **Several products** (if any): order, per-product bands and deadlines, one confirmation, notes per product.
12. **Closing**: the outcome table (outcome, reason, when). Every row becomes an end of the plan.

Write the rule table before the plan. When you write the plan, every rule must land in a prompt, a route, a code
parameter or an end. A rule you could not place: say so in one line.
