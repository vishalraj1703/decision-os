"""Hardening for real small-model output: shapes Llama-3.1-8B commonly returns."""

import json

from conftest import MANAGER, ScriptedAI, make_client

NOTES = ("Sprint sync. Raj will fix the login bug by Oct 28. "
         "Priya will test the login fix after Raj is done. Someone should update the docs.")


def ingest(settings_, db, reply):
    ai = ScriptedAI(settings_, [reply, reply])
    c = make_client(settings_, db, ai)
    r = c.post("/extract", json={"notes": NOTES, "meeting_date": "2026-10-26"}, headers=MANAGER)
    return c, r, ai


def action(**kw):
    base = {"task": "Fix the login bug", "owner": "Raj", "deadline": "Oct 28",
            "evidence_quote": "Raj will fix the login bug by Oct 28.", "confidence": 0.9, "missing_info": []}
    base.update(kw)
    return base


def test_prose_around_fenced_json(settings_, db):
    body = {"meeting_topic": "Sprint", "decisions": [], "risks": [], "contradictions": [], "actions": [action(id="a1")]}
    reply = "Here is the extracted data:\n```json\n" + json.dumps(body) + "\n```\nLet me know if you need anything else."
    _, r, ai = ingest(settings_, db, reply)
    assert r.status_code == 200 and r.json()["items"] == 1 and ai.calls == 1


def test_trailing_commas_and_missing_groups(settings_, db):
    reply = '{"meeting_topic": "Sprint", "actions": [' + json.dumps(action(id="a1"))[:-1] + ', },],}'
    _, r, ai = ingest(settings_, db, reply)
    assert r.status_code == 200 and r.json()["items"] == 1 and ai.calls == 1


def test_wrapped_object_and_alias_keys(settings_, db):
    reply = {"result": {"topic": "Sprint", "action_items": [action(id="1")]}}
    _, r, ai = ingest(settings_, db, reply)
    assert r.status_code == 200 and r.json()["items"] == 1 and ai.calls == 1


def test_odd_ids_percent_confidence_and_named_dependencies(settings_, db):
    reply = {"meeting_topic": "Sprint", "decisions": [], "risks": [], "contradictions": [], "actions": [
        action(id="Task-1", confidence="92%", missing_info="none"),
        {"id": "Task-2", "task": "Test the login fix", "owner": "Priya", "deadline": "after Raj is done",
         "dependencies": "Fix the login bug", "evidence_quote": "Priya will test the login fix after Raj is done.",
         "confidence": "0.8", "missing_info": ""},
        {"task": "Update the docs", "owner": None, "deadline": None, "dependencies": [],
         "evidence_quote": "Someone should update the docs.", "confidence": 0.5, "missing_info": "owner, deadline"},
    ]}
    c, r, ai = ingest(settings_, db, reply)
    assert r.status_code == 200 and r.json()["items"] == 3 and ai.calls == 1
    st = c.get("/state", headers=MANAGER).json()
    acts = {a["text"]: a for a in st["actions"]}
    assert acts["Test the login fix"]["depends_on"] == [acts["Fix the login bug"]["id"]]
    assert abs(acts["Fix the login bug"]["confidence"] - 0.92) < 1e-6
    docs = acts["Update the docs"]
    assert docs["owner"] is None and set(docs["missing_info"]) == {"owner", "deadline"}


def test_owner_with_role_annotation(settings_, db):
    reply = {"meeting_topic": "Sprint", "actions": [action(id="a1", owner="Raj (Platform team)")]}
    c, r, _ = ingest(settings_, db, reply)
    a = c.get("/state", headers=MANAGER).json()["actions"][0]
    assert a["owner"] == "Raj" and a["team"] == "Platform"


def test_reply_that_is_not_json_at_all_retries_then_fails_cleanly(settings_, db):
    _, r, ai = ingest(settings_, db, "I could not find any action items in these notes.")
    assert r.status_code == 502 and ai.calls == 2 and r.json()["code"] == "INVALID_AI_RESPONSE"


def test_risk_reporter_is_not_owner(settings_, db):
    notes = "Ops sync. Ravi said the push notification server might not be ready in time."
    reply = {"meeting_topic": "Ops", "actions": [], "decisions": [], "contradictions": [], "risks": [
        {"risk": "Push server may be late", "owner": "Ravi", "deadline": "UNKNOWN", "severity": "medium",
         "evidence_quote": "Ravi said the push notification server might not be ready in time.", "confidence": 0.8, "missing_info": []}]}
    c = make_client(settings_, db, ScriptedAI(settings_, [reply]))
    c.post("/extract", json={"notes": notes, "meeting_date": "2026-10-26"}, headers=MANAGER)
    r = c.get("/state", headers=MANAGER).json()["risks"][0]
    assert r["owner"] is None and "owner" in r["missing_info"] and any("reported this risk" in x for x in r["checks"])
