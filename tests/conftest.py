import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.ai import ReplayAI  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import DB  # noqa: E402
from app.main import create_app  # noqa: E402
from app.qualcomm import ChatResult  # noqa: E402

TOKEN = "test-internal-token"
MANAGER = {"x-internal-token": TOKEN, "x-user-email": "vishal@decisionos.demo"}


def as_user(email):
    return {"x-internal-token": TOKEN, "x-user-email": email}


def notes(name):
    return (ROOT / "fixtures" / f"{name}.txt").read_text(encoding="utf-8")


class ScriptedAI(ReplayAI):
    """Replay AI whose extraction replies come from a script (for failure paths)."""

    mode = "test"

    def __init__(self, s, replies):
        super().__init__(s)
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, **kw):
        from app.prompts import EXTRACTION_SYSTEM
        if messages[0]["content"] != EXTRACTION_SYSTEM:
            return super().chat(messages, **kw)
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return ChatResult(r if isinstance(r, str) else json.dumps(r), None, "test-model", 5, "stop", None, None)


@pytest.fixture
def settings_():
    s = Settings()
    s.internal_token = TOKEN
    s.scheduler_enabled = False
    s.resend_api_key = ""
    s.email_override_to = ""
    s.structured_mode = "json"
    return s


@pytest.fixture
def db():
    return DB(":memory:")


@pytest.fixture
def client(settings_, db):
    return TestClient(create_app(settings_, db, ReplayAI(settings_)))


def make_client(settings_, db, ai):
    return TestClient(create_app(settings_, db, ai))


def extract(client, name="demo_meeting_1", date="2026-10-26"):
    r = client.post("/extract", json={"notes": notes(name), "meeting_date": date}, headers=MANAGER)
    assert r.status_code == 200, r.text
    return r.json()
