# Decision OS

AI meeting intelligence on the **Qualcomm Cloud AI Playground**. Paste messy meeting notes and get a live, evidence-backed decision graph: owners, deadlines, dependencies, risks and contradictions across meetings. The AI **refuses to guess**: if the notes don't say who owns a task, the row reads **UNKNOWN** and goes to a Needs Review queue.

Source of truth: `Decision_OS_Scope_Freeze_Report.pdf` (v1.0).

## Quick start (Windows PowerShell)

Requires Python 3.10+ (tested on 3.12) and Node 20+ (tested on 24).

```powershell
.\scripts\start.ps1
```

On first run it installs everything and creates `.env` and `web\.env.local` with fresh secrets. Then open http://localhost:3000. The login password is `DEMO_PASSWORD` in `web\.env.local`.

To run the pieces by hand:

```powershell
python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt
cd web; npm ci; cd ..
.\.venv\Scripts\python scripts\setup_env.py
.\.venv\Scripts\python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
cd web; npm run dev          # second terminal
.\.venv\Scripts\python scripts\demo_seed.py   # optional: reset and load the two demo meetings
```

### Keys (all in `.env`, never committed)

| Variable | What for |
|---|---|
| `QUALCOMM_API_KEY` | Key from https://aisuite.cirrascale.com/api-keys. Without it the app runs in **Replay (dev)** mode, badged in the UI, with only the two bundled demo meetings. |
| `QUALCOMM_CLIENT`, `QUALCOMM_STRUCTURED_MODE` | Set from the result of `scripts\check_qualcomm.py`. |
| `RESEND_API_KEY`, `EMAIL_OVERRIDE_TO` | Real email. The free tier only delivers to your own Resend account address until a domain is verified, so set `EMAIL_OVERRIDE_TO` to that inbox. |

**First thing to run with a key:** `.\.venv\Scripts\python scripts\check_qualcomm.py`. It sends the spec's demo notes through the Imagine SDK and the OpenAI-compatible route, each with JSON prompting and tool calling. It validates the output against the schema, checks the quotes, tests embeddings and the reranker, times the runs, and prints the settings to use.

## How it works

```
Browser ──► Next.js (NextAuth session, /api/backend proxy) ──► FastAPI (127.0.0.1:8000) ──► Qualcomm Cloud AI
                                    internal token + user email        SQLite, apscheduler, Resend
```

0. **Redaction** (`redact.py`): emails, phone numbers and long ID numbers become `[email]`, `[phone]` and `[id]` before any AI call. The masked text is also what is stored and highlighted.
1. **Extraction** (`backend/app/extract.py`): one Qualcomm chat call returns the spec 5.2 JSON. If the reply is invalid, or a quote isn't in the notes, there is **one corrective retry**; after that, nothing is saved.
2. **Honesty checks in code**, not only in the prompt:
   - An owner must be named in the item's own sentence, or it becomes UNKNOWN.
   - A team ("finance") is never treated as an owner.
   - Deadline wording must be in the sentence.
   - Every quote is located in the stored notes, which is what the highlight uses. Unverifiable items are rejected and listed.
   - **Pass 2, the Verifier** (`verifier.py`): a second Qualcomm call re-reads the notes and judges each item. It can only remove an item (a "maybe", a question) or set an owner or deadline to UNKNOWN; it never adds or rewrites. If it fails twice, items are kept and marked "not verified". `VERIFIER_ENABLED=false` turns it off.
   - **Self-check replay:** pass 1 is stored beside the final result, each change tagged *Code check* or *Verifier*. **Trust Receipt** on every item: quote found, meaning verified, confidence.
3. **Dates** (`dates.py`):
   - "Oct 27", "tomorrow" and "next Friday" become exact dates.
   - "Friday" and "the 20th" become a likely date marked **needs confirmation**.
   - "once Raj finishes" means it follows its dependency.
   - "soon" becomes UNKNOWN.
4. **Needs Review:** tasks missing an owner or deadline, and risks missing an owner. The manager can assign an owner, set or confirm a deadline, mark for a follow-up meeting, or discard. **Clarify Loop** (`clarify.py`): each flag comes with a drafted question, sent to the person the sentence names, the team it mentions, or the task owner (in the app, and by email when Resend is set).
5. **Conflicts** (`conflicts.py`):
   - Qualcomm **embeddings** find earlier decisions with the same meaning.
   - The **reranker** orders them.
   - The **chat** model confirms a real reversal.
   - The card shows both quotes from both meetings.
6. **Cascade** (`cascade.py`, apscheduler hourly, plus the demo clock): past-deadline tasks that aren't done turn red, and everything downstream turns orange. The manager and the affected owners are notified.
   - **What-if** (`risk.py`): before anything is late, drag a task's delay from 0 to 10 days. `d_j = max(0, max over predecessors d_p − slack_j)`. Slack comes from the deadlines (days after the latest input, minus one day of work) and can be overridden per task. Reports teams affected and days at risk.
   - **Health Score** (`health.py`): `100 × (0.30 O + 0.25 D + 0.20 V + 0.15 (1 − A) + 0.10 (1 − C))` per meeting, with a clickable breakdown. It rises as gaps are fixed.
7. **Email** (`emailer.py`) has exactly three triggers: due within 24h, overdue (manager in cc), and dependency complete. Every send is deduplicated, logged and protected by an idempotency key.
8. **Dashboards:**
   - **Manager:** stats bar with Health Score, AI warning callout, React Flow graph (max 7 nodes plus "and N more") with the what-if slider, action table with Trust Receipts and CSV / Jira JSON export, Needs Review with questions, conflict cards, team strip, meetings with self-check and delete, accuracy scoreboard, AI call log, bell.
   - **Employee:** own tasks only, a status dropdown, waiting-on and blocking lists, dependency updates, and Mark Blocked.

