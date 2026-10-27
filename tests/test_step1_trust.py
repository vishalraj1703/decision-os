"""Step 1 trust layer: redaction, the Verifier (pass 2), the self-check replay and the AI audit log."""

import json
import sqlite3

from app.db import DB
from app.prompts import VERIFY_SYSTEM
from app.qualcomm import ChatResult, QualcommError
from app.redact import redact

from conftest import MANAGER, ScriptedAI, extract, make_client

NOTES = ("Sprint 14 planning. Priya will finish the API spec by Nov 4. "
         "Maybe look at offsite options, Arun? Ask Meera whether someone can close the vendor renewal by Nov 6.")


def act(id_, task, owner, deadline, quote, conf=0.9):
    return {"id": id_, "task": task, "owner": owner, "deadline": deadline, "dependencies": [],
            "evidence_quote": quote, "confidence": conf, "missing_info": []}


PASS1 = {"meeting_topic": "Sprint 14", "decisions": [], "risks": [], "contradictions": [], "actions": [
    act("a1", "Finish the API spec", "Priya", "Nov 4", "Priya will finish the API spec by Nov 4."),
    act("a2", "Book offsite venue", "Arun", "UNKNOWN", "Maybe look at offsite options, Arun?"),
    act("a3", "Close the vendor renewal", "Meera", "Nov 6", "Ask Meera whether someone can close the vendor renewal by Nov 6."),
]}


class VerifyingAI(ScriptedAI):
    """Scripted extraction plus scripted Verifier replies (or the replay heuristic when none are given)."""

    def __init__(self, s, replies, verdicts=None):
        super().__init__(s, replies)
        self.verdicts = list(verdicts or [])
        self.seen: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.seen.append(messages)
        if messages[0]["content"] == VERIFY_SYSTEM and self.verdicts:
            v = self.verdicts.pop(0)
            if isinstance(v, Exception):
                raise v
            return ChatResult(v if isinstance(v, str) else json.dumps(v), None, "test-verifier", 7, "stop", None, None)
        return super().chat(messages, **kw)


def ingest(settings_, db, ai, notes=NOTES):
    c = make_client(settings_, db, ai)
    r = c.post("/extract", json={"notes": notes, "meeting_date": "2026-10-27"}, headers=MANAGER)
    assert r.status_code == 200, r.text
    return c, r.json()


def test_redact_masks_contacts_not_dates():
    text, n = redact("Call Raj on +91 98765 43210 or raj.k@acme.com by 2026-10-30. Card 4111 1111 1111 1111.")
    assert text == "Call Raj on [phone] or [email] by 2026-10-30. Card [id]."
    assert n == {"email": 1, "phone": 1, "id": 1}
    assert redact("Raj will fix the login bug by Oct 28, budget 25000.") == ("Raj will fix the login bug by Oct 28, budget 25000.", {})


def test_ai_only_sees_redacted_notes_and_they_are_stored_masked(settings_, db):
    notes = "Ops sync. Raj will fix the login bug tomorrow, call him on 98450 12345 or raj@acme.com."
    reply = {"meeting_topic": "Ops", "decisions": [], "risks": [], "contradictions": [], "actions": [
        act("a1", "Fix login", "Raj", "tomorrow", "Raj will fix the login bug tomorrow, call him on [phone] or [email].")]}
    ai = VerifyingAI(settings_, [reply])
    c, out = ingest(settings_, db, ai, notes)
    assert out["items"] == 1 and out["redactions"] == {"email": 1, "phone": 1}
    sent = json.dumps(ai.seen)
    assert "98450" not in sent and "raj@acme.com" not in sent
    src = c.get(f"/meetings/{out['meeting_id']}/source", headers=MANAGER).json()
    assert "[phone]" in src["notes"] and "raj@acme.com" not in src["notes"]


def test_verifier_removes_a_suggestion_and_replay_shows_it(settings_, db):
    c, out = ingest(settings_, db, VerifyingAI(settings_, [PASS1]))  # replay heuristic as the Verifier
    assert out["items"] == 2 and out["verify"]["status"] == "ok" and out["verify"]["removed"] == 1
    gone = next(r for r in out["rejected"] if r["by"] == "verifier")
    assert gone["text"] == "Book offsite venue" and gone["reason"].startswith("Verifier:")
    replay = c.get(f"/meetings/{out['meeting_id']}/source", headers=MANAGER).json()["replay"]
    assert [r["outcome"] for r in replay] == ["kept", "removed", "kept"]
    assert replay[1]["reasons"][0]["by"] == "verifier" and replay[1]["owner"] == "Arun"


