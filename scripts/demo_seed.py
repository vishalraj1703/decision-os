"""Reset the running app and ingest the two demo meetings (last week, then this week).

Usage:  .venv\\Scripts\\python scripts\\demo_seed.py
Talks to the running FastAPI on 127.0.0.1:8000 as the manager, using INTERNAL_API_TOKEN from .env.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402

API = "http://127.0.0.1:8000"


def call(method: str, path: str, body: dict | None = None) -> dict:
    s = settings()
    req = urllib.request.Request(
        API + path, method=method, data=json.dumps(body or {}).encode(),
        headers={"content-type": "application/json", "x-internal-token": s.internal_token,
                 "x-user-email": "vishal@decisionos.demo"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> None:
    call("POST", "/admin/reset")
    for f, d in (("demo_meeting_0.txt", "2026-10-19"), ("demo_meeting_1.txt", "2026-10-26")):
        notes = (ROOT / "fixtures" / f).read_text(encoding="utf-8").strip()
        r = call("POST", "/extract", {"notes": notes, "meeting_date": d})
        print(f"{f}: {r['items']} items, {r['attempts']} call(s), {r['latency_ms']} ms, model {r['model']}")
    print("Seeded. Open http://localhost:3000")


if __name__ == "__main__":
    main()