9. **Accuracy scoreboard** (`gold.py`, `fixtures/gold/`): 10 hand-labelled notes, each built around typical mistakes. `scripts/eval_gold.py` runs them on live Qualcomm and measures precision, recall and hallucinations for pass 1 alone, plus code checks, plus the Verifier. The saved `results.json` is what the manager sees: a recorded run, never computed on page load.
10. **Privacy controls:** every AI call is logged (purpose, model, latency, verdict; never text) in the **AI call log**. **Delete** on a meeting removes it and everything taken from it; **Clear all** wipes every meeting. Each evidence quote carries a fingerprint (SHA-256) in the exports.

## Tests

```powershell
.\.venv\Scripts\python -m pytest tests     # 89 tests, one file per build block and step
cd web; npm run build                       # typecheck + production build
.\.venv\Scripts\python scripts\eval_gold.py   # accuracy on the gold set (needs QUALCOMM_API_KEY; ~25 calls)
```

`test_block6_cascade.py::test_overdue_cascades_downstream` depends on the real date: on or after 28 Oct 2026 the task is already overdue when it is extracted, so the "newly overdue" check finds nothing.

## Scope freeze checklist (spec chapter 11), honest status

| Area | Status |
|---|---|
| AI extraction: `/extract`, Pydantic schema, one corrective retry, SQLite | Built and tested. **Live Qualcomm call not yet verified**: no key so far. |
| Ambiguity: UNKNOWN owner and deadline, grey italic `?` rows, Needs Review badge and queue, Resolve | Built and tested |
| Evidence: non-empty quote, Evidence column, view source with highlight, notes stored | Built and tested. Quotes are also verified against the notes, which goes beyond the spec. |
| Conflicts: topic and time per meeting, comparison, stored with both quotes, panel, Resolve | Built and tested. Matching uses embeddings, a reranker and chat instead of an exact topic string. |
| Flowchart: React Flow auto-layout, status colors only, cap at 7, callout, real-time | Built. Seen in the browser. |
| Manager dashboard: stats, callout, table (6 columns), team strip, bell with deep links | Built |
| Employee dashboard: NextAuth login, task count, cards, status writes back within ~1 s, dependency panel, Mark Blocked | Built and tested |
| Email: Resend, 3 triggers, real inbox | Built and tested with Resend stubbed. **Real delivery not yet verified**: no key so far. |
| Deadline cascade: hourly scheduler, overdue, downstream at risk, red/orange, bell, strip, stats | Built and tested |
| Role-based access: employee sees own tasks, manager sees all, two roles, sessions persist | Built and tested |

## Hackathon documentation (EP-01), honest status

| Area | Status |
|---|---|
| Redact before AI (emails, phones, IDs) | Built and tested. Pattern-based; names are kept because ownership needs them. |
| Two passes: Extract, then Verify | Built and tested, and run locally on live Qualcomm (Llama-3.3-70B): the demo note's "maybe" is removed, the unowned finance task is kept as UNKNOWN. |
| Self-correction replay, Trust Receipt | Built and tested |
| Clarify Loop (drafted question per flag) | Built and tested. Email delivery depends on Resend. |
| Dependency graph with slack, what-if slider, "N teams, X days at risk" | Built and tested, including the documented example (Design +5 → 2 teams, 5 days). |
| Health Score with published formula and breakdown | Built and tested |
| CSV and Jira-ready JSON export | Built and tested |
| 10-note gold set, precision / recall / hallucinations, pass 1 vs both passes | Built, tested and measured on 28 Oct 2026 (Llama-3.3-70B, 39 answers): pass 1 alone 91% precision, 100% recall, 7 hallucinations; with both passes 97% precision, 97% recall, 1 hallucination. |
| Audit log of every AI call | Built and tested |
| Purge a meeting or everything | Built and tested |
| Long notes split by topic | Not built: notes are limited to 12,000 characters. |
| Encryption at rest, Postgres with row-level security | Not built: SQLite on one instance. Stated as the production path. |
| Contact-center mode, Teams / Zoom ingestion, on-device mode | Roadmap |

## Deviations from the spec (and why)

- **Notes are stored, masked.** The documentation says raw notes aren't retained, but the evidence highlight needs them. We store the redacted text (no emails or phone numbers), never log it, and **Delete** removes it. The Qualcomm Playground also keeps request history in your account.
- **Slack assumes one day of work** per task, because the notes give deadlines, not durations. The manager can override it.
- **Confidence** is shown, but labelled *self-reported by the model*, because it isn't a calibrated accuracy.
- **Email templates** are Gmail-safe inline HTML rendered in Python, not React Email. React Email would need a Node renderer beside the Python sender.
- **Demo clock:** "Simulate this date" and "Run check now" let the cascade happen live on stage. A badge shows when the date is simulated.
- **Replay (dev) mode** exists for building without a key. It is always badged, and the demo should run live.

## Repo layout

```
backend/app/   config, qualcomm (client), ai (live/replay, audit log), schema, prompts, redact, extract, verifier,
               dates, evidence, roster, db, service, conflicts, cascade, risk (what-if), health, clarify,
               export, gold (scoring), emailer, main (FastAPI)
web/           Next.js 16 app: login, manager and employee dashboards, NextAuth, proxy, React Flow
scripts/       check_qualcomm.py (--apply), eval_gold.py, test_email.py, preflight.py, setup_env.py, demo_seed.py,
               make_replay.py, start.ps1
fixtures/      demo meetings, dev replay replies, gold/ (10 labelled notes, results.json)
tests/         89 tests (one file per block and step)
docs/          GO-LIVE.md (steps for key day), demo-script.md
```
