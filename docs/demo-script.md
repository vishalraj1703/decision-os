# Decision OS: 3-minute demo script

**Before you go on stage**
1. The top bar shows the green **Qualcomm Cloud AI** badge, not "Replay (dev)". Open the site a minute early: Render's free tier takes 30–50 s to wake.
2. `fixtures/gold/results.json` is committed, so the **Accuracy scoreboard** shows real numbers (run `scripts\eval_gold.py` with the key first).
3. Sign in as **Vishal (Manager)**. **Clear all**, then add **last week's meeting** only. Paste this week's notes live.
4. Make one warm-up extraction 5 minutes before, so the first live call isn't a cold start.
5. Optional: `RESEND_API_KEY` and `EMAIL_OVERRIDE_TO` set, inbox open on your phone.
6. Backup: record replies with `QUALCOMM_RECORD=1` during rehearsal. If the network dies, set `QUALCOMM_REPLAY=1`. The badge then says "Replay": say it out loud.

This week's demo note is written to tempt two mistakes, and we say so: guessing an owner for "someone needs to follow up with finance", and turning a "maybe" about an offsite into a task. A live model may not make both; if Self-check shows no changes, say the checks had nothing to catch this time and point at the scoreboard instead.

| Time | Do | Say |
|---|---|---|
| 0:00 | The graph with last week's chain: Ravi → Asha → Meera | "Meetings end. Accountability shouldn't. This is last week's plan as a live graph." |
| 0:20 | **New meeting** → this week's meeting → **Extract**. Read the success line: items, the Verifier's removal, time | "One paste of messy notes. Two passes on Qualcomm Cloud AI: extract, then verify." |
| 0:50 | Click a row's **View source**; point at its **Trust receipt** ✓ quote ✓ meaning | "Every item cites its sentence. Quote found by code, meaning checked by a second model." |
| 1:20 | **Meetings → Self-check → View**: the offsite "maybe" struck through by the Verifier, the finance owner corrected by the code check | "Watch it delete its own mistake. Pass 1 guessed; the checks caught it, and the reason is on screen." |
| 1:45 | **Needs review**: Follow up with finance, owner UNKNOWN, the drafted question to Kavya → **Send question** | "It refuses to guess, and it doesn't leave you stuck: it drafts the question and picks who to ask." |
| 2:05 | **Conflicts**: AWS now vs Azure last week, both quotes | "It remembers last week. This reverses a decision. Two meetings, two quotes." |
| 2:25 | **What if**: Approve the API contract slips → drag to 3 days. Cards turn red | "One slip shows every team at risk, before anyone is late. Slack absorbs small slips." |
| 2:45 | **Meeting health** tile → breakdown; then the **Accuracy scoreboard** | "Every number has a formula. On ten hand-labelled notes: one prompt alone versus Decision OS." |
| 2:55 | Close | "It proves every extraction, refuses to guess, and predicts what breaks before it breaks." |

**Likely questions**
- *Why not one prompt?* The scoreboard: pass 1 alone versus code checks versus the Verifier, on the same 10 notes. It's a recorded run; the card says which model and when.
- *Doesn't the Verifier share the Extractor's blind spots?* That's why the code check runs first: the quote must be in the notes and the owner and deadline must be in that sentence. The Verifier can only remove or downgrade, never add.
- *Is the confidence number reliable?* No. It's self-reported by the model, and we label it that way. Trust comes from the evidence link and the checks.
- *Where does "5 days at risk" come from?* `d_j = max(0, max over predecessors d_p − slack_j)`. Slack comes from the deadlines, minus one day of work, and the manager can change it.
- *Privacy?* Emails and phone numbers are masked before any AI call, and the masked text is what's stored. The AI call log records model, latency and verdict, never text. **Delete** removes a meeting and everything taken from it. Keys stay on the server.
