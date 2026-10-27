from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    qualcomm_api_key: str = field(default_factory=lambda: os.environ.get("QUALCOMM_API_KEY", "").strip())
    qualcomm_endpoint: str = field(
        default_factory=lambda: os.environ.get("QUALCOMM_ENDPOINT", "https://aisuite.cirrascale.com/apis/v2").strip()
    )
    qualcomm_model: str = field(default_factory=lambda: os.environ.get("QUALCOMM_MODEL", "Llama-3.3-70B").strip())
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("QUALCOMM_EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5").strip()
    )
    reranker_model: str = field(
        default_factory=lambda: os.environ.get("QUALCOMM_RERANKER_MODEL", "").strip()
    )
    # "stream" (default; required: non-streaming JSON replies are lost by the server), "imagine" or "openai".
    qualcomm_client: str = field(default_factory=lambda: os.environ.get("QUALCOMM_CLIENT", "stream").strip())
    # "json" (prompt asks for JSON) or "tool" (schema passed as a function the model must call).
    structured_mode: str = field(default_factory=lambda: os.environ.get("QUALCOMM_STRUCTURED_MODE", "json").strip())
    call_timeout_s: float = field(default_factory=lambda: float(os.environ.get("QUALCOMM_TIMEOUT_S", "45")))
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("QUALCOMM_MAX_TOKENS", "2500")))

    db_path: Path = field(default_factory=lambda: Path(os.environ.get("DECISIONOS_DB", str(ROOT / "data" / "decisionos.db"))))
    # Shared secret between the Next.js server and FastAPI. FastAPI only trusts identity headers carrying it.
    internal_token: str = field(default_factory=lambda: os.environ.get("INTERNAL_API_TOKEN", "").strip())

    resend_api_key: str = field(default_factory=lambda: os.environ.get("RESEND_API_KEY", "").strip())
    email_from: str = field(default_factory=lambda: os.environ.get("EMAIL_FROM", "Decision OS <onboarding@resend.dev>").strip())
    # Resend's free tier only delivers to your own address until a domain is verified;
    # when set, every email is delivered here (the intended recipient is shown in the body).
    email_override_to: str = field(default_factory=lambda: os.environ.get("EMAIL_OVERRIDE_TO", "").strip())
    app_url: str = field(default_factory=lambda: os.environ.get("APP_URL", "http://localhost:3000").strip())

    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    scheduler_minutes: int = field(default_factory=lambda: int(os.environ.get("SCHEDULER_MINUTES", "60")))
    timezone: str = field(default_factory=lambda: os.environ.get("APP_TIMEZONE", "Asia/Kolkata").strip())


def settings() -> Settings:
    return Settings()
