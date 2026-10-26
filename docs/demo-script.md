# Decision OS: 90-second demo script

**Before you go on stage**
1. `QUALCOMM_API_KEY` is set in `.env`, `scripts\check_qualcomm.py` passed, and the top bar shows the green **Qualcomm Cloud AI** badge, not "Replay (dev)".
2. `RESEND_API_KEY` and `EMAIL_OVERRIDE_TO` are set, and the inbox is open on your phone.
3. Run `.\.venv\Scripts\python scripts\demo_seed.py` to reset the app. Then ingest **last week's meeting** only. Paste this week's notes live.
4. Make one warm-up extraction 5 minutes before you present, so the first live call isn't a cold start.
5. Backup: record replies with `QUALCOMM_RECORD=1` during rehearsal. If the Wi-Fi dies, set `QUALCOMM_REPLAY=1`. The badge then says "Replay", so say it out loud.

| Time | Do | Say |
|---|---|---|
| 0:00 | Manager dashboard with last week's meeting: Ravi → Asha → Meera chain | "Decisions die in notes. Here is last week's checkout plan as a live graph." |
| 0:10 | Click **Load this week's meeting**, then **Extract** ("Asking the model…") | "This week's messy notes, sent to Qualcomm Cloud AI." |
| 0:20 | Point at **Follow up with finance: Owner UNKNOWN**, Needs Review | "Every other AI tool would invent an owner here. Ours refuses: the notes don't say who." |
| 0:30 | Click **view source** on Raj's row: the sentence is highlighted | "Every row links to the exact sentence. Nothing is a black box." |
| 0:40 | **Decision conflicts** card: AWS now vs Azure last week, both quotes | "It remembers last week. This reverses a decision. Two meetings, two quotes, side by side." |
| 0:50 | **Simulate date → Wed 28 Oct** | "Now Ravi misses his deadline." |
| 0:55 | Flowchart: Ravi red, Asha and Meera orange; bell; callout | "The delay cascades. Asha and Meera are at risk before anyone tells them." |
| 1:05 | Show the **overdue email** on your phone | "Real email, real inbox. The manager is copied." |
| 1:15 | Sign in as Asha (second browser): her task card says waiting on Ravi | "Each person sees only what they owe and what they're waiting on." |
| 1:25 | Close | "Decision OS doesn't summarize meetings. It makes them accountable, with an AI honest enough to say UNKNOWN." |

**Likely questions**
- *Is the confidence number reliable?* No. It's self-reported by the model, and we label it that way. Trust comes from the evidence link and the code checks: an owner must be named in the quoted sentence, or it becomes UNKNOWN.
- *What if the AI invents a quote?* Every quote is located in the stored notes. If it isn't found, we make one corrective retry. If it still isn't found, the item is rejected and listed, not shown.
- *Why three Qualcomm models?* Embeddings find past decisions with the same meaning, the reranker orders them, and the chat model confirms whether the pair is a real reversal.
- *Privacy?* Keys stay on the server, and the backend never logs raw notes. Notes are stored so the source can be shown. The Qualcomm Playground also keeps request history on its side.
