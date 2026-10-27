# Gold set: 10 hand-labelled meeting notes

The accuracy scoreboard compares what the AI extracts with these answer keys. Each note is
written to tempt one or more typical mistakes (listed as `traps` in `gold.json`).

## Labelling rules (the same rules the product enforces)

- **A task needs a commitment.** "Maybe", "perhaps", "think about", "might look into" and
  questions are not tasks. They go in `not_items`.
- **An owner must be named for that item.** Someone who reports, worries about, flags or is
  asked about something is not its owner. A team ("the finance team") or "someone" is not
  a named owner. These are `UNKNOWN`.
- **A deadline must be stated for that item.** Copy the wording ("Friday", "once Raj fixes
  the bug"). Finished work has no deadline. Never infer one.
- **Decisions** need agreement or a final choice. Their owner and deadline are not scored.
- **A disagreement** with nothing decided is neither a task nor a decision.
- `evidence` is a phrase from the item's own sentence, after masking (phone numbers and
  emails become `[phone]` and `[email]`), so it must not include masked text.

## How an extraction is scored

An extracted item **matches** a gold item when the kinds are equal and the evidence
sentences overlap. Then, per layer (pass 1 alone, plus code checks, plus the Verifier):

- **Precision** = matched items / extracted items
- **Recall** = matched items / gold items
- **Hallucinations** = extracted items that are invented (no gold item), plus matched
  items with an invented owner (wrong person, or a person where the key says `UNKNOWN`)
  or an invented deadline (a date where the key says `UNKNOWN`).
- **Hallucination rate** = hallucinations / extracted items

Run it with a Qualcomm key: `.venv\Scripts\python scripts\eval_gold.py`. It writes
`results.json`, which the scoreboard shows.
