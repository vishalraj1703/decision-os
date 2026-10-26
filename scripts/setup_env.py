"""Create .env and web/.env.local with fresh random secrets (keeps existing values).

Usage:  .venv\\Scripts\\python scripts\\setup_env.py
The demo login password is written to web/.env.local as DEMO_PASSWORD; it is not printed.
"""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def upsert(path: Path, values: dict[str, str], template: Path | None = None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else (
        template.read_text(encoding="utf-8").splitlines() if template and template.exists() else [])
    seen = set()
    for i, line in enumerate(lines):
        if "=" in line and not line.lstrip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in values:
                seen.add(k)
                if not line.split("=", 1)[1].strip():
                    lines[i] = f"{k}={values[k]}"
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    env = ROOT / ".env"
    cur = read(env)
    token = cur.get("INTERNAL_API_TOKEN") or secrets.token_urlsafe(32)
    upsert(env, {"INTERNAL_API_TOKEN": token}, ROOT / ".env.example")

    web = ROOT / "web" / ".env.local"
    wcur = read(web)
    upsert(web, {
        "NEXTAUTH_URL": wcur.get("NEXTAUTH_URL") or "http://localhost:3000",
        "NEXTAUTH_SECRET": wcur.get("NEXTAUTH_SECRET") or secrets.token_urlsafe(32),
        "BACKEND_URL": wcur.get("BACKEND_URL") or "http://127.0.0.1:8000",
        "INTERNAL_API_TOKEN": token,
        "DEMO_PASSWORD": wcur.get("DEMO_PASSWORD") or secrets.token_urlsafe(9),
    })
    # The two files must share the same internal token.
    upsert(web, {"INTERNAL_API_TOKEN": token})
    text = web.read_text(encoding="utf-8").splitlines()
    text = [f"INTERNAL_API_TOKEN={token}" if l.startswith("INTERNAL_API_TOKEN=") else l for l in text]
    web.write_text("\n".join(text) + "\n", encoding="utf-8")
    print("Wrote .env and web/.env.local. Demo login password: see DEMO_PASSWORD in web/.env.local.")
    print("Add QUALCOMM_API_KEY (and RESEND_API_KEY, EMAIL_OVERRIDE_TO) to .env yourself.")


if __name__ == "__main__":
    main()
