"""Pre-demo checklist. Run it 15 minutes before presenting.

Usage:  .venv\\Scripts\\python scripts\\preflight.py
Checks keys, Qualcomm reachability and model, Resend key, both servers, demo data, and the
offline fallback recordings. Prints PASS / WARN / FAIL per line. Sends no email.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai import REPLAY_DIR, notes_key  # noqa: E402
from app.config import settings  # noqa: E402

results: list[tuple[str, str, str]] = []


def mark(level: str, what: str, detail: str = "") -> None:
    results.append((level, what, detail))
    print(f"[{level}] {what}{' - ' + detail if detail else ''}")


def http(url: str, headers: dict | None = None, timeout: float = 5) -> tuple[int, str]:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    s = settings()

    # Keys
    if s.qualcomm_api_key:
        mark("PASS", "QUALCOMM_API_KEY set")
    else:
        mark("FAIL", "QUALCOMM_API_KEY missing", "the app will run in Replay mode")
    mark("PASS" if s.internal_token else "FAIL", "INTERNAL_API_TOKEN set", "" if s.internal_token else "run scripts/setup_env.py")
    if s.resend_api_key and s.email_override_to:
        mark("PASS", "Resend configured", f"demo mail goes to {s.email_override_to}")
    else:
        mark("WARN", "Resend not fully configured", "emails will be recorded as skipped")

    # Qualcomm
    if s.qualcomm_api_key:
        try:
            from app.qualcomm import Qualcomm

            q = Qualcomm(s)
            models = q.models()
            llms = next((v for k, v in models.items() if "llm" in k.lower()), [])
            if s.qualcomm_model in llms:
                mark("PASS", "Qualcomm reachable, model available", s.qualcomm_model)
            else:
                mark("WARN", "Qualcomm reachable but model not listed", f"{s.qualcomm_model} not in {llms[:5]}")
            r = q.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=5)
            mark("PASS" if r.latency_ms < 15000 else "WARN", "Qualcomm warm-up call", f"{r.latency_ms} ms")
        except Exception as e:  # noqa: BLE001
            mark("FAIL", "Qualcomm call failed", getattr(e, "message", str(e))[:160])
        check = ROOT / "docs" / "qualcomm-check.json"
        mark("PASS" if check.exists() else "WARN", "check_qualcomm.py has been run", "" if check.exists() else "run it once with --apply")

    # Servers
    code, body = http("http://127.0.0.1:8000/health")
    if code == 200:
        mode = json.loads(body)["ai"]["mode"]
        mark("PASS" if mode == "live" else "WARN", "Backend running", f"AI mode: {mode}")
    else:
        mark("FAIL", "Backend not running on 127.0.0.1:8000", "start scripts/start.ps1")
    code, _ = http("http://localhost:3000/login")
    mark("PASS" if code == 200 else "FAIL", "Web app running on http://localhost:3000")

    # Data
    if s.internal_token and code == 200:
        c2, st = http("http://127.0.0.1:8000/state", {"x-internal-token": s.internal_token, "x-user-email": "vishal@decisionos.demo"})
        if c2 == 200:
            d = json.loads(st)
            n = len(d.get("meetings", []))
            mark("PASS" if n >= 1 else "WARN", "Demo data loaded", f"{n} meeting(s); simulated date: {d.get('simulated')}")
            if d.get("simulated"):
                mark("WARN", "Simulated date is still set", "click 'Use real date' before starting")

    # Offline fallback
    recorded = []
    for name in ("demo_meeting_0", "demo_meeting_1"):
        p = REPLAY_DIR / f"extract-{notes_key((ROOT / 'fixtures' / f'{name}.txt').read_text(encoding='utf-8'))}.json"
        if p.exists():
            recorded.append(json.loads(p.read_text(encoding="utf-8")).get("source", ""))
    live_rec = [r for r in recorded if "recorded live" in r]
    if len(live_rec) == 2:
        mark("PASS", "Offline fallback uses recorded Qualcomm replies")
    else:
        mark("WARN", "Offline fallback still uses hand-written replies",
             "once live works, restart the backend with QUALCOMM_RECORD=1 and extract both demo meetings")

    fails = sum(1 for r in results if r[0] == "FAIL")
    warns = sum(1 for r in results if r[0] == "WARN")
    print(f"\n{len(results) - fails - warns} pass, {warns} warn, {fails} fail")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
