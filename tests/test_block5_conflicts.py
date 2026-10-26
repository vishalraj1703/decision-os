"""Block 5: a second meeting that reverses an earlier decision surfaces a conflict card."""

import json

from app.ai import ReplayAI
from app.prompts import CONFLICT_SYSTEM
from app.qualcomm import ChatResult

from conftest import MANAGER, as_user, extract, make_client


def two_meetings(c):
    extract(c, "demo_meeting_0", "2026-10-19")
    extract(c, "demo_meeting_1", "2026-10-26")
    return c.get("/state", headers=MANAGER).json()


def test_cross_meeting_conflict_with_both_quotes(client):
    st = two_meetings(client)
    cards = [c for c in st["conflicts"] if c["source"] == "cross_meeting"]
    assert len(cards) == 1
    c = cards[0]
    assert c["current"] == "Deploy on AWS" and c["previous"] == "Deploy on Azure"
    assert c["current_evidence"] == "We agreed to deploy on AWS."
    assert c["previous_evidence"] == "We agreed to deploy on Azure."  # quoted from last week's meeting
    assert c["previous_meeting_id"] != c["meeting_id"] and c["status"] == "open"
    # the notes' own "last week we agreed Azure" line is merged into the same card
    assert not [x for x in st["conflicts"] if x["source"] == "in_meeting"]
    assert any(n["kind"] == "contradiction" for n in st["notifications"])


def test_unrelated_decisions_not_flagged(client):
    st = two_meetings(client)
    assert all("Oct 30" not in c["previous"] for c in st["conflicts"])


def test_resolve_confirm_current_supersedes_previous(client):
    st = two_meetings(client)
    c = next(x for x in st["conflicts"] if x["source"] == "cross_meeting")
    assert client.post(f"/contradictions/{c['id']}/resolve", json={"action": "confirm_current"},
                       headers=as_user("raj@decisionos.demo")).status_code == 403
    r = client.post(f"/contradictions/{c['id']}/resolve", json={"action": "confirm_current"}, headers=MANAGER)
    assert r.status_code == 200 and r.json()["status"] == "confirmed_current" and r.json()["resolved_by"] == "Vishal"
    st = client.get("/state", headers=MANAGER).json()
    azure = next(d for d in st["decisions"] if d["text"] == "Deploy on Azure")
    assert azure["review_state"] == "superseded"


def test_resolve_follow_up_and_bad_action(client):
    st = two_meetings(client)
    c = next(x for x in st["conflicts"] if x["source"] == "cross_meeting")
    assert client.post(f"/contradictions/{c['id']}/resolve", json={"action": "nope"}, headers=MANAGER).status_code == 422
    assert client.post(f"/contradictions/{c['id']}/resolve", json={"action": "follow_up"}, headers=MANAGER).json()["status"] == "follow_up"


class SaysNoConflict(ReplayAI):
    def chat(self, messages, **kw):
        if messages[0]["content"] == CONFLICT_SYSTEM:
            return ChatResult(json.dumps({"contradicts": False, "topic": "", "explanation": "related only"}), None, "m", 1, "stop", None, None)
        return super().chat(messages, **kw)


def test_only_model_confirmed_pairs_become_cards(settings_, db):
    c = make_client(settings_, db, SaysNoConflict(settings_))
    st = two_meetings(c)
    assert not [x for x in st["conflicts"] if x["source"] == "cross_meeting"]
    # the in-meeting contradiction the notes state themselves is still shown
    assert [x for x in st["conflicts"] if x["source"] == "in_meeting"]