def test_verifier_downgrades_guessed_owner(settings_, db):
    verdicts = {"verdicts": [
        {"id": "a1", "supported": True, "owner_stated": True, "deadline_stated": True, "reason": ""},
        {"id": "a2", "supported": False, "reason": "A suggestion, not an agreed task."},
        {"id": "a3", "supported": True, "owner_stated": False, "deadline_stated": True,
         "reason": "Meera is asked, not named as the owner."}]}
    c, out = ingest(settings_, db, VerifyingAI(settings_, [PASS1], [verdicts]))
    st = c.get("/state", headers=MANAGER).json()
    vendor = next(a for a in st["actions"] if "vendor" in a["text"])
    assert vendor["owner"] is None and "owner" in vendor["missing_info"] and vendor["review_state"] == "needs_review"
    assert any(x.startswith("Verifier:") for x in vendor["checks"])
    assert vendor["verification"] == {"quote_found": True, "supported": True, "owner_ok": False, "deadline_ok": True,
                                      "by": "test-verifier", "note": "Meera is asked, not named as the owner."}
    spec = next(a for a in st["actions"] if "API spec" in a["text"])
    assert spec["owner"] == "Priya" and spec["verification"]["supported"] is True
    replay = c.get(f"/meetings/{out['meeting_id']}/source", headers=MANAGER).json()["replay"]
    assert replay[2]["outcome"] == "corrected" and replay[2]["final"]["owner"] == "UNKNOWN"


def test_verifier_cannot_add_or_remove_by_omission(settings_, db):
    verdicts = {"verdicts": [{"id": "a9", "supported": False}, {"id": "a1", "supported": True}]}
    c, out = ingest(settings_, db, VerifyingAI(settings_, [PASS1], [verdicts]))
    assert out["items"] == 3  # unknown id ignored; unjudged items kept
    st = c.get("/state", headers=MANAGER).json()
    unjudged = [a for a in st["actions"] if a["verification"]["supported"] is None]
    assert len(unjudged) == 2


def test_verifier_failure_keeps_items_unverified(settings_, db):
    ai = VerifyingAI(settings_, [PASS1], ["not json", QualcommError("TIMEOUT", "slow", True)])
    c, out = ingest(settings_, db, ai)
    assert out["items"] == 3 and out["verify"]["status"] == "failed" and out["verify"]["attempts"] == 2
    st = c.get("/state", headers=MANAGER).json()
    assert all(a["verification"]["supported"] is None for a in st["actions"])


def test_trust_receipt_on_demo_meeting(client):
    extract(client)
    st = client.get("/state", headers=MANAGER).json()
    for i in st["actions"] + st["decisions"] + st["risks"]:
        assert i["verification"]["quote_found"] is True and i["verification"]["supported"] is True


def test_audit_log_records_calls_without_text(settings_, db):
    c, out = ingest(settings_, db, VerifyingAI(settings_, ["Sure! here you go", PASS1]))
    calls = c.get("/state", headers=MANAGER).json()["ai_calls"]
    mine = [x for x in calls if x["meeting_id"] == out["meeting_id"]]
    purposes = sorted(x["purpose"] for x in mine)
    assert purposes == ["extract", "extract retry", "verify"]
    first = next(x for x in mine if x["purpose"] == "extract")
    assert first["ok"] and first["verdict"].endswith("problem") and first["model"] == "test-model"
    assert next(x for x in mine if x["purpose"] == "verify")["verdict"] == "2 supported, 1 removed, 0 corrected"
    assert "Priya" not in json.dumps(calls) and "offsite" not in json.dumps(calls)


def test_audit_log_records_failures(settings_, db):
    ai = VerifyingAI(settings_, [QualcommError("AUTH", "bad key", False)])
    c = make_client(settings_, db, ai)
    assert c.post("/extract", json={"notes": NOTES, "meeting_date": "2026-10-27"}, headers=MANAGER).status_code == 502
    calls = c.get("/state", headers=MANAGER).json()["ai_calls"]
    assert calls[0]["purpose"] == "extract" and calls[0]["ok"] is False and calls[0]["verdict"] == "AUTH"


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE meetings (id TEXT PRIMARY KEY, topic TEXT NOT NULL, title TEXT, meeting_date TEXT NOT NULL, notes TEXT NOT NULL,
            created_by TEXT, model TEXT, attempts INTEGER, latency_ms INTEGER, rejected_json TEXT, created_at TEXT NOT NULL);
        INSERT INTO meetings VALUES ('m1', 'Old', NULL, '2026-10-01', 'x', NULL, 'm', 1, 0, '[]', '2026-10-01');
    """)
    con.close()
    db = DB(path)
    m = db.meeting("m1")
    assert m["replay"] == [] and m["verify"] == {} and m["redactions"] == {}
    assert db.ai_calls() == []
