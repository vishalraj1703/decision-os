# Go live: steps for the day you have the keys

About 20 minutes. Run every command from the `decision-os` folder in PowerShell.

## 1. Add the keys to `.env`
Open `decision-os\.env` and fill in:
```
QUALCOMM_API_KEY=...        # https://aisuite.cirrascale.com/api-keys
RESEND_API_KEY=...          # https://resend.com/api-keys
EMAIL_OVERRIDE_TO=...       # the email address you signed up to Resend with
```
Never paste keys into chat or commit `.env`. It's already in `.gitignore`.

## 2. Verify Qualcomm and apply the best settings (about 2 min)
```
.\.venv\Scripts\python scripts\check_qualcomm.py --apply
```
It tests 4 combinations (Imagine SDK or OpenAI-compatible, JSON prompting or tool calling) on the real demo notes and writes the winner into `.env`.
- **All combinations failed with AUTH:** the key is wrong.
- **"valid": false everywhere:** save `docs\qualcomm-check.json` and share it so the prompt can be tuned.

## 3. Verify email (30 s)
```
.\.venv\Scripts\python scripts\test_email.py
```
One email should arrive in `EMAIL_OVERRIDE_TO`. Check the spam folder too.

## 4. Record real replies for the offline fallback (2 min)
Stop the backend if it's running, then:
```
$env:QUALCOMM_RECORD="1"; .\.venv\Scripts\python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000
```
In a second window:
```
.\.venv\Scripts\python scripts\demo_seed.py
```
This saves the real Qualcomm replies for both demo meetings into `data\recorded\` (not committed to git, because it holds your real notes). If the Wi-Fi fails at the venue, start with `$env:QUALCOMM_REPLAY="1"` and the app replays them. The badge then reads "Replay mode", so say so out loud.

## 5. Normal start
Close the recording backend, then run:
```
.\scripts\start.ps1
```

## 6. Set up the demo state
1. Run `.\.venv\Scripts\python scripts\demo_seed.py`, or load only *last week's meeting* from **New meeting** so you can paste this week's notes live.
2. Sign in as Vishal (password: `DEMO_PASSWORD` in `web\.env.local`).
3. Make sure the header shows **Qualcomm Cloud AI**, not "Replay mode".

## 7. Preflight (15 minutes before presenting)
```
.\.venv\Scripts\python scripts\preflight.py
```
Everything should read PASS, except that "Simulated date" must *not* be set before you start.

## 8. Rehearse
Follow `docs\demo-script.md` with a stopwatch, three times.

## If something looks wrong in live mode
| Symptom | Fix |
|---|---|
| Owners guessed wrongly | The code backstop should catch it. If not, note the sentence and share it. |
| Extraction slow (>15 s) | Set `QUALCOMM_MAX_TOKENS=1500` in `.env`. Use shorter notes in the demo. |
| "AI reply could not be used" | Run step 2 again and check `docs\qualcomm-check.json`. Try `QUALCOMM_STRUCTURED_MODE=tool`. |
| No conflict card | It appears a few seconds after extraction, because it runs in the background. Check that both meetings exist. |
| Emails show "skipped" | `RESEND_API_KEY` or `EMAIL_OVERRIDE_TO` is missing. Restart the backend after editing `.env`. |
