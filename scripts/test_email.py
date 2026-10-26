"""Send ONE test email through Resend to EMAIL_OVERRIDE_TO, to prove delivery works.

Usage:  .venv\\Scripts\\python scripts\\test_email.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.emailer import _layout  # noqa: E402


def main() -> int:
    s = settings()
    if not s.resend_api_key:
        print("RESEND_API_KEY is not set in .env (create one at https://resend.com/api-keys).")
        return 2
    if not s.email_override_to:
        print("EMAIL_OVERRIDE_TO is not set. Use the email address you signed up to Resend with.")
        return 2
    import resend

    resend.api_key = s.resend_api_key
    try:
        r = resend.Emails.send({
            "from": s.email_from, "to": [s.email_override_to], "subject": "Decision OS test email",
            "html": _layout("Email delivery works", ["This is a test from Decision OS.",
                                                    "Deadline and dependency emails will arrive like this one."],
                            "Open Decision OS", s.app_url, None),
            "text": "This is a test from Decision OS. Deadline and dependency emails will arrive like this one.",
        })
    except Exception as e:  # noqa: BLE001
        print(f"Send failed: {type(e).__name__}: {e}")
        print("Common causes: wrong key; EMAIL_OVERRIDE_TO is not your Resend account address; EMAIL_FROM uses an unverified domain.")
        return 1
    print(f"Sent. Resend id: {r.get('id') if isinstance(r, dict) else r}. Check {s.email_override_to} (and the spam folder).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
