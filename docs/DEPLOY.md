# Deploy Decision OS (shareable link)

Two free services:

| Part | Service | What it runs |
|---|---|---|
| Back end | **Render** | FastAPI + Qualcomm AI calls + SQLite |
| Web app | **Vercel** | Next.js dashboard (the link you share) |

The three secrets you need are in `deploy-secrets.txt` at the project root. That file is git-ignored: never commit it, and never paste it into chat.

---

## 1. Back end on Render (about 5 minutes)

1. Sign in at **render.com** with GitHub.
2. **New → Blueprint** → pick the `vishalraj1703/decision-os` repo. Render reads `render.yaml`.
3. It asks for the values marked *sync: false*:
   - `QUALCOMM_API_KEY` → your key (the same one as in `.env`)
   - `INTERNAL_API_TOKEN` → from `deploy-secrets.txt`
   - `APP_URL` → leave blank for now; fill it after step 2
   - `RESEND_API_KEY`, `EMAIL_OVERRIDE_TO` → optional (email alerts); leave blank to skip
4. **Apply**, then wait for "Live". Copy the URL, e.g. `https://decision-os-api.onrender.com`.
5. Check: open `https://<your-render-url>/health`. It should show `"mode": "live"`.

## 2. Web app on Vercel (about 5 minutes)

1. Sign in at **vercel.com** with GitHub → **Add New → Project** → import `decision-os`.
2. **Root Directory: `web`** (important). The framework is detected as Next.js.
3. Environment Variables:

   | Name | Value |
   |---|---|
   | `BACKEND_URL` | your Render URL (no trailing slash) |
   | `INTERNAL_API_TOKEN` | same value as on Render |
   | `NEXTAUTH_SECRET` | from `deploy-secrets.txt` |
   | `DEMO_PASSWORD` | from `deploy-secrets.txt` |
   | `NEXTAUTH_URL` | add after the first deploy (step 5) |

4. **Deploy**, then copy the URL, e.g. `https://decision-os.vercel.app`.
5. Vercel → Settings → Environment Variables → add `NEXTAUTH_URL` = that URL → **Redeploy**.
6. Render → Environment → set `APP_URL` = the same URL (used in email links).

## 3. Share it

Send people:
- the Vercel link
- the demo password (`DEMO_PASSWORD`)
- how to start: sign in as **Vishal (Manager)** → **Reset demo** loads two sample meetings, or **New meeting** to paste their own notes.

## Good to know (free tier)

- **First visit after ~15 min idle takes 30–50 s.** Render puts the back end to sleep. Open the link yourself a minute before a demo.
- **Data resets** when Render restarts or redeploys. Click **Reset demo** to reload the samples.
- Every paste uses your Qualcomm key. The demo password limits who can use it; change `DEMO_PASSWORD` on Vercel to cut access.
- Updates: push to `main` and both services redeploy automatically.
