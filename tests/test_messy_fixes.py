"""The three gaps found with the messy notes: 'tmrw', in-meeting disagreements, finished work."""

from conftest import MANAGER, ScriptedAI, make_client

NOTES = ("Release sync. He'll send the release notes tmrw EOD. Raj will fix the bug tmrw. "
         "Release date: Sam says Nov 10, Leena says Nov 12. no decision. "
         "Ravi already finished the API contract review. Priya will review the docs, done soon.")


def act(id_, task, owner, deadline, quote, status="open"):
    return {"id": id_, "task": task, "owner": owner, "deadline": deadline, "dependencies": [], "status": status,
            "evidence_quote": quote, "confidence": 0.9, "missing_info": []}


REPLY = {
    "meeting_topic": "Release sync", "decisions": [], "risks": [],
    "actions": [
        act("a1", "Fix the bug", "Raj", "tomorrow", "Raj will fix the bug tmrw."),
        act("a2", "Review the API contract", "Ravi", "UNKNOWN", "Ravi already finished the API contract review.", "done"),
        act("a3", "Review the docs", "Priya", "UNKNOWN", "Priya will review the docs, done soon.", "done"),
    ],
    "contradictions": [{"kind": "disagreement", "topic": "Release date", "current": "Nov 10", "previous": "Nov 12",
                        "current_evidence": "Sam says Nov 10", "previous_evidence": "Leena says Nov 12"}],
}


def state(settings_, db):
    c = make_client(settings_, db, ScriptedAI(settings_, [REPLY]))
    r = c.post("/extract", json={"notes": NOTES, "meeting_date": "2026-10-27"}, headers=MANAGER)
    assert r.status_code == 200, r.text
    return c, c.get("/state", headers=MANAGER).json()


def test_tmrw_matches_tomorrow(settings_, db):
    _, st = state(settings_, db)
    fix = next(a for a in st["actions"] if a["text"] == "Fix the bug")
    assert fix["deadline_date"] == "2026-10-28" and "deadline" not in fix["missing_info"]


def test_finished_work_is_done_only_with_evidence(settings_, db):
    _, st = state(settings_, db)
    acts = {a["text"]: a for a in st["actions"]}
    assert acts["Review the API contract"]["status"] == "done" and acts["Review the API contract"]["color"] == "green"
    assert "deadline" not in acts["Review the API contract"]["missing_info"]
    # "will review ..., done soon" is future work even though the AI said done.
    assert acts["Review the docs"]["status"] == "not_started"
    assert any("does not say it is finished" in x for x in acts["Review the docs"]["checks"])
    assert acts["Fix the bug"]["status"] == "not_started"


def test_disagreement_card(settings_, db):
    c, st = state(settings_, db)
    cards = [x for x in st["conflicts"] if x["source"] == "disagreement"]
    assert len(cards) == 1 and cards[0]["current"] == "Nov 10" and cards[0]["previous"] == "Nov 12"
    assert cards[0]["current_evidence"] == "Sam says Nov 10" and cards[0]["previous_evidence"] == "Leena says Nov 12"
    r = c.post(f"/contradictions/{cards[0]['id']}/resolve", json={"action": "revert"}, headers=MANAGER)
    assert r.json()["status"] == "reverted"
