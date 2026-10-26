"""Block 7: the three email triggers, deduplicated, with demo routing and failure handling.

Resend's network call is replaced by a recorder; nothing is sent from tests.
"""

import pytest
import resend

from conftest import MANAGER, as_user, extract, make_client
from app.ai import ReplayAI


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_send(params, options=None):
        calls.append({"params": params, "options": options})
        return {"id": f"re_{len(calls)}"}

    monkeypatch.setattr(resend.Emails, "send", staticmethod(fake_send))
    return calls


@pytest.fixture
def mail_client(settings_, db):
    settings_.resend_api_key = "re_test_key"
    settings_.email_override_to = "inbox@example.com"
    return make_client(settings_, db, ReplayAI(settings_))


def clock(c, date):
    return c.post("/admin/clock", json={"date": date}, headers=MANAGER).json()


def test_trigger1_due_within_24h(mail_client, sent):
    extract(mail_client, "demo_meeting_0", "2026-10-19")
    clock(mail_client, "2026-10-26")  # Ravi's Oct 27 is due tomorrow
    subj = [c["params"]["subject"] for c in sent]
    assert "Due tomorrow: Approve the API contract" in subj
    ravi = next(c for c in sent if "Approve the API contract" in c["params"]["subject"])
    assert ravi["params"]["to"] == ["inbox@example.com"]
    assert "Ravi" in ravi["params"]["html"] and "Mark it done" in ravi["params"]["text"]
    assert ravi["options"]["idempotency_key"].startswith("due24:")


def test_trigger2_overdue_mentions_downstream_and_is_deduplicated(mail_client, sent):
    extract(mail_client, "demo_meeting_0", "2026-10-19")
    clock(mail_client, "2026-10-28")
    over = [c for c in sent if c["params"]["subject"].startswith("Overdue: Approve the API contract")]
    assert len(over) == 1 and "blocking downstream" in over[0]["params"]["subject"]
    assert "Asha" in over[0]["params"]["text"] and "Intended for Ravi" in over[0]["params"]["text"]
    mail_client.post("/admin/run-check", headers=MANAGER)
    mail_client.post("/admin/run-check", headers=MANAGER)
    assert len([c for c in sent if c["params"]["subject"].startswith("Overdue: Approve")]) == 1


def test_trigger2_cc_manager_without_override(settings_, db, sent):
    settings_.resend_api_key = "re_test_key"
    settings_.email_override_to = ""
    c = make_client(settings_, db, ReplayAI(settings_))
    extract(c, "demo_meeting_0", "2026-10-19")
    clock(c, "2026-10-28")
    st = c.get("/state", headers=MANAGER).json()
    assert sent == []  # demo .demo addresses have no inbox, so nothing is sent
    assert all(e["status"] == "skipped" for e in st["emails"])


def test_trigger3_dependency_done(mail_client, sent):
    extract(mail_client, "demo_meeting_1", "2026-10-26")
    st = mail_client.get("/state", headers=MANAGER).json()
    raj = next(a for a in st["actions"] if a["owner"] == "Raj")
    mail_client.patch(f"/items/{raj['id']}/status", json={"status": "done"}, headers=as_user("raj@decisionos.demo"))
    dep = [c for c in sent if c["params"]["subject"] == "You can start: Test payment API"]
    assert len(dep) == 1 and "Raj" in dep[0]["params"]["text"]


def test_no_key_records_skipped(client):
    extract(client, "demo_meeting_0", "2026-10-19")
    client.post("/admin/clock", json={"date": "2026-10-28"}, headers=MANAGER)
    emails = client.get("/state", headers=MANAGER).json()["emails"]
    assert emails and all(e["status"] == "skipped" and "RESEND_API_KEY" in e["error"] for e in emails)


def test_failure_is_recorded_and_retried_later(mail_client, monkeypatch):
    calls = {"n": 0}

    def flaky(params, options=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise resend.exceptions.ResendError(code=500, error_type="application_error", message="boom", suggested_action="")
        return {"id": "re_ok"}

    monkeypatch.setattr(resend.Emails, "send", staticmethod(flaky))
    extract(mail_client, "demo_meeting_0", "2026-10-19")
    clock(mail_client, "2026-10-28")
    first = mail_client.get("/state", headers=MANAGER).json()["emails"]
    assert any(e["status"] == "failed" for e in first)
    mail_client.post("/admin/run-check", headers=MANAGER)
    after = mail_client.get("/state", headers=MANAGER).json()["emails"]
    assert any(e["status"] == "sent" and e["subject"].startswith("Overdue: Approve") for e in after)
